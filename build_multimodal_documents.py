import json

from pipeline.database import get_connection, initialize_database
from pipeline.multimodal import (
    build_event_text_document,
    build_transcript_window_document,
    get_event_keyframe_documents,
)


MATCH_ID = "El classico 2017"
DB_PATH = "data/artifacts/El classico 2017/match.db"
OUTPUT_PATH = "data/artifacts/El classico 2017/signals/multimodal_documents.json"


initialize_database(DB_PATH)

documents = []
with get_connection(DB_PATH) as connection:
    event_rows = connection.execute(
        """
        SELECT event_id
        FROM events
        WHERE match_id = ?
        ORDER BY timestamp, event_id
        """,
        (MATCH_ID,),
    ).fetchall()

    for event_row in event_rows:
        event_id = event_row["event_id"]
        documents.append(
            {
                "event_id": event_id,
                "modality": "text",
                "source_type": "event",
                "source_id": event_id,
                "content": build_event_text_document(connection, event_id),
            }
        )
        documents.append(
            {
                "event_id": event_id,
                "modality": "text",
                "source_type": "transcript_window",
                "source_id": f"{event_id}:transcript-window",
                "content": build_transcript_window_document(connection, event_id),
            }
        )
        for keyframe in get_event_keyframe_documents(connection, event_id):
            documents.append(
                {
                    "event_id": event_id,
                    "modality": "image",
                    "source_type": "keyframe",
                    "source_id": keyframe["keyframe_id"],
                    "timestamp": keyframe["timestamp"],
                    "image_path": keyframe["image_path"],
                    "content": None,
                }
            )

with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    json.dump(documents, f, indent=4, ensure_ascii=False)

print(f"Built {len(documents)} multimodal documents.")
