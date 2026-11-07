"""Command-line entry point: summarize every transcript in ``calls/incoming/``.

Usage (from the repository root):
    python -m lead_summarizer            # summarize new transcripts
    python -m lead_summarizer --force    # redo files that already have a summary

Exit codes: 0 all passed, 1 at least one file failed, 2 run stopped early
(missing key, rejected key, or daily cost cap).
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from lead_summarizer import config
from lead_summarizer.config import Paths, Settings
from lead_summarizer.output_files import append_run_log, summary_path

MISSING_KEY_MESSAGE = (
    f"{config.API_KEY_ENV_VAR} is not set. Set it in your own terminal before running. "
    "Do not paste the key into chat or into any file in this folder."
)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse command-line flags."""
    parser = argparse.ArgumentParser(description="Summarize plumbing call transcripts locally.")
    parser.add_argument(
        "--force", action="store_true", help="re-summarize files that already have a summary"
    )
    return parser.parse_args(argv)


def find_transcripts(paths: Paths, force: bool) -> list[Path]:
    """Return incoming .txt files, skipping ones already summarized unless ``force``."""
    files = sorted(paths.incoming.glob("*.txt"))
    if force:
        return files
    return [f for f in files if not summary_path(paths.summaries, f.name).exists()]


def _fail_all(files: list[Path], paths: Paths, now: datetime, detail: str) -> int:
    """Log every file as failed for a run-level problem; returns the stop exit code."""
    for f in files:
        append_run_log(paths.run_log, now, f.name, False, detail)
    print(f"STOPPED: {detail}", file=sys.stderr)
    return 2


def run(
    paths: Paths,
    settings: Settings,
    api_key: str | None,
    client_factory: Callable[[str], Any],
    force: bool = False,
    now_fn: Callable[[], datetime] = lambda: datetime.now().astimezone(),
) -> int:
    """Process all pending transcripts and return an exit code."""
    from lead_summarizer.pipeline import process_file

    files = find_transcripts(paths, force)
    if not files:
        print(f"No new transcripts in {paths.incoming}")
        return 0
    if not api_key:
        return _fail_all(files, paths, now_fn(), MISSING_KEY_MESSAGE)
    if settings.model not in config.PRICES_PER_MTOK:
        return _fail_all(files, paths, now_fn(), f"no price for model '{settings.model}' in config")
    client = client_factory(api_key)
    failed = 0
    for path in files:
        now = now_fn()
        outcome = process_file(path, client, settings, paths, now)
        append_run_log(paths.run_log, now, path.name, outcome.passed, outcome.detail)
        print(f"{'PASS' if outcome.passed else 'FAIL'}  {path.name}: {outcome.detail}")
        failed += 0 if outcome.passed else 1
        if outcome.stop_all:
            print(f"WARNING: run stopped early - {outcome.detail}", file=sys.stderr)
            return 2
    print(f"Done: {len(files) - failed} passed, {failed} failed. Log: {paths.run_log}")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    """CLI wrapper: reads the key from the environment only, then runs."""
    from lead_summarizer.claude_extract import make_client

    args = parse_args(argv)
    api_key = os.environ.get(config.API_KEY_ENV_VAR, "").strip() or None
    return run(config.default_paths(), config.load_settings(), api_key, make_client, args.force)
