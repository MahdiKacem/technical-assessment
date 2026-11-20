from pipeline.database import (
    get_connection,
    initialize_database,
    insert_match,
)
from pipeline.multimodal import (
    content_hash,
    cosine_similarity,
    persist_embedding,
    record_embedding_usage,
)


def test_persist_text_and_image_embeddings_with_cache(tmp_path):
    db_path = tmp_path / "match.db"
    initialize_database(str(db_path))

    with get_connection(str(db_path)) as connection:
        insert_match(
            connection,
            "test-match",
            "test.mp4",
            {"duration_seconds": 100.0},
        )

        text_result = persist_embedding(
            connection,
            "test-match",
            None,
            "transcription",
            "segment-1",
            20.0,
            "text",
            "test-multimodal",
            "v1",
            "Goal at minute 20",
            [1.0, 0.0],
        )
        repeat_result = persist_embedding(
            connection,
            "test-match",
            None,
            "transcription",
            "segment-1",
            20.0,
            "text",
            "test-multimodal",
            "v1",
            "Goal at minute 20",
            [1.0, 0.0],
        )
        image_result = persist_embedding(
            connection,
            "test-match",
            None,
            "keyframe",
            "keyframe-1",
            20.0,
            "image",
            "test-multimodal",
            "v1",
            b"fake-image-bytes",
            [1.0, 0.0],
        )

        usage_id = record_embedding_usage(
            connection,
            "test-match",
            "test-multimodal",
            "text_image",
            item_count=2,
            cache_hits=1,
            estimated_cost=0.001,
        )

        counts = (
            connection.execute(
                "SELECT COUNT(*) FROM multimodal_embeddings"
            ).fetchone()[0],
            connection.execute(
                "SELECT COUNT(*) FROM embedding_usage"
            ).fetchone()[0],
        )

    assert text_result["cache_hit"] is False
    assert repeat_result["cache_hit"] is True
    assert image_result["cache_hit"] is False
    assert counts == (2, 1)
    assert usage_id
    assert len(content_hash("test")) == 64
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0


def test_multimodal_documents_share_event_id(tmp_path):
    db_path = tmp_path / "match.db"
    initialize_database(str(db_path))

    with get_connection(str(db_path)) as connection:
        insert_match(
            connection,
            "test-match",
            "test.mp4",
            {"duration_seconds": 100.0},
        )
        connection.execute(
            """
            INSERT INTO events (
                event_id, match_id, event_type, timestamp,
                title, confidence, entities_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "test-match:red-card:40",
                "test-match",
                "red_card",
                40.0,
                "Red card",
                0.95,
                '{"resolution_status":"confirmed"}',
            ),
        )
        connection.execute(
            """
            INSERT INTO event_keyframes (
                event_keyframe_id, event_id, keyframe_id,
                timestamp, image_path, role
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "test-keyframe",
                "test-match:red-card:40",
                "keyframe-40",
                40.0,
                "event_keyframes/red-card/at_event.jpg",
                "at_event",
            ),
        )

        from pipeline.multimodal import get_event_keyframe_documents

        keyframes = get_event_keyframe_documents(
            connection,
            "test-match:red-card:40",
        )

    assert len(keyframes) == 1
    assert keyframes[0]["keyframe_id"] == "keyframe-40"
