"""Processes one transcript: budget gate, API call, spend record, fact check, write."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import anthropic

from lead_summarizer import config
from lead_summarizer.claude_extract import (
    ExtractionError,
    build_request,
    call_claude,
    parse_response,
)
from lead_summarizer.config import Paths, Settings
from lead_summarizer.cost_guard import (
    CostCapExceeded,
    LedgerError,
    actual_call_cost,
    check_budget,
    load_spend,
    record_spend,
    worst_case_call_cost,
)
from lead_summarizer.output_files import render_summary, write_summary
from lead_summarizer.verify_facts import verify_lead


@dataclass
class FileOutcome:
    """Result for one transcript; ``stop_all`` halts the rest of the run."""

    passed: bool
    detail: str
    stop_all: bool = False


def _request_chars(request: dict[str, Any]) -> int:
    """Characters sent to the model, used for the worst-case cost estimate."""
    return len(request["system"]) + sum(len(m["content"]) for m in request["messages"])


def _budget_gate(request: dict[str, Any], settings: Settings, paths: Paths, day: str) -> str | None:
    """Return a stop reason if this call could pass the daily cap, else None."""
    worst = worst_case_call_cost(
        _request_chars(request), settings.model, settings.max_output_tokens, settings.use_fallback
    )
    try:
        check_budget(load_spend(paths.spend_ledger, day), worst, settings.daily_cap_usd)
    except (CostCapExceeded, LedgerError) as exc:
        return f"STOPPED: {exc}"
    return None


def _send(client: Any, request: dict[str, Any]) -> tuple[Any, FileOutcome | None]:
    """Call the API; map errors to a failed outcome instead of raising."""
    try:
        return call_claude(client, request), None
    except anthropic.AuthenticationError:
        return None, FileOutcome(False, "API key rejected (authentication error)", stop_all=True)
    except anthropic.PermissionDeniedError:
        return None, FileOutcome(False, "API key lacks permission for this model", stop_all=True)
    except anthropic.NotFoundError:
        return None, FileOutcome(False, f"model '{request['model']}' not found", stop_all=True)
    except anthropic.APIStatusError as exc:
        return None, FileOutcome(False, f"API error HTTP {exc.status_code}")
    except anthropic.APIConnectionError:
        return None, FileOutcome(False, "network error reaching the API")


def _finish(
    path: Path,
    transcript: str,
    response: Any,
    cost: float,
    total: float,
    now: datetime,
    paths: Paths,
) -> FileOutcome:
    """Parse, fact-check, and write the summary for a completed API call."""
    try:
        fields = parse_response(response)
    except ExtractionError as exc:
        return FileOutcome(False, f"{exc}; cost ${cost:.4f}")
    lead = verify_lead(fields, transcript)
    text = render_summary(path.name, lead, lead.proof_ok, cost, now)
    out = write_summary(paths.summaries, path.name, text)
    detail = f"wrote {out.name}; cost ${cost:.4f}; today ${total:.4f}"
    if lead.notes:
        detail += f"; {len(lead.notes)} field(s) removed or flagged"
    if not lead.proof_ok:
        detail = "proof quote not verified; " + detail
    return FileOutcome(lead.proof_ok, detail)


def process_file(
    path: Path, client: Any, settings: Settings, paths: Paths, now: datetime
) -> FileOutcome:
    """Summarize one transcript file and return its outcome. Never sends anything else."""
    transcript = path.read_text(encoding="utf-8", errors="replace").strip()
    if not transcript:
        return FileOutcome(False, "empty transcript; no API call made")
    if len(transcript) > config.MAX_TRANSCRIPT_CHARS:
        return FileOutcome(False, "transcript too long; not truncated, no API call made")
    day = now.date().isoformat()
    request = build_request(path.name, transcript, settings)
    stop_reason = _budget_gate(request, settings, paths, day)
    if stop_reason:
        return FileOutcome(False, stop_reason, stop_all=True)
    response, failure = _send(client, request)
    if failure:
        return failure
    cost = actual_call_cost(response.usage, getattr(response, "model", None))
    try:
        total = record_spend(paths.spend_ledger, day, cost)
    except LedgerError as exc:
        return FileOutcome(False, f"STOPPED: {exc}", stop_all=True)
    outcome = _finish(path, transcript, response, cost, total, now, paths)
    if total >= settings.daily_cap_usd:
        outcome.stop_all = True
        outcome.detail += f"; STOPPED: daily cap ${settings.daily_cap_usd:.2f} reached"
    return outcome
