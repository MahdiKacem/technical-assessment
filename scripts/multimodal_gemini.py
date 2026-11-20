import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
from google import genai
from google.genai import types

from pipeline.database import get_connection, initialize_database
from pipeline.multimodal import (
    persist_embedding,
    record_embedding_usage,
)


MATCH_ID = "El classico 2017"
DB_PATH = "data/artifacts/El classico 2017/match.db"
ARTIFACT_DIR = Path("data/artifacts/El classico 2017")
MODEL_NAME = "gemini-embedding-2"
MODEL_VERSION = "v1"
MAX_ITEMS = 8


load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise RuntimeError("GEMINI_API_KEY is not configured.")

initialize_database(DB_PATH)
client = genai.Client(api_key=api_key)

text_items = [
    {
        "source_type": "event",
        "source_id": "El classico 2017:red_card:5187.25",
        "timestamp": 5187.25,
        "content": (
            "Red card for Sergio Ramos at Real Madrid against Barcelona "
            "with the scoreboard showing RMA 1 2 BAR."
        ),
    },
    {
        "source_type": "event",
        "source_id": "El classico 2017:goal:1955.25",
        "timestamp": 1955.25,
        "content": (
            "Goal at 27:52: Real Madrid scored to make RMA 1 0 Barcelona."
        ),
    },
]

image_items = [
    {
        "source_type": "keyframe",
        "source_id": "El classico 2017:red_card:5187.25:at_event",
        "timestamp": 5187.25,
        "path": (
            ARTIFACT_DIR
            / "event_keyframes"
            / "El_classico_2017_red_card_5187.25"
            / "at_event.jpg"
        ),
    },
    {
        "source_type": "keyframe",
        "source_id": "El classico 2017:goal:1955.25:at_event",
        "timestamp": 1955.25,
        "path": (
            ARTIFACT_DIR
            / "event_keyframes"
            / "El_classico_2017_goal_1955.25"
            / "at_event.jpg"
        ),
    },
]

started = time.time()
cache_hits = 0
persisted = 0

with get_connection(DB_PATH) as connection:
    for item in text_items[:MAX_ITEMS]:
        result = client.models.embed_content(
            model=MODEL_NAME,
            contents=(
                "task: search result | title: none | "
                f"text: {item['content']}"
            ),
        )
        vector = list(result.embeddings[0].values)
        canonical_event = connection.execute(
            "SELECT event_id FROM events WHERE event_id = ?",
            (item["source_id"],),
        ).fetchone()
        save_result = persist_embedding(
            connection,
            MATCH_ID,
            canonical_event["event_id"] if canonical_event else None,
            item["source_type"],
            item["source_id"],
            item["timestamp"],
            "text",
            MODEL_NAME,
            MODEL_VERSION,
            item["content"],
            vector,
        )
        cache_hits += 1 if save_result["cache_hit"] else 0
        persisted += 0 if save_result["cache_hit"] else 1

    for item in image_items[:MAX_ITEMS]:
        if not item["path"].exists():
            continue
        image_bytes = item["path"].read_bytes()
        result = client.models.embed_content(
            model=MODEL_NAME,
            contents=[
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type="image/jpeg",
                )
            ],
        )
        vector = list(result.embeddings[0].values)
        canonical_event = connection.execute(
            """
            SELECT event_id
            FROM events
            WHERE event_id = (
                SELECT event_id
                FROM event_keyframes
                WHERE keyframe_id = ?
                LIMIT 1
            )
            """,
            (item["source_id"],),
        ).fetchone()
        save_result = persist_embedding(
            connection,
            MATCH_ID,
            canonical_event["event_id"] if canonical_event else None,
            item["source_type"],
            item["source_id"],
            item["timestamp"],
            "image",
            MODEL_NAME,
            MODEL_VERSION,
            image_bytes,
            vector,
        )
        cache_hits += 1 if save_result["cache_hit"] else 0
        persisted += 0 if save_result["cache_hit"] else 1

    latency_ms = int((time.time() - started) * 1000)
    record_embedding_usage(
        connection,
        MATCH_ID,
        MODEL_NAME,
        "text_image",
        item_count=min(MAX_ITEMS, len(text_items) + len(image_items)),
        cache_hits=cache_hits,
        latency_ms=latency_ms,
        success=True,
    )

print(f"Persisted {persisted} new embeddings.")
