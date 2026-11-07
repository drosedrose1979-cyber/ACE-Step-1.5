"""Configuration for the lead summarizer: model, cost cap, prices, and paths.

Edit the constants here, or override the model with the
``LEAD_SUMMARIZER_MODEL`` environment variable. The API key is never stored
here; it is read only from ``ANTHROPIC_API_KEY`` at run time.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Model name lives in config, not in code. Override without editing this file:
#   PowerShell:  $env:LEAD_SUMMARIZER_MODEL = "claude-haiku-5-5"
DEFAULT_MODEL_NAME = "claude-opus-5-5"
MODEL_ENV_VAR = "LEAD_SUMMARIZER_MODEL"
API_KEY_ENV_VAR = "ANTHROPIC_API_KEY"

# "low" keeps thinking (and output cost) small; extraction does not need more.
EFFORT = "low"
MAX_OUTPUT_TOKENS = 4096
REQUEST_TIMEOUT_SECONDS = 120.0

# Server-side refusal fallback: if the model declines, the API retries once on
# Anthropic's recommended fallback model. Priced into the worst-case estimate.
USE_REFUSAL_FALLBACK = True
FALLBACK_BETA = "server-side-fallback-2026-07-01"

DAILY_COST_CAP_USD = 2.00

# USD per 1M tokens: (input, output). Source: Anthropic model price table
# (claude-api reference, cached 2026-10-06). Unknown models are billed at the
# highest rate listed here so the cap errs on the side of stopping early.
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
}
CACHE_WRITE_MULTIPLIER = 2.0  # worst case (1-hour cache write)
CACHE_READ_MULTIPLIER = 0.1

# Transcripts longer than this are rejected, never truncated.
MAX_TRANSCRIPT_CHARS = 60_000

BASE_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Settings:
    """Run settings for one summarizer invocation."""

    model: str
    effort: str
    max_output_tokens: int
    use_fallback: bool
    daily_cap_usd: float


@dataclass(frozen=True)
class Paths:
    """Folder and file locations used by the summarizer."""

    incoming: Path
    summaries: Path
    run_log: Path
    spend_ledger: Path


def load_settings() -> Settings:
    """Build settings from the constants above plus the model env override."""
    model = os.environ.get(MODEL_ENV_VAR, "").strip() or DEFAULT_MODEL_NAME
    return Settings(
        model=model,
        effort=EFFORT,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        use_fallback=USE_REFUSAL_FALLBACK,
        daily_cap_usd=DAILY_COST_CAP_USD,
    )


def default_paths(base_dir: Path = BASE_DIR) -> Paths:
    """Return the standard folder layout rooted at ``base_dir``."""
    return Paths(
        incoming=base_dir / "calls" / "incoming",
        summaries=base_dir / "calls" / "summaries",
        run_log=base_dir / "logs" / "run_log.txt",
        spend_ledger=base_dir / "logs" / "spend_ledger.json",
    )
