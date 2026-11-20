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
    CREATE TABLE IF NOT EXISTS scoreboard_observations (
        observation_id TEXT PRIMARY KEY,
        match_id TEXT NOT NULL,
        timestamp REAL NOT NULL,
        raw_text TEXT,
        home_score INTEGER,
        away_score INTEGER,
        match_time TEXT,
        confidence REAL,
        bbox_json TEXT,
        FOREIGN KEY (match_id)
            REFERENCES matches(match_id)
            ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS audio_features (
        feature_id TEXT PRIMARY KEY,
        match_id TEXT NOT NULL,
        start_time REAL NOT NULL,
        end_time REAL NOT NULL,
        center_time REAL NOT NULL,
        rms REAL NOT NULL,
        zero_crossing_rate REAL NOT NULL,
        spectral_centroid REAL NOT NULL,
        FOREIGN KEY (match_id)
            REFERENCES matches(match_id)
            ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS audio_peaks (
        peak_id TEXT PRIMARY KEY,
        match_id TEXT NOT NULL,
        timestamp REAL NOT NULL,
        rms REAL NOT NULL,
        z_score REAL NOT NULL,
        FOREIGN KEY (match_id)
            REFERENCES matches(match_id)
            ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_scoreboard_match_time
    ON scoreboard_observations(match_id, timestamp);

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

    CREATE INDEX IF NOT EXISTS idx_audio_features_match_time
        ON audio_features(match_id, start_time);

    CREATE INDEX IF NOT EXISTS idx_audio_peaks_match_time
        ON audio_peaks(match_id, timestamp);
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


def insert_audio_features(
    connection,
    match_id: str,
    features: list[dict],
) -> None:
    rows = [
        (
            f"{match_id}:feature:{index:05d}",
            match_id,
            feature["start_time"],
            feature["end_time"],
            feature["center_time"],
            feature["rms"],
            feature["zero_crossing_rate"],
            feature["spectral_centroid"],
        )
        for index, feature in enumerate(features, start=1)
    ]

    connection.executemany(
        """
        INSERT INTO audio_features (
            feature_id,
            match_id,
            start_time,
            end_time,
            center_time,
            rms,
            zero_crossing_rate,
            spectral_centroid
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(feature_id)
        DO UPDATE SET
            match_id = excluded.match_id,
            start_time = excluded.start_time,
            end_time = excluded.end_time,
            center_time = excluded.center_time,
            rms = excluded.rms,
            zero_crossing_rate = excluded.zero_crossing_rate,
            spectral_centroid = excluded.spectral_centroid
        """,
        rows,
    )


def insert_audio_peaks(
    connection,
    match_id: str,
    peaks: list[dict],
) -> None:
    rows = [
        (
            peak["peak_id"],
            match_id,
            peak["timestamp"],
            peak["rms"],
            peak["z_score"],
        )
        for peak in peaks
    ]

    connection.executemany(
        """
        INSERT INTO audio_peaks (
            peak_id,
            match_id,
            timestamp,
            rms,
            z_score
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(peak_id)
        DO UPDATE SET
            match_id = excluded.match_id,
            timestamp = excluded.timestamp,
            rms = excluded.rms,
            z_score = excluded.z_score
        """,
        rows,
    )


def insert_scoreboard_observations(
    connection,
    match_id: str,
    observations: list[dict],
) -> None:
    import json

    raw_by_timestamp = {}

    if observations and "raw_text" in observations[0]:
        parsed_observations = observations
    else:
        from pipeline.analysis.scoreboard_parser import parse_scoreboard

        parsed_observations = parse_scoreboard(observations)

    for observation in observations:
        if "timestamp" not in observation:
            continue
        raw_by_timestamp.setdefault(observation["timestamp"], []).append(observation)

    rows = []
    for index, parsed in enumerate(parsed_observations, start=1):
        timestamp = parsed["timestamp"]

        score_candidates = parsed.get("score_candidates") or []
        clock_candidates = parsed.get("clock_candidates") or []
        score = score_candidates[0] if score_candidates else None

        source_observations = raw_by_timestamp.get(timestamp, [])
        confidences = [
            float(item["confidence"])
            for item in source_observations
            if item.get("confidence") is not None
        ]
        confidence = (
            sum(confidences) / len(confidences)
            if confidences
            else parsed.get("confidence")
        )

        bbox_values = [
            item["bbox"]
            for item in source_observations
            if item.get("bbox")
        ]

        rows.append(
            (
                f"{match_id}:{timestamp}:{index}",
                match_id,
                timestamp,
                parsed.get("raw_text"),
                score.get("home") if score else None,
                score.get("away") if score else None,
                clock_candidates[0] if clock_candidates else None,
                confidence,
                json.dumps(bbox_values, ensure_ascii=False),
            )
        )

    connection.executemany(
        """
        INSERT INTO scoreboard_observations (
            observation_id,
            match_id,
            timestamp,
            raw_text,
            home_score,
            away_score,
            match_time,
            confidence,
            bbox_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(observation_id)
        DO UPDATE SET
            match_id = excluded.match_id,
            timestamp = excluded.timestamp,
            raw_text = excluded.raw_text,
            home_score = excluded.home_score,
            away_score = excluded.away_score,
            match_time = excluded.match_time,
            confidence = excluded.confidence,
            bbox_json = excluded.bbox_json
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


def persist_scoreboard(
    db_path: str,
    match_id: str,
    observations: list[dict],
) -> None:
    with get_connection(db_path) as connection:
        insert_scoreboard_observations(
            connection,
            match_id,
            observations,
        )


def persist_audio(
    db_path: str,
    match_id: str,
    features: list[dict],
    peaks: list[dict],
) -> None:
    with get_connection(db_path) as connection:
        insert_audio_features(connection, match_id, features)
        insert_audio_peaks(connection, match_id, peaks)