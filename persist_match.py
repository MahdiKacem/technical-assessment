import json

from pipeline.database import (
    initialize_database,
    get_connection,
    persist_ingestion,
)

MATCH_ID = "El classico 2017"
VIDEO_PATH = "data/input/Barcelona vs Real Madrid (2017).mp4"

ARTIFACT_DIR = f"data/artifacts/{MATCH_ID}"
INDEX_DIR = f"{ARTIFACT_DIR}/index"
DB_PATH = f"{ARTIFACT_DIR}/match.db"


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# Load outputs from the previous pipeline stages.
metadata = load_json(f"{ARTIFACT_DIR}/video_metadata.json")
shots = load_json(f"{INDEX_DIR}/shots.json")
windows = load_json(f"{INDEX_DIR}/windows.json")
keyframes = load_json(f"{INDEX_DIR}/keyframes.json")


# Initialize and persist.
initialize_database(DB_PATH)

persist_ingestion(
    db_path=DB_PATH,
    match_id=MATCH_ID,
    video_path=VIDEO_PATH,
    metadata=metadata,
    shots=shots,
    windows=windows,
    keyframes=keyframes,
)


# Verify inserted record counts.
with get_connection(DB_PATH) as connection:
    for table in ["matches", "shots", "windows", "keyframes"]:
        count = connection.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]

        print(f"{table}: {count}")
