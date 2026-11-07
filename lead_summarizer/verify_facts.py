"""Checks that every name, number, address, and quote really appears in the transcript.

The model is told not to guess, but this module does not trust that. Any name,
number, or address that cannot be found in the transcript is replaced with
"not given" and the removed value is noted for the owner to review.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

NOT_GIVEN = "not given"

_WORD_DIGITS = {
    "zero": "0", "oh": "0", "o": "0", "one": "1", "two": "2", "three": "3",
    "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
}
_QUOTE_CHARS = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})
_MIN_PHONE_DIGITS = 7


@dataclass
class VerifiedLead:
    """Lead fields after checking, plus notes and the proof-quote result."""

    fields: dict[str, str]
    notes: list[str] = field(default_factory=list)
    proof_ok: bool = True


def _normalize(text: str) -> str:
    """Lowercase, straighten curly quotes, and collapse whitespace."""
    return re.sub(r"\s+", " ", text.translate(_QUOTE_CHARS).lower()).strip()


def _tokens(text: str) -> list[str]:
    """Split text into lowercase alphanumeric words."""
    return re.findall(r"[a-z0-9]+", _normalize(text))


def _is_not_given(value: str) -> bool:
    """True for empty values or any capitalization of "not given"."""
    return _normalize(value) in ("", NOT_GIVEN)


def spoken_digits(text: str) -> str:
    """All digits in ``text``, with spoken digits ("five", "oh") converted."""
    return "".join(_WORD_DIGITS.get(tok, tok if tok.isdigit() else "") for tok in _tokens(text))


def number_in_transcript(number: str, transcript: str) -> bool:
    """True when the number's digits (written or spoken) appear in order in the transcript."""
    digits = spoken_digits(number)
    return len(digits) >= _MIN_PHONE_DIGITS and digits in spoken_digits(transcript)


def words_in_transcript(value: str, transcript: str) -> bool:
    """True when every word of ``value`` appears somewhere in the transcript."""
    words = _tokens(value)
    available = set(_tokens(transcript))
    return bool(words) and all(word in available for word in words)


def quote_in_transcript(quote: str, transcript: str) -> bool:
    """True when the quote (minus wrapping quote marks) is a verbatim slice of the text."""
    cleaned = _normalize(quote).strip("\"' ").rstrip(".,!?;:")
    return bool(cleaned) and cleaned in _normalize(transcript)


def _check_field(fields: dict[str, str], notes: list[str], name: str, ok: bool) -> None:
    """Replace an unsupported field with "not given" and record what was removed."""
    value = fields[name]
    if _is_not_given(value):
        fields[name] = NOT_GIVEN
    elif not ok:
        notes.append(f"{name}: model said '{value}' but it is not in the transcript; removed.")
        fields[name] = NOT_GIVEN


def verify_lead(fields: dict[str, str], transcript: str) -> VerifiedLead:
    """Return a checked copy of ``fields``; never adds information, only removes it."""
    checked = dict(fields)
    notes: list[str] = []
    checks = {
        "caller_name": words_in_transcript(fields["caller_name"], transcript),
        "callback_number": number_in_transcript(fields["callback_number"], transcript),
        "address_or_town": words_in_transcript(fields["address_or_town"], transcript),
    }
    for name, ok in checks.items():
        _check_field(checked, notes, name, ok)
    for name in ("problem", "urgency"):
        if _is_not_given(checked[name]):
            checked[name] = NOT_GIVEN
    proof_ok = _check_proof(checked, notes, transcript)
    return VerifiedLead(fields=checked, notes=notes, proof_ok=proof_ok)


def _check_proof(fields: dict[str, str], notes: list[str], transcript: str) -> bool:
    """A stated problem must come with a quote that is really in the transcript."""
    quote = fields["problem_quote"]
    if _is_not_given(quote):
        fields["problem_quote"] = NOT_GIVEN
        if fields["problem"] == NOT_GIVEN:
            return True
        notes.append("problem_quote: no proof quote was given for the problem.")
        return False
    if quote_in_transcript(quote, transcript):
        return True
    notes.append(f"problem_quote: '{quote}' is not word-for-word in the transcript.")
    fields["problem_quote"] = NOT_GIVEN
    return False
