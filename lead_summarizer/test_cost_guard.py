"""Tests for spend estimates, the ledger, and the daily cap."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from lead_summarizer.cost_guard import (
    CostCapExceeded,
    LedgerError,
    actual_call_cost,
    check_budget,
    load_spend,
    record_spend,
    worst_case_call_cost,
)


def _usage(model=None, inp=0, out=0, iterations=None):
    """Build a fake usage object shaped like the SDK's."""
    return SimpleNamespace(
        model=model, input_tokens=inp, output_tokens=out,
        cache_creation_input_tokens=0, cache_read_input_tokens=0, iterations=iterations,
    )


class TestCostEstimates(unittest.TestCase):
    """Worst-case and actual cost math."""

    def test_worst_case_without_fallback(self):
        # 3000 chars -> 1000 + 800 overhead = 1800 input tokens; 4096 output tokens.
        cost = worst_case_call_cost(3000, "claude-opus-5-5", 4096, fallback=False)
        self.assertAlmostEqual(cost, (1800 * 4 + 4096 * 20) / 1e6)

    def test_worst_case_adds_fallback_attempt_at_max_rate(self):
        cost = worst_case_call_cost(3000, "claude-opus-5-5", 4096, fallback=True)
        self.assertAlmostEqual(cost, (1800 * 4 + 4096 * 20 + 1800 * 5 + 4096 * 25) / 1e6)

    def test_actual_cost_single_attempt(self):
        cost = actual_call_cost(_usage(inp=1000, out=500), "claude-opus-5-5")
        self.assertAlmostEqual(cost, (1000 * 4 + 500 * 20) / 1e6)

    def test_actual_cost_sums_fallback_iterations_per_model(self):
        iterations = [
            _usage("claude-opus-5-5", 1000, 50),
            _usage("claude-opus-4-8", 1000, 400),
        ]
        cost = actual_call_cost(_usage(inp=1000, out=400, iterations=iterations), "claude-opus-4-8")
        self.assertAlmostEqual(cost, (1000 * 4 + 50 * 20 + 1000 * 5 + 400 * 25) / 1e6)

    def test_unknown_model_is_priced_at_highest_rate(self):
        cost = actual_call_cost(_usage(inp=1000, out=1000), "some-new-model")
        self.assertAlmostEqual(cost, (1000 * 5 + 1000 * 25) / 1e6)


class TestLedgerAndCap(unittest.TestCase):
    """Daily ledger storage and cap enforcement."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ledger = Path(self._tmp.name) / "spend_ledger.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_record_and_load_are_per_day(self):
        record_spend(self.ledger, "2026-11-07", 0.25)
        record_spend(self.ledger, "2026-11-07", 0.50)
        record_spend(self.ledger, "2026-11-08", 0.10)
        self.assertAlmostEqual(load_spend(self.ledger, "2026-11-07"), 0.75)
        self.assertAlmostEqual(load_spend(self.ledger, "2026-11-08"), 0.10)
        self.assertEqual(load_spend(self.ledger, "2026-11-09"), 0.0)

    def test_corrupt_ledger_raises(self):
        self.ledger.write_text("{not json", encoding="utf-8")
        with self.assertRaises(LedgerError):
            load_spend(self.ledger, "2026-11-07")

    def test_cap_blocks_call_that_would_pass_it(self):
        with self.assertRaises(CostCapExceeded):
            check_budget(1.90, 0.20, 2.00)

    def test_cap_allows_call_under_it(self):
        check_budget(1.00, 0.20, 2.00)


if __name__ == "__main__":
    unittest.main()
