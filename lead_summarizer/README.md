# Lead summarizer: David Rose LLC plumber line (Union, KY)

This tool runs on your own computer and is for testing only. It reads call transcripts and
voicemail text, then writes a short lead summary for each one. It does not email, text,
call, or post anything. You read the summaries and decide who to call back.

## What it does

- **Input:** `.txt` files in `lead_summarizer/calls/incoming/`
- **Output:** `lead_summarizer/calls/summaries/<file>_summary.txt`, with these fields: caller
  name, callback number, address or town, problem plus one quote from the transcript as proof,
  urgency (emergency / today / this week / quote only / not given), and whether the caller
  asked for a human callback.
- **Run log:** `lead_summarizer/logs/run_log.txt`, one line per file in the form
  `time | file | PASS/FAIL | detail`.
- **Spend ledger:** `lead_summarizer/logs/spend_ledger.json`, the dollars spent each day.

## Guardrails

- **No guessing.** The tool checks every name, number, and address against the transcript.
  If it can't find one there, it changes that field to `not given` and writes the removed
  value under "Checks" so you can look at it yourself. If the proof quote isn't word for word
  in the transcript, that file is marked FAIL.
- **Daily cost cap: $2.00.** Before each API call, the tool works out the most that call
  could cost. If that amount plus what was already spent today would pass the cap, the tool
  stops and prints a warning. After each call, it adds the real cost to the ledger.
- **API key.** The key is read only from the `ANTHROPIC_API_KEY` environment variable. It is
  never printed, logged, or written to a file. `.env` is listed in `.gitignore`.
- **Customer data stays out of git.** Real transcripts, summaries, and logs are gitignored.
  Only the three fake `sample_*.txt` files are tracked.

## Run it (Windows PowerShell, from the repository root)

```powershell
pip install -r lead_summarizer\requirements.txt   # Anthropic SDK only
$env:ANTHROPIC_API_KEY = "<your key>"           # type this in your own terminal; lasts this window only
python -m lead_summarizer                        # summarizes new files
python -m lead_summarizer --force                # redoes files that already have a summary
```

Exit codes: `0` all passed, `1` at least one file failed, `2` the run stopped early (key
missing or rejected, or the cost cap was reached).

## Settings (`config.py`)

| Setting | Default | Notes |
| --- | --- | --- |
| `DEFAULT_MODEL_NAME` | `claude-opus-5-5` | Set the `LEAD_SUMMARIZER_MODEL` environment variable to use a different model without editing code |
| `EFFORT` | `low` | Keeps thinking tokens (and cost) low; this is a simple extraction job |
| `DAILY_COST_CAP_USD` | `2.00` | Counted in your computer's local time |
| `USE_REFUSAL_FALLBACK` | `True` | If the model declines, the API retries on Anthropic's fallback model. That retry is included in the cost estimate |
| `PRICES_PER_MTOK` | see file | A model that isn't in this table is refused, so its cost can't go unestimated |

## Limits to know

- The cap only counts calls made by this tool. Other apps using the same key are not
  counted, so set a spend limit in the Anthropic Console as the real backstop.
- The worst-case estimate is deliberately high, so a run stops a little before $2.00 of
  actual spend.

## Tests

```bash
python -m unittest discover -s lead_summarizer -t . -p "test_*.py"
```
