"""Tests for the transcript fact checks in verify_facts."""

import unittest

from lead_summarizer.verify_facts import NOT_GIVEN, number_in_transcript, verify_lead

TRANSCRIPT = (
    "Hi, this is Linda Marsh. A pipe burst in our basement and there’s water "
    "spraying everywhere down there. We're at 1420 Hickory Ridge Court in Union. "
    "My cell is 859-555-0142. Please call me back."
)


def _fields(**overrides: str) -> dict[str, str]:
    """Return a full, valid field set with optional overrides."""
    base = {
        "caller_name": "Linda Marsh",
        "callback_number": "859-555-0142",
        "address_or_town": "1420 Hickory Ridge Court, Union",
        "problem": "Burst pipe flooding the basement.",
        "problem_quote": "there's water spraying everywhere down there",
        "urgency": "emergency",
        "human_callback_requested": "yes",
    }
    base.update(overrides)
    return base


class TestVerifyLead(unittest.TestCase):
    """verify_lead keeps stated facts and strips anything not in the transcript."""

    def test_all_stated_facts_are_kept(self):
        lead = verify_lead(_fields(), TRANSCRIPT)
        self.assertTrue(lead.proof_ok)
        self.assertEqual(lead.notes, [])
        self.assertEqual(lead.fields["callback_number"], "859-555-0142")

    def test_invented_number_is_removed(self):
        lead = verify_lead(_fields(callback_number="859-555-9999"), TRANSCRIPT)
        self.assertEqual(lead.fields["callback_number"], NOT_GIVEN)
        self.assertIn("859-555-9999", lead.notes[0])

    def test_invented_name_and_address_are_removed(self):
        lead = verify_lead(
            _fields(caller_name="Linda Smith", address_or_town="Florence, KY"), TRANSCRIPT
        )
        self.assertEqual(lead.fields["caller_name"], NOT_GIVEN)
        self.assertEqual(lead.fields["address_or_town"], NOT_GIVEN)
        self.assertEqual(len(lead.notes), 2)

    def test_fabricated_quote_fails_proof(self):
        lead = verify_lead(_fields(problem_quote="the basement is flooding badly"), TRANSCRIPT)
        self.assertFalse(lead.proof_ok)
        self.assertEqual(lead.fields["problem_quote"], NOT_GIVEN)

    def test_problem_without_quote_fails_proof(self):
        lead = verify_lead(_fields(problem_quote="not given"), TRANSCRIPT)
        self.assertFalse(lead.proof_ok)

    def test_no_problem_and_no_quote_passes(self):
        lead = verify_lead(_fields(problem="Not Given", problem_quote="NOT GIVEN"), TRANSCRIPT)
        self.assertTrue(lead.proof_ok)
        self.assertEqual(lead.fields["problem"], NOT_GIVEN)

    def test_not_given_values_are_not_flagged(self):
        lead = verify_lead(_fields(caller_name="Not given", callback_number=""), TRANSCRIPT)
        self.assertEqual(lead.fields["caller_name"], NOT_GIVEN)
        self.assertEqual(lead.fields["callback_number"], NOT_GIVEN)
        self.assertEqual(lead.notes, [])


class TestNumberInTranscript(unittest.TestCase):
    """Phone number matching handles spoken digits and rejects short fragments."""

    def test_spoken_digits_match(self):
        text = "It's eight five nine, five five five, zero one eight seven."
        self.assertTrue(number_in_transcript("(859) 555-0187", text))

    def test_spoken_number_from_model_matches(self):
        # Regression: a number the model copied in words was wrongly removed.
        text = "It's eight five nine, five five five, zero one eight seven."
        spoken = "eight five nine, five five five, zero one eight seven"
        self.assertTrue(number_in_transcript(spoken, text))

    def test_short_fragment_is_rejected(self):
        self.assertFalse(number_in_transcript("1420", TRANSCRIPT))


if __name__ == "__main__":
    unittest.main()
