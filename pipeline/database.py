import sqlite3
from pathlib import Path
import json


def get_connection(db_path: str) -> sqlite3.Connection:
    """Create a SQLite connection with foreign-key support."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    return connection


def initialize_database(db_path: str) -> None:
    """Create all initial database tables."""

    schema = """
    CREATE TABLE IF NOT EXISTS matches (
        match_id TEXT PRIMARY KEY,
        source_video TEXT NOT NULL,
        duration_seconds REAL NOT NULL,
        width INTEGER,
        height INTEGER,
        video_codec TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS shots (
        shot_id TEXT PRIMARY KEY,
        match_id TEXT NOT NULL,
        start_time REAL NOT NULL,
        end_time REAL NOT NULL,
        duration REAL NOT NULL,

        FOREIGN KEY (match_id)
            REFERENCES matches(match_id)
            ON DELETE CASCADE,

        CHECK (end_time > start_time)
    );

    CREATE TABLE IF NOT EXISTS windows (
        window_id TEXT PRIMARY KEY,
        shot_id TEXT NOT NULL,
        start_time REAL NOT NULL,
        end_time REAL NOT NULL,
        duration REAL NOT NULL,

        FOREIGN KEY (shot_id)
            REFERENCES shots(shot_id)
            ON DELETE CASCADE,

        CHECK (end_time > start_time)
    );

    CREATE TABLE IF NOT EXISTS keyframes (
        keyframe_id TEXT PRIMARY KEY,
        window_id TEXT NOT NULL,
        timestamp REAL NOT NULL,
        image_path TEXT NOT NULL,

        FOREIGN KEY (window_id)
            REFERENCES windows(window_id)
            ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS transcriptions (
        segment_id TEXT PRIMARY KEY,
        match_id TEXT NOT NULL,
        start_time REAL NOT NULL,
        end_time REAL NOT NULL,
        text TEXT NOT NULL,

        FOREIGN KEY (match_id)
            REFERENCES matches(match_id)
            ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_transcriptions_match
        ON transcriptions(match_id);

    CREATE INDEX IF NOT EXISTS idx_transcriptions_time
        ON transcriptions(match_id, start_time, end_time);

    CREATE INDEX IF NOT EXISTS idx_shots_match
        ON shots(match_id);

    CREATE INDEX IF NOT EXISTS idx_windows_shot
        ON windows(shot_id);

    CREATE INDEX IF NOT EXISTS idx_keyframes_window
        ON keyframes(window_id);

    CREATE INDEX IF NOT EXISTS idx_keyframes_timestamp
        ON keyframes(timestamp);
    """

    with get_connection(db_path) as connection:
        connection.executescript(schema)

    print(f"Database initialized: {db_path}")




def insert_match(connection, match_id: str, video_path: str, metadata: dict):
    video = metadata.get("video") or {}

    connection.execute(
        """
        INSERT INTO matches (
            match_id,
            source_video,
            duration_seconds,
            width,
            height,
            video_codec
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(match_id) DO UPDATE SET
            source_video = excluded.source_video,
            duration_seconds = excluded.duration_seconds,
            width = excluded.width,
            height = excluded.height,
            video_codec = excluded.video_codec
        """,
        (
            match_id,
            video_path,
            metadata["duration_seconds"],
            video.get("width", metadata.get("width")),
            video.get("height", metadata.get("height")),
            video.get("codec", metadata.get("video_codec")),
        ),
    )


def insert_shots(connection, match_id: str, shots: list[dict]):
    connection.executemany(
        """
        INSERT INTO shots (
            shot_id, match_id, start_time, end_time, duration
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(shot_id) DO UPDATE SET
            match_id = excluded.match_id,
            start_time = excluded.start_time,
            end_time = excluded.end_time,
            duration = excluded.duration
        """,
        [
            (
                shot["shot_id"],
                match_id,
                shot["start_time"],
                shot["end_time"],
                shot["duration"],
            )
            for shot in shots
        ],
    )


def insert_windows(connection, windows: list[dict]):
    connection.executemany(
        """
        INSERT INTO windows (
            window_id, shot_id, start_time, end_time, duration
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(window_id) DO UPDATE SET
            shot_id = excluded.shot_id,
            start_time = excluded.start_time,
            end_time = excluded.end_time,
            duration = excluded.duration
        """,
        [
            (
                window["window_id"],
                window["shot_id"],
                window["start_time"],
                window["end_time"],
                window["duration"],
            )
            for window in windows
        ],
    )


def insert_keyframes(connection, keyframes: list[dict]):
    connection.executemany(
        """
        INSERT INTO keyframes (
            keyframe_id, window_id, timestamp, image_path
        )
        VALUES (?, ?, ?, ?)
        ON CONFLICT(keyframe_id) DO UPDATE SET
            window_id = excluded.window_id,
            timestamp = excluded.timestamp,
            image_path = excluded.image_path
        """,
        [
            (
                keyframe["keyframe_id"],
                keyframe["window_id"],
                keyframe["timestamp"],
                keyframe["image_path"],
            )
            for keyframe in keyframes
        ],
    )
def insert_transcriptions(
    connection,
    match_id: str,
    segments: list[dict],
) -> None:

    rows = [
        (
            segment["segment_id"],
            match_id,
            segment["start_time"],
            segment["end_time"],
            segment["text"],
        )
        for segment in segments
    ]

    connection.executemany(
        """
        INSERT INTO transcriptions (
            segment_id,
            match_id,
            start_time,
            end_time,
            text
        )
        VALUES (?, ?, ?, ?, ?)

        ON CONFLICT(segment_id)
        DO UPDATE SET
            match_id = excluded.match_id,
            start_time = excluded.start_time,
            end_time = excluded.end_time,
            text = excluded.text
        """,
        rows,
    )


def persist_ingestion(
    db_path: str,
    match_id: str,
    video_path: str,
    metadata: dict,
    shots: list[dict],
    windows: list[dict],
    keyframes: list[dict],
):
    from pipeline.database import get_connection

    with get_connection(db_path) as connection:
        # One transaction for the complete ingestion result.
        insert_match(connection, match_id, video_path, metadata)
        insert_shots(connection, match_id, shots)
        insert_windows(connection, windows)
        insert_keyframes(connection, keyframes)

    print(f"Successfully persisted ingestion for {match_id}")

def persist_transcription(
    db_path: str,
    match_id: str,
    segments: list[dict],
) -> None:

    with get_connection(db_path) as connection:
        insert_transcriptions(
            connection,
            match_id,
            segments,
        )