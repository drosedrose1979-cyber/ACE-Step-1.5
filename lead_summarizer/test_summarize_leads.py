"""End-to-end tests of the run loop with a mocked Claude client (no network)."""

import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

HAS_SDK = importlib.util.find_spec("anthropic") is not None
if HAS_SDK:
    import anthropic
    import httpx2

    from lead_summarizer.config import Settings, default_paths
    from lead_summarizer.summarize_leads import run

FAKE_KEY = "sk-ant-test-DO-NOT-LEAK-123"
NOW = datetime(2026, 11, 7, 9, 0, tzinfo=timezone.utc)
TRANSCRIPT = (
    "Hi, this is Linda Marsh. A pipe burst and there's water spraying everywhere. "
    "We're at 1420 Hickory Ridge Court in Union. My cell is 859-555-0142. Call me back."
)
GOOD_FIELDS = {
    "caller_name": "Linda Marsh",
    "callback_number": "859-555-0142",
    "address_or_town": "1420 Hickory Ridge Court, Union",
    "problem": "Burst pipe spraying water.",
    "problem_quote": "there's water spraying everywhere",
    "urgency": "emergency",
    "human_callback_requested": "yes",
}


def _response(fields=None, stop_reason="end_turn", inp=900, out=300):
    """Fake Messages API response shaped like the SDK's."""
    text = json.dumps(fields if fields is not None else GOOD_FIELDS)
    usage = SimpleNamespace(
        input_tokens=inp, output_tokens=out, cache_creation_input_tokens=0,
        cache_read_input_tokens=0, iterations=None,
    )
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason, usage=usage, model="claude-opus-5-5",
    )


@unittest.skipUnless(HAS_SDK, "anthropic SDK not installed")
class TestRun(unittest.TestCase):
    """The run loop writes summaries, logs every file, and respects the cap."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.paths = default_paths(Path(self._tmp.name))
        self.paths.incoming.mkdir(parents=True)
        (self.paths.incoming / "call_a.txt").write_text(TRANSCRIPT, encoding="utf-8")
        self.settings = Settings("claude-opus-5-5", "low", 4096, True, 2.00)
        self.client = MagicMock()
        self.client.beta.messages.create.return_value = _response()
        self.factory = MagicMock(return_value=self.client)

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, api_key=FAKE_KEY):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = run(self.paths, self.settings, api_key, self.factory, now_fn=lambda: NOW)
        return code, out.getvalue() + err.getvalue()

    def _log(self):
        return self.paths.run_log.read_text(encoding="utf-8")

    def test_success_writes_summary_and_logs_pass(self):
        code, _ = self._run()
        self.assertEqual(code, 0)
        summary = (self.paths.summaries / "call_a_summary.txt").read_text(encoding="utf-8")
        self.assertIn("859-555-0142", summary)
        self.assertIn("Urgency:          emergency", summary)
        self.assertIn("| call_a.txt | PASS |", self._log())
        ledger = json.loads(self.paths.spend_ledger.read_text(encoding="utf-8"))
        self.assertAlmostEqual(ledger["2026-11-07"], (900 * 4 + 300 * 20) / 1e6)

    def test_request_uses_config_model_schema_and_fallback(self):
        self._run()
        kwargs = self.client.beta.messages.create.call_args.kwargs
        self.assertEqual(kwargs["model"], "claude-opus-5-5")
        self.assertEqual(kwargs["fallbacks"], "default")
        self.assertEqual(kwargs["output_config"]["format"]["type"], "json_schema")
        self.assertEqual(kwargs["output_config"]["effort"], "low")

    def test_hallucinated_number_is_not_written(self):
        self.client.beta.messages.create.return_value = _response(
            dict(GOOD_FIELDS, callback_number="859-555-7777")
        )
        self._run()
        summary = (self.paths.summaries / "call_a_summary.txt").read_text(encoding="utf-8")
        self.assertIn("Callback number:  not given", summary)
        self.assertIn("removed", summary)

    def test_missing_key_makes_no_client_and_logs_fail(self):
        code, output = self._run(api_key=None)
        self.assertEqual(code, 2)
        self.factory.assert_not_called()
        self.assertIn("| call_a.txt | FAIL | ANTHROPIC_API_KEY is not set", self._log())

    def test_cost_cap_blocks_call_before_it_is_made(self):
        self.paths.spend_ledger.parent.mkdir(parents=True, exist_ok=True)
        self.paths.spend_ledger.write_text(json.dumps({"2026-11-07": 1.95}), encoding="utf-8")
        code, output = self._run()
        self.assertEqual(code, 2)
        self.client.beta.messages.create.assert_not_called()
        self.assertIn("daily cost cap $2.00", self._log())
        self.assertIn("WARNING", output)

    def test_refusal_logs_fail_and_still_records_cost(self):
        self.client.beta.messages.create.return_value = _response(stop_reason="refusal")
        code, _ = self._run()
        self.assertEqual(code, 1)
        self.assertIn("FAIL | model declined", self._log())
        self.assertTrue(self.paths.spend_ledger.exists())

    def test_rejected_key_stops_run(self):
        request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
        error = anthropic.AuthenticationError(
            "invalid x-api-key", response=httpx2.Response(401, request=request), body=None
        )
        self.client.beta.messages.create.side_effect = error
        code, _ = self._run()
        self.assertEqual(code, 2)
        self.assertIn("API key rejected", self._log())

    def test_key_never_appears_in_output_or_files(self):
        _, output = self._run()
        self.assertNotIn(FAKE_KEY, output)
        for path in Path(self._tmp.name).rglob("*"):
            if path.is_file():
                self.assertNotIn(FAKE_KEY, path.read_text(encoding="utf-8", errors="ignore"))

    def test_already_summarized_files_are_skipped(self):
        self._run()
        self._run()
        self.assertEqual(self.client.beta.messages.create.call_count, 1)


if __name__ == "__main__":
    unittest.main()
