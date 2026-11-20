from pipeline.database import (
    get_connection,
    initialize_database,
    insert_match,
    insert_scoreboard_observations,
    insert_audio_features,
    insert_audio_peaks,
    insert_card_events,
    insert_event_keyframes,
    insert_events,
)


def test_insert_match_reads_nested_video_metadata(tmp_path):
    db_path = tmp_path / "match.db"
    initialize_database(str(db_path))

    metadata = {
        "duration_seconds": 6197.730975,
        "video": {
            "codec": "h264",
            "width": 1280,
            "height": 720,
        },
    }

    with get_connection(str(db_path)) as connection:
        insert_match(
            connection,
            "El classico 2017",
            "data/input/Barcelona vs Real Madrid (2017).mp4",
            metadata,
        )
        row = connection.execute(
            """
            SELECT source_video, duration_seconds, width, height, video_codec
            FROM matches
            WHERE match_id = ?
            """,
            ("El classico 2017",),
        ).fetchone()

    assert row["source_video"] == "data/input/Barcelona vs Real Madrid (2017).mp4"
    assert row["duration_seconds"] == 6197.730975
    assert row["width"] == 1280
    assert row["height"] == 720
    assert row["video_codec"] == "h264"


def test_insert_scoreboard_observations_persists_parsed_scores(tmp_path):
    db_path = tmp_path / "match.db"
    initialize_database(str(db_path))

    observations = [
        {
            "timestamp": 1955.25,
            "text": "27.52",
            "confidence": 0.98,
            "bbox": [[106, 42], [184, 42], [184, 72], [106, 72]],
        },
        {
            "timestamp": 1955.25,
            "text": "RMA",
            "confidence": 0.99,
            "bbox": [[197, 43], [247, 43], [247, 63], [197, 63]],
        },
        {
            "timestamp": 1955.25,
            "text": "1 0",
            "confidence": 0.74,
            "bbox": [[196, 43], [249, 43], [249, 67], [196, 67]],
        },
        {
            "timestamp": 1955.25,
            "text": "BAR",
            "confidence": 0.95,
            "bbox": [[339, 43], [387, 43], [387, 63], [339, 63]],
        },
    ]

    with get_connection(str(db_path)) as connection:
        insert_match(
            connection,
            "El classico 2017",
            "data/input/Barcelona vs Real Madrid (2017).mp4",
            {"duration_seconds": 6197.730975},
        )
        insert_scoreboard_observations(
            connection,
            "El classico 2017",
            observations,
        )
        row = connection.execute(
            """
            SELECT timestamp, raw_text, home_score, away_score,
                   match_time, confidence, bbox_json
            FROM scoreboard_observations
            WHERE match_id = ?
            """,
            ("El classico 2017",),
        ).fetchone()

    assert row["timestamp"] == 1955.25
    assert row["home_score"] == 1
    assert row["away_score"] == 0
    assert "1 0" in row["raw_text"]
    assert row["match_time"] is None
    assert row["confidence"] == 0.915
    assert len(__import__("json").loads(row["bbox_json"])) == 4


def test_insert_audio_features_and_peaks(tmp_path):
    db_path = tmp_path / "match.db"
    initialize_database(str(db_path))

    features = [
        {
            "start_time": 0.0,
            "end_time": 2.0,
            "center_time": 1.0,
            "rms": 0.12,
            "zero_crossing_rate": 0.08,
            "spectral_centroid": 1400.0,
        }
    ]
    peaks = [
        {
            "peak_id": "audio_peak_00001",
            "timestamp": 372.0,
            "rms": 0.109,
            "z_score": 2.52,
        }
    ]

    with get_connection(str(db_path)) as connection:
        insert_match(
            connection,
            "El classico 2017",
            "data/input/Barcelona vs Real Madrid (2017).mp4",
            {"duration_seconds": 6197.730975},
        )
        insert_audio_features(connection, "El classico 2017", features)
        insert_audio_peaks(connection, "El classico 2017", peaks)

        feature = connection.execute(
            "SELECT * FROM audio_features WHERE match_id = ?",
            ("El classico 2017",),
        ).fetchone()
        peak = connection.execute(
            "SELECT * FROM audio_peaks WHERE match_id = ?",
            ("El classico 2017",),
        ).fetchone()

    assert feature["center_time"] == 1.0
    assert feature["rms"] == 0.12
    assert peak["peak_id"] == "audio_peak_00001"
    assert peak["timestamp"] == 372.0


def test_insert_card_events_deduplicates_red_card(tmp_path):
    db_path = tmp_path / "match.db"
    initialize_database(str(db_path))

    parsed_observations = [
        {
            "timestamp": 5187.25,
            "card_candidates": [
                {"type": "red", "team": "RMA", "player": "SERGIO RAMOS"}
            ],
        },
        {
            "timestamp": 5187.5,
            "card_candidates": [
                {"type": "red", "team": "RMA", "player": "SERGIO RAMOS"}
            ],
        },
    ]

    with get_connection(str(db_path)) as connection:
        insert_match(
            connection,
            "El classico 2017",
            "data/input/Barcelona vs Real Madrid (2017).mp4",
            {"duration_seconds": 6197.730975},
        )
        insert_card_events(
            connection,
            "El classico 2017",
            parsed_observations,
        )
        row = connection.execute(
            """
            SELECT timestamp, card_type, team, player_name
            FROM card_events
            WHERE match_id = ?
            """,
            ("El classico 2017",),
        ).fetchone()
        count = connection.execute(
            "SELECT COUNT(*) FROM card_events WHERE match_id = ?",
            ("El classico 2017",),
        ).fetchone()[0]

    assert count == 1
    assert row["timestamp"] == 5187.25
    assert row["card_type"] == "red"
    assert row["team"] == "RMA"
    assert row["player_name"] == "SERGIO RAMOS"


def test_insert_event_keyframes(tmp_path):
    db_path = tmp_path / "match.db"
    initialize_database(str(db_path))

    event = {
        "event_id": "test:goal:100",
        "event_type": "goal",
        "timestamp": 100.0,
        "confidence": 0.95,
        "entities": {"resolution_status": "confirmed"},
        "evidence": [],
    }
    manifest = [
        {
            "event_id": event["event_id"],
            "keyframes": [
                {
                    "keyframe_id": "keyframe_0001",
                    "timestamp": 90.0,
                    "image_path": "keyframes/keyframe_0001.jpg",
                    "role": "before",
                }
            ],
        }
    ]

    with get_connection(str(db_path)) as connection:
        insert_match(
            connection,
            "test-match",
            "test.mp4",
            {"duration_seconds": 100.0},
        )
        insert_events(connection, "test-match", [event])
        insert_event_keyframes(connection, "test-match", manifest)
        row = connection.execute(
            """
            SELECT keyframe_id, timestamp, image_path, role
            FROM event_keyframes
            WHERE event_id = ?
            """,
            (event["event_id"],),
        ).fetchone()

    assert row["keyframe_id"] == "keyframe_0001"
    assert row["timestamp"] == 90.0
    assert row["role"] == "before"
