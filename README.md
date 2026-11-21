# Imaginario AI technical assessment — football highlight pipeline

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -r requirements.txt
copy .env.example .env            # then fill in GEMINI_API_KEY and CLAUDE_API_KEY
```

FFmpeg/FFprobe must be on `PATH`. Inputs live in `data/input/` (match video and roster CSVs).

## Usage

Everything runs through `run.py`. The match ID and video path default to
`pipeline/config.py`; override with `--match-id` / `--video`.

```bash
# Indexing (run once before querying; each stage can be rerun alone)
python run.py index                       # all stages below, in order
python run.py ingest                      # metadata, audio, shots, windows, keyframes
python run.py rosters
python run.py audio                       # audio features + peaks
python run.py transcribe
python run.py scoreboard                  # OCR of the full match, every 2 s
python run.py events                      # candidates, fusion, event frames, search index
python run.py embed --limit 50            # Gemini embeddings (cache checked before each call)

# Querying
python run.py search "late goal" --semantic --type goal --limit 5
python run.py brief "60s vertical: all goals, best two near misses, no replays"

# Inspection: row counts, stage timings, LLM token usage and cost
python run.py status
```

Every stage run is timed into the `stage_runs` table, and every LLM call
(including cache hits and failures) is logged to `llm_usage`.

## Layout

```text
run.py                    CLI entry point
pipeline/
  config.py               match inputs and artifact paths
  stages.py               one function per stage: compute -> JSON artifact -> SQLite, timed
  database.py             schema and persistence
  ingestion/              metadata, audio, shots, windows, keyframes, rosters
  analysis/               audio features/peaks, transcription, scoreboard OCR + parsing
  events/                 per-signal event candidates, fusion, event keyframes
  briefs/                 creative brief schema + Claude interpretation
  embeddings.py           Gemini embedding client
  multimodal.py           embedding documents, cache, usage
  search.py               hybrid (semantic + FTS + confidence) event search
data/artifacts/<match>/   match.db, index/, signals/, audio/, event_keyframes/
```
