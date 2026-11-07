"""Writes summary files and the per-run log. Local disk only; nothing is sent."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from lead_summarizer.verify_facts import VerifiedLead

_LABELS = [
    ("caller_name", "Caller name"),
    ("callback_number", "Callback number"),
    ("address_or_town", "Address or town"),
    ("problem", "Problem"),
    ("problem_quote", "Proof (quote)"),
    ("urgency", "Urgency"),
    ("human_callback_requested", "Human callback"),
]


def summary_path(summaries_dir: Path, source_name: str) -> Path:
    """Where the summary for ``source_name`` is written."""
    return summaries_dir / f"{Path(source_name).stem}_summary.txt"


def render_summary(
    source_name: str, lead: VerifiedLead, passed: bool, cost_usd: float, when: datetime
) -> str:
    """Build the plain-text summary for one transcript."""
    lines = [
        "LEAD SUMMARY - David Rose LLC plumber line (Union, KY)",
        f"Source file:      {source_name}",
        f"Summarized:       {when.strftime('%Y-%m-%d %H:%M %Z').strip()}",
        f"Status:           {'PASS' if passed else 'FAIL - read the transcript yourself'}",
        "",
    ]
    for key, label in _LABELS:
        value = lead.fields.get(key, "not given")
        if key == "problem_quote" and value != "not given":
            value = f'"{value}"'
        lines.append(f"{label + ':':<18}{value}")
    lines += ["", "Checks:"]
    ok_line = "- all names, numbers, and quotes found in transcript"
    lines += [f"- {note}" for note in lead.notes] or [ok_line]
    lines += ["", f"API cost (this file): ${cost_usd:.4f}", ""]
    return "\n".join(lines)


def write_summary(summaries_dir: Path, source_name: str, text: str) -> Path:
    """Save the summary text and return its path."""
    summaries_dir.mkdir(parents=True, exist_ok=True)
    path = summary_path(summaries_dir, source_name)
    path.write_text(text, encoding="utf-8")
    return path


def append_run_log(
    log_path: Path, when: datetime, file_name: str, passed: bool, detail: str
) -> None:
    """Append one ``time | file | PASS/FAIL | detail`` line to the run log."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    stamp = when.strftime("%Y-%m-%d %H:%M:%S %Z").strip()
    line = f"{stamp} | {file_name} | {'PASS' if passed else 'FAIL'} | {detail}\n"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(line)
