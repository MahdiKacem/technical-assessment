import json

from pipeline.database import initialize_database, persist_audio


MATCH_ID = "El classico 2017"
DB_PATH = "data/artifacts/El classico 2017/match.db"
ARTIFACT_DIR = "data/artifacts/El classico 2017/signals"

with open(f"{ARTIFACT_DIR}/audio_features.json", "r", encoding="utf-8") as f:
    features = json.load(f)

with open(f"{ARTIFACT_DIR}/audio_peaks.json", "r", encoding="utf-8") as f:
    peaks = json.load(f)

initialize_database(DB_PATH)
persist_audio(DB_PATH, MATCH_ID, features, peaks)

print(f"Inserted/updated {len(features)} audio features.")
print(f"Inserted/updated {len(peaks)} audio peaks.")
