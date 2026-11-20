import json

from pipeline.database import initialize_database, persist_scoreboard


MATCH_ID = "El classico 2017"
DB_PATH = "data/artifacts/El classico 2017/match.db"
OCR_PATH = "data/artifacts/El classico 2017/signals/scoreboard_ocr.json"

with open(OCR_PATH, "r", encoding="utf-8") as f:
    observations = json.load(f)

initialize_database(DB_PATH)
persist_scoreboard(DB_PATH, MATCH_ID, observations)

print(f"Inserted/updated {len(observations)} scoreboard OCR observations.")
