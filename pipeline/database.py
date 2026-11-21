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


def _add_missing_columns(connection, table: str, columns: dict[str, str]) -> None:
    existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
    for name, column_type in columns.items():
        if name not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {column_type}")


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

    CREATE TABLE IF NOT EXISTS card_events (
        card_id TEXT PRIMARY KEY,
        match_id TEXT NOT NULL,
        timestamp REAL NOT NULL,
        card_type TEXT NOT NULL,
        team TEXT,
        player_name TEXT,
        FOREIGN KEY (match_id)
            REFERENCES matches(match_id)
            ON DELETE CASCADE,
        CHECK (card_type IN ('red', 'yellow'))
    );

    CREATE TABLE IF NOT EXISTS teams (
        team_id TEXT PRIMARY KEY,
        match_id TEXT NOT NULL,
        name TEXT NOT NULL,
        short_name TEXT,
        side TEXT,
        FOREIGN KEY (match_id)
            REFERENCES matches(match_id)
            ON DELETE CASCADE,
        CHECK (side IS NULL OR side IN ('home', 'away'))
    );

    CREATE TABLE IF NOT EXISTS players (
        player_id TEXT PRIMARY KEY,
        match_id TEXT NOT NULL,
        team_id TEXT,
        shirt_number INTEGER,
        name TEXT NOT NULL,
        position TEXT,
        role TEXT,
        FOREIGN KEY (match_id)
            REFERENCES matches(match_id)
            ON DELETE CASCADE,
        FOREIGN KEY (team_id)
            REFERENCES teams(team_id)
            ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS events (
        event_id TEXT PRIMARY KEY,
        match_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        timestamp REAL NOT NULL,
        end_timestamp REAL,
        title TEXT,
        description TEXT,
        confidence REAL NOT NULL,
        entities_json TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (match_id)
            REFERENCES matches(match_id)
            ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS event_evidence (
        evidence_id TEXT PRIMARY KEY,
        event_id TEXT NOT NULL,
        source_type TEXT NOT NULL,
        source_id TEXT,
        source_timestamp REAL,
        source_value TEXT,
        confidence REAL,
        weight REAL NOT NULL DEFAULT 1.0,
        details_json TEXT,
        FOREIGN KEY (event_id)
            REFERENCES events(event_id)
            ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS event_keyframes (
        event_keyframe_id TEXT PRIMARY KEY,
        event_id TEXT NOT NULL,
        keyframe_id TEXT,
        timestamp REAL NOT NULL,
        image_path TEXT NOT NULL,
        role TEXT NOT NULL,
        FOREIGN KEY (event_id)
            REFERENCES events(event_id)
            ON DELETE CASCADE,
        CHECK (role IN ('before', 'at_event', 'after'))
    );

    CREATE TABLE IF NOT EXISTS event_search_documents (
        event_id TEXT PRIMARY KEY,
        match_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        status TEXT NOT NULL,
        timestamp REAL NOT NULL,
        title TEXT,
        description TEXT,
        entities_json TEXT,
        evidence_text TEXT,
        searchable_text TEXT NOT NULL,
        embedding_json TEXT,
        FOREIGN KEY (event_id)
            REFERENCES events(event_id)
            ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS multimodal_embeddings (
        embedding_id TEXT PRIMARY KEY,
        match_id TEXT NOT NULL,
        event_id TEXT,
        source_type TEXT NOT NULL,
        source_id TEXT,
        timestamp REAL,
        modality TEXT NOT NULL,
        model_name TEXT NOT NULL,
        model_version TEXT,
        content_hash TEXT NOT NULL,
        vector_store_id TEXT,
        vector_json TEXT,
        dimensions INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (match_id)
            REFERENCES matches(match_id)
            ON DELETE CASCADE,
        FOREIGN KEY (event_id)
            REFERENCES events(event_id)
            ON DELETE CASCADE,
        CHECK (modality IN ('text', 'image'))
    );

    CREATE TABLE IF NOT EXISTS embedding_usage (
        usage_id TEXT PRIMARY KEY,
        match_id TEXT,
        model_name TEXT NOT NULL,
        modality TEXT NOT NULL,
        item_count INTEGER NOT NULL,
        cache_hits INTEGER NOT NULL DEFAULT 0,
        input_tokens INTEGER,
        output_tokens INTEGER,
        estimated_cost REAL,
        latency_ms INTEGER,
        success INTEGER NOT NULL DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        CHECK (modality IN ('text', 'image', 'text_image'))
    );

    CREATE TABLE IF NOT EXISTS creative_briefs (
        brief_id TEXT PRIMARY KEY,
        match_id TEXT NOT NULL,
        raw_text TEXT NOT NULL,
        cache_key TEXT NOT NULL UNIQUE,
        llm_output_json TEXT,
        parsed_json TEXT NOT NULL,
        model_name TEXT NOT NULL,
        prompt_version TEXT NOT NULL,
        schema_version TEXT NOT NULL,
        effort TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (match_id)
            REFERENCES matches(match_id)
            ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS llm_usage (
        usage_id TEXT PRIMARY KEY,
        stage TEXT NOT NULL,
        match_id TEXT,
        ref_id TEXT,
        model_name TEXT NOT NULL,
        prompt_version TEXT,
        input_tokens INTEGER,
        output_tokens INTEGER,
        cache_read_tokens INTEGER,
        latency_ms INTEGER,
        estimated_cost REAL,
        cache_hit INTEGER NOT NULL DEFAULT 0,
        success INTEGER NOT NULL DEFAULT 1,
        error TEXT,
        request_id TEXT,
        stop_reason TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS frame_analyses (
        analysis_id TEXT PRIMARY KEY,
        event_id TEXT NOT NULL,
        round_index INTEGER NOT NULL,
        model_name TEXT NOT NULL,
        prompt_version TEXT NOT NULL,
        context_text TEXT NOT NULL,
        frames_json TEXT NOT NULL,
        response_json TEXT NOT NULL,
        input_tokens INTEGER,
        output_tokens INTEGER,
        thoughts_tokens INTEGER,
        latency_ms INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS goal_sequences (
        sequence_id TEXT PRIMARY KEY,
        event_id TEXT NOT NULL,
        match_id TEXT NOT NULL,
        status TEXT NOT NULL,
        buildup_start REAL NOT NULL,
        goal_time REAL NOT NULL,
        celebration_end REAL NOT NULL,
        brackets_json TEXT,
        replays_json TEXT,
        issues_json TEXT,
        frame_labels_json TEXT,
        model_name TEXT NOT NULL,
        prompt_version TEXT NOT NULL,
        feature_extractor TEXT,
        details_json TEXT,
        clip_start REAL,
        clip_end REAL,
        cut_notes_json TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (event_id)
            REFERENCES events(event_id)
            ON DELETE CASCADE,
        CHECK (status IN ('ok', 'uncertain', 'fallback'))
    );

    CREATE TABLE IF NOT EXISTS stage_runs (
        run_id TEXT PRIMARY KEY,
        stage TEXT NOT NULL,
        match_id TEXT,
        started_at TEXT NOT NULL,
        elapsed_seconds REAL,
        status TEXT NOT NULL,
        params_json TEXT,
        summary_json TEXT,
        error TEXT,
        CHECK (status IN ('running', 'success', 'failed'))
    );

    CREATE INDEX IF NOT EXISTS idx_stage_runs_stage
        ON stage_runs(stage, started_at);

    CREATE INDEX IF NOT EXISTS idx_llm_usage_stage
        ON llm_usage(stage, created_at);

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

    CREATE INDEX IF NOT EXISTS idx_card_events_match_time
        ON card_events(match_id, timestamp);

    CREATE INDEX IF NOT EXISTS idx_events_match_time
        ON events(match_id, timestamp);

    CREATE INDEX IF NOT EXISTS idx_events_match_type
        ON events(match_id, event_type);

    CREATE INDEX IF NOT EXISTS idx_event_evidence_event
        ON event_evidence(event_id);

    CREATE INDEX IF NOT EXISTS idx_event_evidence_source
        ON event_evidence(source_type, source_id);

    CREATE INDEX IF NOT EXISTS idx_event_keyframes_event
        ON event_keyframes(event_id, timestamp);

    CREATE INDEX IF NOT EXISTS idx_multimodal_match_time
        ON multimodal_embeddings(match_id, timestamp);

    CREATE INDEX IF NOT EXISTS idx_multimodal_event
        ON multimodal_embeddings(event_id);

    CREATE INDEX IF NOT EXISTS idx_multimodal_cache
        ON multimodal_embeddings(model_name, model_version, content_hash);

    CREATE INDEX IF NOT EXISTS idx_teams_match
        ON teams(match_id);

    CREATE INDEX IF NOT EXISTS idx_players_match
        ON players(match_id);

    CREATE INDEX IF NOT EXISTS idx_players_team
        ON players(team_id);

    CREATE INDEX IF NOT EXISTS idx_event_search_match
        ON event_search_documents(match_id, event_type, status);
    """

    with get_connection(db_path) as connection:
        connection.executescript(schema)
        _add_missing_columns(connection, "creative_briefs", {"llm_output_json": "TEXT"})
        _add_missing_columns(connection, "goal_sequences", {
            "clip_start": "REAL", "clip_end": "REAL", "cut_notes_json": "TEXT",
        })
        try:
            connection.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS event_search_fts
                USING fts5(
                    event_id UNINDEXED,
                    match_id UNINDEXED,
                    event_type UNINDEXED,
                    status UNINDEXED,
                    title,
                    description,
                    entities,
                    evidence_text,
                    tokenize='unicode61'
                )
                """
            )
        except sqlite3.OperationalError:
            pass

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
        parsed_observations = parse_scoreboard_with_roster(
            connection, match_id, observations
        )

    for observation in observations:
        if "timestamp" not in observation:
            continue
        raw_by_timestamp.setdefault(observation["timestamp"], []).append(observation)

    return _insert_parsed_scoreboard(
        connection, match_id, parsed_observations, raw_by_timestamp
    )


def parse_scoreboard_with_roster(connection, match_id: str, observations: list[dict]) -> list[dict]:
    from pipeline.analysis.scoreboard_parser import parse_scoreboard

    teams = connection.execute(
        "SELECT name, side FROM teams WHERE match_id = ?", (match_id,)
    ).fetchall()
    players = connection.execute(
        "SELECT shirt_number, name, position, role FROM players WHERE match_id = ?",
        (match_id,),
    ).fetchall()

    team_labels = {
        "left": next((t["name"] for t in teams if t["side"] == "home"), None),
        "right": next((t["name"] for t in teams if t["side"] == "away"), None),
    }
    player_values = [dict(player) for player in players]

    return parse_scoreboard(
        observations,
        team_labels=team_labels,
        players=player_values,
    )


def _insert_parsed_scoreboard(
    connection,
    match_id: str,
    parsed_observations: list[dict],
    raw_by_timestamp: dict,
) -> None:

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


def insert_card_events(
    connection,
    match_id: str,
    parsed_observations: list[dict],
) -> None:
    seen = set()
    rows = []

    for observation in parsed_observations:
        timestamp = observation["timestamp"]
        for card in observation.get("card_candidates") or []:
            key = (
                card["type"],
                card.get("team"),
                card.get("player"),
            )
            if key in seen:
                continue

            seen.add(key)
            card_id = (
                f"{match_id}:card:"
                f"{card['type']}:{card.get('team') or 'unknown'}:"
                f"{card.get('player') or 'unknown'}"
            )
            rows.append(
                (
                    card_id,
                    match_id,
                    timestamp,
                    card["type"],
                    card.get("team"),
                    card.get("player"),
                )
            )

    connection.executemany(
        """
        INSERT INTO card_events (
            card_id,
            match_id,
            timestamp,
            card_type,
            team,
            player_name
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(card_id)
        DO UPDATE SET
            match_id = excluded.match_id,
            timestamp = excluded.timestamp,
            card_type = excluded.card_type,
            team = excluded.team,
            player_name = excluded.player_name
        """,
        rows,
    )


def persist_card_events(
    db_path: str,
    match_id: str,
    parsed_observations: list[dict],
) -> None:
    with get_connection(db_path) as connection:
        insert_card_events(connection, match_id, parsed_observations)


def persist_audio(
    db_path: str,
    match_id: str,
    features: list[dict],
    peaks: list[dict],
) -> None:
    with get_connection(db_path) as connection:
        insert_audio_features(connection, match_id, features)
        insert_audio_peaks(connection, match_id, peaks)


def insert_events(
    connection,
    match_id: str,
    events: list[dict],
) -> None:
    connection.execute(
        """
        DELETE FROM event_evidence
        WHERE event_id IN (
            SELECT event_id FROM events WHERE match_id = ?
        )
        """,
        (match_id,),
    )
    connection.execute(
        "DELETE FROM events WHERE match_id = ?",
        (match_id,),
    )

    event_rows = []
    evidence_rows = []

    for event in events:
        entities = event.get("entities") or {}
        event_rows.append(
            (
                event["event_id"],
                match_id,
                event["event_type"],
                event["timestamp"],
                event.get("end_timestamp"),
                event.get("title"),
                event.get("description"),
                event.get("confidence", 0.0),
                json.dumps(entities, ensure_ascii=False),
            )
        )

        for evidence in event.get("evidence") or []:
            details = evidence.get("details") or {}
            evidence_rows.append(
                (
                    evidence["evidence_id"],
                    event["event_id"],
                    evidence["source_type"],
                    evidence.get("source_id"),
                    evidence.get("source_timestamp"),
                    evidence.get("source_value"),
                    evidence.get("confidence"),
                    evidence.get("weight", 1.0),
                    json.dumps(details, ensure_ascii=False),
                )
            )

    connection.executemany(
        """
        INSERT INTO events (
            event_id,
            match_id,
            event_type,
            timestamp,
            end_timestamp,
            title,
            description,
            confidence,
            entities_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(event_id)
        DO UPDATE SET
            match_id = excluded.match_id,
            event_type = excluded.event_type,
            timestamp = excluded.timestamp,
            end_timestamp = excluded.end_timestamp,
            title = excluded.title,
            description = excluded.description,
            confidence = excluded.confidence,
            entities_json = excluded.entities_json
        """,
        event_rows,
    )

    connection.executemany(
        """
        INSERT INTO event_evidence (
            evidence_id,
            event_id,
            source_type,
            source_id,
            source_timestamp,
            source_value,
            confidence,
            weight,
            details_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(evidence_id)
        DO UPDATE SET
            event_id = excluded.event_id,
            source_type = excluded.source_type,
            source_id = excluded.source_id,
            source_timestamp = excluded.source_timestamp,
            source_value = excluded.source_value,
            confidence = excluded.confidence,
            weight = excluded.weight,
            details_json = excluded.details_json
        """,
        evidence_rows,
    )


def persist_events(
    db_path: str,
    match_id: str,
    events: list[dict],
) -> None:
    with get_connection(db_path) as connection:
        insert_events(connection, match_id, events)


def insert_event_keyframes(
    connection,
    match_id: str,
    manifest: list[dict],
) -> None:
    connection.execute(
        """
        DELETE FROM event_keyframes
        WHERE event_id IN (
            SELECT event_id FROM events WHERE match_id = ?
        )
        """,
        (match_id,),
    )

    rows = []
    for entry in manifest:
        event_id = entry["event_id"]
        for index, keyframe in enumerate(entry["keyframes"], start=1):
            rows.append(
                (
                    f"{event_id}:keyframe:{index}",
                    event_id,
                    keyframe["keyframe_id"],
                    keyframe["timestamp"],
                    keyframe["image_path"],
                    keyframe["role"],
                )
            )

    connection.executemany(
        """
        INSERT INTO event_keyframes (
            event_keyframe_id,
            event_id,
            keyframe_id,
            timestamp,
            image_path,
            role
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(event_keyframe_id)
        DO UPDATE SET
            event_id = excluded.event_id,
            keyframe_id = excluded.keyframe_id,
            timestamp = excluded.timestamp,
            image_path = excluded.image_path,
            role = excluded.role
        """,
        rows,
    )


def persist_event_keyframes(
    db_path: str,
    match_id: str,
    manifest: list[dict],
) -> None:
    with get_connection(db_path) as connection:
        insert_event_keyframes(connection, match_id, manifest)


def insert_rosters(
    connection,
    match_id: str,
    rosters: list[dict],
) -> None:
    team_rows = []
    player_rows = []

    for roster in rosters:
        teams = roster.get("teams") or []
        roster_team_name = (roster.get("team_name") or "").lower()
        matching_team_id = None

        for team in teams:
            team_name = team["name"]
            team_id = f"{match_id}:team:{team_name}"
            team_rows.append(
                (
                    team_id,
                    match_id,
                    team_name,
                    team_name,
                    team.get("side"),
                )
            )

            normalized_team_name = team_name.lower()
            if (
                roster_team_name
                and (
                    normalized_team_name == roster_team_name
                    or roster_team_name in normalized_team_name
                    or normalized_team_name in roster_team_name
                )
            ):
                matching_team_id = team_id

        if matching_team_id is None and teams:
            matching_team_id = f"{match_id}:team:{teams[0]['name']}"

        for player in roster.get("players") or []:
            shirt_number = player.get("shirt_number")
            player_name = player["name"]
            player_id = (
                f"{match_id}:player:"
                f"{teams[0]['name'] if teams else 'unknown'}:"
                f"{shirt_number if shirt_number is not None else player_name}"
            )
            player_rows.append(
                (
                    player_id,
                    match_id,
                    matching_team_id,
                    shirt_number,
                    player_name,
                    player.get("position"),
                    player.get("role"),
                )
            )

    connection.executemany(
        """
        INSERT INTO teams (
            team_id,
            match_id,
            name,
            short_name,
            side
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(team_id)
        DO UPDATE SET
            match_id = excluded.match_id,
            name = excluded.name,
            short_name = excluded.short_name,
            side = excluded.side
        """,
        team_rows,
    )

    connection.executemany(
        """
        INSERT INTO players (
            player_id,
            match_id,
            team_id,
            shirt_number,
            name,
            position,
            role
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(player_id)
        DO UPDATE SET
            match_id = excluded.match_id,
            team_id = excluded.team_id,
            shirt_number = excluded.shirt_number,
            name = excluded.name,
            position = excluded.position,
            role = excluded.role
        """,
        player_rows,
    )


def persist_rosters(
    db_path: str,
    match_id: str,
    rosters: list[dict],
) -> None:
    with get_connection(db_path) as connection:
        insert_rosters(connection, match_id, rosters)