from pipeline.database import (get_connection,initialize_database,insert_match,)


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
