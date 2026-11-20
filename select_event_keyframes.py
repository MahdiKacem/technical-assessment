import json

from pipeline.database import (
    get_connection,
    initialize_database,
    persist_event_keyframes,
)
from pipeline.events.keyframe_context import (
    extract_event_frames,
    select_keyframes_for_events,
)


MATCH_ID = "El classico 2017"
DB_PATH = "data/artifacts/El classico 2017/match.db"
EVENTS_PATH = "data/artifacts/El classico 2017/signals/events.json"
KEYFRAMES_PATH = "data/artifacts/El classico 2017/index/keyframes.json"
OUTPUT_PATH = "data/artifacts/El classico 2017/signals/event_keyframes.json"
VIDEO_PATH = "data/input/Barcelona vs Real Madrid (2017).mp4"
FRAME_OUTPUT_DIR = "data/artifacts/El classico 2017/event_keyframes"


with open(EVENTS_PATH, "r", encoding="utf-8") as f:
    events = json.load(f)
with open(KEYFRAMES_PATH, "r", encoding="utf-8") as f:
    keyframes = json.load(f)

manifest = select_keyframes_for_events(events, keyframes)
manifest = extract_event_frames(
    VIDEO_PATH,
    manifest,
    FRAME_OUTPUT_DIR,
)

initialize_database(DB_PATH)
persist_event_keyframes(DB_PATH, MATCH_ID, manifest)

with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=4, ensure_ascii=False)

print(f"Selected keyframes for {len(manifest)} events.")
