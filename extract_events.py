import json

from pipeline.database import (
    get_connection,
    initialize_database,
    persist_events,
)
from pipeline.events import (
    extract_scoreboard_events,
    extract_audio_events,
    extract_transcription_events,
)
from pipeline.events.clustering import cluster_events


MATCH_ID = "El classico 2017"
DB_PATH = "data/artifacts/El classico 2017/match.db"
OUTPUT_PATH = "data/artifacts/El classico 2017/signals/events.json"


initialize_database(DB_PATH)

with get_connection(DB_PATH) as connection:
    events = []
    events.extend(extract_scoreboard_events(connection, MATCH_ID))
    events.extend(extract_audio_events(connection, MATCH_ID))
    events.extend(extract_transcription_events(connection, MATCH_ID))
    events.sort(key=lambda event: event["timestamp"])
    events = cluster_events(events)

persist_events(DB_PATH, MATCH_ID, events)

with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    json.dump(events, f, indent=4, ensure_ascii=False)

print(f"Extracted {len(events)} events.")
