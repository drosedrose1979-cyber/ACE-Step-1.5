"""Local lead summarizer for the David Rose LLC plumber line (Union, KY).

Reads call transcripts or voicemail text from ``calls/incoming/``, asks Claude to
pull out lead details, checks every name/number/address against the transcript,
and writes a short summary file to ``calls/summaries/``. Nothing is sent to
customers; output stays on local disk.
"""
