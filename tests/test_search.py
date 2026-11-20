from pipeline.database import (
    get_connection,
    initialize_database,
    insert_match,
    insert_events,
)
from pipeline.search import build_event_search_index, search_events


def prepare_search_database(tmp_path):
    db_path = tmp_path / "match.db"
    initialize_database(str(db_path))

    with get_connection(str(db_path)) as connection:
        insert_match(
            connection,
            "test-match",
            "test.mp4",
            {"duration_seconds": 100.0},
        )
        insert_events(
            connection,
            "test-match",
            [
                {
                    "event_id": "test-match:goal:20",
                    "event_type": "goal",
                    "timestamp": 20.0,
                    "title": "First goal",
                    "description": "The away team scored.",
                    "confidence": 0.95,
                    "entities": {
                        "resolution_status": "confirmed",
                        "team": "away",
                        "player": "John Doe",
                    },
                    "evidence": [
                        {
                            "evidence_id": "goal-scoreboard",
                            "source_type": "scoreboard",
                            "source_id": "score-20",
                            "source_timestamp": 20.0,
                            "source_value": "0-1",
                            "confidence": 0.95,
                            "weight": 1.0,
                            "details": {"relation": "support"},
                        }
                    ],
                },
                {
                    "event_id": "test-match:red-card:40",
                    "event_type": "red_card",
                    "timestamp": 40.0,
                    "title": "Red card",
                    "description": "Straight red card.",
                    "confidence": 0.90,
                    "entities": {
                        "resolution_status": "confirmed",
                        "team": "home",
                        "player": "Jane Roe",
                    },
                    "evidence": [],
                },
            ],
        )
        count = build_event_search_index(connection, "test-match")

    return db_path, count


def test_build_and_search_confirmed_goals(tmp_path):
    db_path, count = prepare_search_database(tmp_path)

    with get_connection(str(db_path)) as connection:
        results = search_events(
            connection,
            "test-match",
            query="goal",
            event_types=["goal"],
            statuses=["confirmed"],
            limit=5,
        )

    assert count == 2
    assert len(results) == 1
    assert results[0]["event_id"] == "test-match:goal:20"
    assert results[0]["entities"]["player"] == "John Doe"
    assert results[0]["evidence"][0]["source_type"] == "scoreboard"


def test_search_supports_time_and_status_filters(tmp_path):
    db_path, _ = prepare_search_database(tmp_path)

    with get_connection(str(db_path)) as connection:
        results = search_events(
            connection,
            "test-match",
            event_types=["red_card"],
            statuses=["confirmed"],
            start_time=30.0,
            end_time=50.0,
            limit=5,
        )

    assert len(results) == 1
    assert results[0]["event_type"] == "red_card"


def test_semantic_search_reranks_filtered_candidates(tmp_path):
    db_path, _ = prepare_search_database(tmp_path)

    with get_connection(str(db_path)) as connection:
        connection.execute(
            """
            INSERT INTO multimodal_embeddings (
                embedding_id, match_id, event_id, source_type, source_id,
                timestamp, modality, model_name, model_version,
                content_hash, vector_json, dimensions
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "goal-vector",
                "test-match",
                "test-match:goal:20",
                "event",
                "test-match:goal:20",
                20.0,
                "text",
                "test-multimodal",
                "v1",
                "goal-hash",
                "[1.0,0.0]",
                2,
            ),
        )
        connection.execute(
            """
            INSERT INTO multimodal_embeddings (
                embedding_id, match_id, event_id, source_type, source_id,
                timestamp, modality, model_name, model_version,
                content_hash, vector_json, dimensions
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "red-vector",
                "test-match",
                "test-match:red-card:40",
                "event",
                "test-match:red-card:40",
                40.0,
                "text",
                "test-multimodal",
                "v1",
                "red-hash",
                "[0.0,1.0]",
                2,
            ),
        )
        results = search_events(
            connection,
            "test-match",
            query="goal",
            query_vector=[1.0, 0.0],
            statuses=["confirmed"],
            limit=5,
        )

    assert results[0]["event_id"] == "test-match:goal:20"
    assert results[0]["semantic_score"] > results[1]["semantic_score"]
