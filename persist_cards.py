import json

from pipeline.database import initialize_database, persist_card_events


MATCH_ID = "El classico 2017"
DB_PATH = "data/artifacts/El classico 2017/match.db"
PARSED_PATH = "data/artifacts/El classico 2017/signals/red_card_parsed.json"

with open(PARSED_PATH, "r", encoding="utf-8") as f:
    parsed_observations = json.load(f)

initialize_database(DB_PATH)
persist_card_events(DB_PATH, MATCH_ID, parsed_observations)

print("Inserted/updated red card events.")
