import hashlib
import json
from pathlib import Path


def content_hash(content: str | bytes) -> str:
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def build_event_text_document(connection, event_id: str) -> str:
    event = connection.execute(
        """
        SELECT event_id, match_id, event_type, timestamp, title,
               description, confidence, entities_json
        FROM events
        WHERE event_id = ?
        """,
        (event_id,),
    ).fetchone()
    if event is None:
        raise ValueError(f"Unknown event: {event_id}")

    evidence_rows = connection.execute(
        """
        SELECT source_type, source_id, source_timestamp,
               source_value, confidence, weight
        FROM event_evidence
        WHERE event_id = ?
        ORDER BY weight DESC, source_timestamp, evidence_id
        """,
        (event_id,),
    ).fetchall()

    evidence_text = " ".join(
        f"{row['source_type']} {row['source_value'] or ''}".strip()
        for row in evidence_rows[:5]
    )
    entities = event["entities_json"] or "{}"

    return " | ".join(
        part for part in (
            f"event_type={event['event_type']}",
            f"title={event['title'] or ''}",
            f"description={event['description'] or ''}",
            f"timestamp={event['timestamp']}",
            f"entities={entities}",
            f"evidence={evidence_text}",
        )
        if part
    )


def build_transcript_window_document(
    connection,
    event_id: str,
    before_seconds: float = 30.0,
    after_seconds: float = 30.0,
) -> str:
    event = connection.execute(
        "SELECT match_id, timestamp FROM events WHERE event_id = ?",
        (event_id,),
    ).fetchone()
    if event is None:
        raise ValueError(f"Unknown event: {event_id}")

    start = event["timestamp"] - before_seconds
    end = event["timestamp"] + after_seconds
    segments = connection.execute(
        """
        SELECT segment_id, start_time, end_time, text
        FROM transcriptions
        WHERE match_id = ?
          AND end_time >= ?
          AND start_time <= ?
        ORDER BY start_time
        LIMIT 5
        """,
        (event["match_id"], start, end),
    ).fetchall()

    return " | ".join(
        f"{row['segment_id']}={row['text']}"
        for row in segments
    )


def get_event_keyframe_documents(connection, event_id: str) -> list[dict]:
    rows = connection.execute(
        """
        SELECT event_keyframe_id, keyframe_id, timestamp,
               image_path, role
        FROM event_keyframes
        WHERE event_id = ?
        ORDER BY timestamp
        """,
        (event_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def find_cached_embedding(
    connection,
    source_type: str,
    source_id: str,
    model_name: str,
    model_version: str | None,
    content: str | bytes,
) -> str | None:
    row = connection.execute(
        """
        SELECT embedding_id FROM multimodal_embeddings
        WHERE model_name = ? AND model_version IS ? AND content_hash = ?
          AND source_type = ? AND source_id = ?
        """,
        (model_name, model_version, content_hash(content), source_type, source_id),
    ).fetchone()
    return row["embedding_id"] if row else None


def persist_embedding(
    connection,
    match_id: str,
    event_id: str | None,
    source_type: str,
    source_id: str,
    timestamp: float | None,
    modality: str,
    model_name: str,
    model_version: str | None,
    content: str | bytes,
    vector: list[float],
    vector_store_id: str | None = None,
) -> dict:
    if modality not in {"text", "image"}:
        raise ValueError("modality must be 'text' or 'image'")
    if not vector:
        raise ValueError("vector must not be empty")

    text_hash = content_hash(content)
    embedding_id = (
        f"{match_id}:embedding:{source_type}:{source_id}:"
        f"{modality}:{model_name}:{model_version or 'default'}:{text_hash[:16]}"
    )

    existing = connection.execute(
        """
        SELECT embedding_id
        FROM multimodal_embeddings
        WHERE model_name = ?
          AND model_version IS ?
          AND content_hash = ?
          AND source_type = ?
          AND source_id = ?
        """,
        (model_name, model_version, text_hash, source_type, source_id),
    ).fetchone()
    if existing:
        return {"embedding_id": existing["embedding_id"], "cache_hit": True}

    connection.execute(
        """
        INSERT INTO multimodal_embeddings (
            embedding_id,
            match_id,
            event_id,
            source_type,
            source_id,
            timestamp,
            modality,
            model_name,
            model_version,
            content_hash,
            vector_store_id,
            vector_json,
            dimensions
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            embedding_id,
            match_id,
            event_id,
            source_type,
            source_id,
            timestamp,
            modality,
            model_name,
            model_version,
            text_hash,
            vector_store_id,
            json.dumps(vector),
            len(vector),
        ),
    )
    return {"embedding_id": embedding_id, "cache_hit": False}


def record_embedding_usage(
    connection,
    match_id: str,
    model_name: str,
    modality: str,
    item_count: int,
    cache_hits: int = 0,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    estimated_cost: float | None = None,
    latency_ms: int | None = None,
    success: bool = True,
) -> str:
    import time

    usage_id = f"{match_id}:embedding-usage:{model_name}:{modality}:{time.time_ns()}"
    connection.execute(
        """
        INSERT INTO embedding_usage (
            usage_id,
            match_id,
            model_name,
            modality,
            item_count,
            cache_hits,
            input_tokens,
            output_tokens,
            estimated_cost,
            latency_ms,
            success
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            usage_id,
            match_id,
            model_name,
            modality,
            item_count,
            cache_hits,
            input_tokens,
            output_tokens,
            estimated_cost,
            latency_ms,
            1 if success else 0,
        ),
    )
    return usage_id


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = sum(a * a for a in left) ** 0.5
    right_norm = sum(b * b for b in right) ** 0.5
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)
