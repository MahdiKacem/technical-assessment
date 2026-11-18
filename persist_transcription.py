import json

from pipeline.database import initialize_database, persist_transcription

MATCH_ID = "El classico 2017"

DB_PATH = "data/artifacts/El classico 2017/match.db"

TRANSCRIPTION_PATH = (
    "data/artifacts/El classico 2017/signals/transcription.json"
)

with open(TRANSCRIPTION_PATH, "r", encoding="utf-8") as f:
    segments = json.load(f)

initialize_database(DB_PATH)

persist_transcription(
    DB_PATH,
    MATCH_ID,
    segments,
)

print(f"Inserted/updated {len(segments)} transcription segments.")