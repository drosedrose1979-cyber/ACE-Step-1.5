"""Daily spend tracking and the hard cost cap.

Before each API call the worst-case cost of that call is checked against what
has already been spent today. After the call, the real cost from the API's
usage report is added to a local ledger (``logs/spend_ledger.json``).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from lead_summarizer import config

CHARS_PER_TOKEN_ESTIMATE = 3  # conservative; real English text is closer to 4
PROMPT_OVERHEAD_TOKENS = 800  # system prompt + JSON schema + wrapper text


class CostCapExceeded(Exception):
    """Raised when the next call could push today's spend past the cap."""


class LedgerError(Exception):
    """Raised when the spend ledger cannot be read, so spend is unknown."""


def rate_for(model: str | None) -> tuple[float, float]:
    """Return (input, output) USD per 1M tokens; unknown models get the max rate."""
    if model in config.PRICES_PER_MTOK:
        return config.PRICES_PER_MTOK[model]
    return (
        max(p[0] for p in config.PRICES_PER_MTOK.values()),
        max(p[1] for p in config.PRICES_PER_MTOK.values()),
    )


def worst_case_call_cost(prompt_chars: int, model: str, max_output: int, fallback: bool) -> float:
    """Upper-bound USD cost of one request, including a fallback attempt if enabled."""
    input_tokens = math.ceil(prompt_chars / CHARS_PER_TOKEN_ESTIMATE) + PROMPT_OVERHEAD_TOKENS
    in_rate, out_rate = rate_for(model)
    cost = (input_tokens * in_rate + max_output * out_rate) / 1_000_000
    if fallback:
        max_in, max_out = rate_for(None)
        cost += (input_tokens * max_in + max_output * max_out) / 1_000_000
    return cost


def _usage_entry_cost(entry: Any, model: str | None) -> float:
    """USD cost of one usage block (top-level usage or one fallback iteration)."""
    in_rate, out_rate = rate_for(model)
    input_tokens = getattr(entry, "input_tokens", 0) or 0
    output_tokens = getattr(entry, "output_tokens", 0) or 0
    cache_write = getattr(entry, "cache_creation_input_tokens", 0) or 0
    cache_read = getattr(entry, "cache_read_input_tokens", 0) or 0
    billed_input = (
        input_tokens
        + cache_write * config.CACHE_WRITE_MULTIPLIER
        + cache_read * config.CACHE_READ_MULTIPLIER
    )
    return (billed_input * in_rate + output_tokens * out_rate) / 1_000_000


def actual_call_cost(usage: Any, served_model: str | None) -> float:
    """USD cost from the API usage report; sums per-attempt iterations when present."""
    iterations = getattr(usage, "iterations", None) or []
    if not iterations:
        return _usage_entry_cost(usage, served_model)
    return sum(
        _usage_entry_cost(item, getattr(item, "model", None) or served_model)
        for item in iterations
    )


def _read_ledger(ledger_path: Path) -> dict[str, float]:
    """Load the ledger; a missing file means nothing spent yet."""
    if not ledger_path.exists():
        return {}
    try:
        data = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LedgerError(f"cannot read spend ledger {ledger_path.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise LedgerError(f"spend ledger {ledger_path.name} is not a JSON object")
    return {str(k): float(v) for k, v in data.items()}


def load_spend(ledger_path: Path, day: str) -> float:
    """Return USD already spent on ``day`` (YYYY-MM-DD)."""
    return _read_ledger(ledger_path).get(day, 0.0)


def record_spend(ledger_path: Path, day: str, amount: float) -> float:
    """Add ``amount`` to ``day`` in the ledger and return the new daily total."""
    ledger = _read_ledger(ledger_path)
    ledger[day] = round(ledger.get(day, 0.0) + amount, 6)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(ledger, indent=2, sort_keys=True), encoding="utf-8")
    return ledger[day]


def check_budget(spent_today: float, next_call_cost: float, cap: float) -> None:
    """Raise CostCapExceeded if ``spent_today + next_call_cost`` would pass ``cap``."""
    if spent_today + next_call_cost > cap:
        raise CostCapExceeded(
            f"daily cost cap ${cap:.2f} would be passed: spent ${spent_today:.4f} today, "
            f"next call could cost up to ${next_call_cost:.4f}"
        )
