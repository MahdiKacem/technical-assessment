from pipeline.database import (
    get_connection,
    initialize_database,
    insert_match,
    insert_scoreboard_observations,
    insert_card_events,
    insert_audio_peaks,
    insert_transcriptions,
)
from pipeline.events import (
    extract_scoreboard_events,
    extract_audio_events,
    extract_transcription_events,
    cluster_events,
    select_event_keyframes,
    select_keyframes_for_events,
)


def prepare_database(tmp_path):
    db_path = tmp_path / "match.db"
    initialize_database(str(db_path))

    connection = get_connection(str(db_path))
    insert_match(
        connection,
        "test-match",
        "test.mp4",
        {"duration_seconds": 100.0},
    )
    return db_path, connection


def test_extract_scoreboard_goal_and_card_events(tmp_path):
    db_path, connection = prepare_database(tmp_path)

    insert_scoreboard_observations(
        connection,
        "test-match",
        [
            {
                "timestamp": 10.0,
                "raw_text": "0 0",
                "score_candidates": [{"home": 0, "away": 0}],
                "bbox": [],
                "confidence": 0.99,
            },
            {
                "timestamp": 12.0,
                "raw_text": "1 0",
                "score_candidates": [{"home": 1, "away": 0}],
                "bbox": [],
                "confidence": 0.98,
            },
        ],
    )
    insert_card_events(
        connection,
        "test-match",
        [
            {
                "timestamp": 20.0,
                "card_candidates": [
                    {"type": "red", "team": "RMA", "player": "SERGIO RAMOS"}
                ],
            }
        ],
    )

    events = extract_scoreboard_events(connection, "test-match")
    connection.close()

    assert [event["event_type"] for event in events] == ["goal", "red_card"]
    assert events[0]["entities"]["score"] == {"home": 1, "away": 0}
    assert events[0]["evidence"][0]["source_type"] == "scoreboard"
    assert events[1]["entities"]["player"] == "SERGIO RAMOS"


def test_extract_audio_and_transcription_events(tmp_path):
    db_path, connection = prepare_database(tmp_path)

    insert_audio_peaks(
        connection,
        "test-match",
        [
            {
                "peak_id": "audio_peak_00001",
                "timestamp": 30.0,
                "rms": 0.2,
                "z_score": 3.0,
            }
        ],
    )
    insert_transcriptions(
        connection,
        "test-match",
        [
            {
                "segment_id": "transcript_00001",
                "start_time": 29.0,
                "end_time": 31.0,
                "text": "And he scores!",
            }
        ],
    )

    audio_events = extract_audio_events(connection, "test-match")
    transcript_events = extract_transcription_events(connection, "test-match")
    connection.close()

    assert audio_events[0]["event_type"] == "crowd_reaction"
    assert audio_events[0]["evidence"][0]["source_id"] == "audio_peak_00001"
    assert transcript_events[0]["event_type"] == "goal"
    assert transcript_events[0]["evidence"][0]["source_id"] == "transcript_00001"


def test_cluster_events_does_not_merge_card_with_substitution():
    events = [
        {
            "event_id": "yellow",
            "event_type": "yellow_card",
            "timestamp": 100.0,
            "confidence": 0.9,
            "evidence": [
                {"evidence_id": "yellow-evidence", "source_type": "scoreboard"}
            ],
        },
        {
            "event_id": "sub",
            "event_type": "substitution",
            "timestamp": 105.0,
            "confidence": 0.65,
            "evidence": [
                {"evidence_id": "sub-evidence", "source_type": "transcription"}
            ],
        },
    ]

    clustered = cluster_events(events)

    assert [event["event_type"] for event in clustered] == [
        "yellow_card",
        "substitution_candidate",
    ]


def test_cluster_goal_without_audio_is_confirmed():
    events = [
        {
            "event_id": "goal",
            "event_type": "goal",
            "timestamp": 1955.25,
            "confidence": 0.95,
            "entities": {},
            "evidence": [
                {
                    "evidence_id": "score-evidence",
                    "source_type": "scoreboard",
                    "source_id": "score-1",
                }
            ],
        }
    ]

    clustered = cluster_events(events)

    assert clustered[0]["event_type"] == "goal"
    assert clustered[0]["entities"]["resolution_status"] == "confirmed"


def test_transcript_goal_is_candidate_when_no_scoreboard_goal():
    events = [
        {
            "event_id": "transcript-goal",
            "event_type": "goal",
            "timestamp": 50.0,
            "confidence": 0.65,
            "entities": {},
            "evidence": [
                {
                    "evidence_id": "transcript-evidence",
                    "source_type": "transcription",
                    "source_id": "segment-1",
                }
            ],
        }
    ]

    clustered = cluster_events(events)

    assert clustered[0]["event_type"] == "goal_candidate"


def test_transcript_near_miss_is_not_a_goal(tmp_path):
    db_path, connection = prepare_database(tmp_path)
    insert_transcriptions(
        connection,
        "test-match",
        [
            {
                "segment_id": "transcript_near_miss",
                "start_time": 40.0,
                "end_time": 42.0,
                "text": "Ronaldo! What a miss! It was lifted over the crossbar.",
            }
        ],
    )

    transcript_events = extract_transcription_events(connection, "test-match")
    clustered = cluster_events(transcript_events)
    connection.close()

    assert len(clustered) == 1
    assert clustered[0]["event_type"] == "near_miss"
    assert clustered[0]["confidence"] == 0.75


def test_near_miss_stays_separate_from_nearby_card():
    events = [
        {
            "event_id": "yellow",
            "event_type": "yellow_card",
            "timestamp": 100.0,
            "confidence": 0.9,
            "evidence": [
                {"evidence_id": "yellow-evidence", "source_type": "scoreboard"}
            ],
        },
        {
            "event_id": "miss",
            "event_type": "near_miss",
            "timestamp": 105.0,
            "confidence": 0.75,
            "evidence": [
                {"evidence_id": "miss-evidence", "source_type": "transcription"}
            ],
        },
    ]

    clustered = cluster_events(events)

    assert [event["event_type"] for event in clustered] == [
        "yellow_card",
        "near_miss",
    ]


def test_fusion_uses_scoreboard_goal_without_audio():
    events = [
        {
            "event_id": "goal",
            "event_type": "goal",
            "timestamp": 1955.25,
            "confidence": 0.95,
            "entities": {},
            "evidence": [
                {
                    "evidence_id": "scoreboard-evidence",
                    "source_type": "scoreboard",
                    "source_id": "observation-1",
                }
            ],
        }
    ]

    fused = cluster_events(events)

    assert fused[0]["event_type"] == "goal"
    assert fused[0]["confidence"] == 0.95
    assert fused[0]["entities"]["resolution_status"] == "confirmed"


def test_fusion_near_miss_does_not_disprove_card():
    events = [
        {
            "event_id": "red",
            "event_type": "red_card",
            "timestamp": 5187.25,
            "confidence": 0.90,
            "entities": {"team": "RMA", "player": "SERGIO RAMOS"},
            "evidence": [
                {
                    "evidence_id": "red-evidence",
                    "source_type": "scoreboard",
                    "source_id": "card-1",
                }
            ],
        },
        {
            "event_id": "miss",
            "event_type": "near_miss",
            "timestamp": 5188.0,
            "confidence": 0.75,
            "evidence": [
                {
                    "evidence_id": "miss-evidence",
                    "source_type": "transcription",
                    "source_id": "segment-1",
                }
            ],
        },
    ]

    fused = cluster_events(events)
    red_events = [event for event in fused if event["event_type"] == "red_card"]

    assert len(red_events) == 1
    assert red_events[0]["confidence"] == 0.90


def test_select_event_keyframes_uses_before_at_and_after():
    event = {
        "event_id": "goal",
        "event_type": "goal",
        "timestamp": 100.0,
        "confidence": 0.95,
        "entities": {"resolution_status": "confirmed"},
    }
    keyframes = [
        {"keyframe_id": "before", "timestamp": 90.0, "image_path": "before.jpg"},
        {"keyframe_id": "at", "timestamp": 100.0, "image_path": "at.jpg"},
        {"keyframe_id": "after", "timestamp": 110.0, "image_path": "after.jpg"},
    ]

    selected = select_event_keyframes(event, keyframes)

    assert [item["role"] for item in selected] == [
        "before",
        "at_event",
        "after",
    ]
    assert [item["keyframe_id"] for item in selected] == [
        "before",
        "at",
        "after",
    ]


def test_keyframe_manifest_skips_low_confidence_candidates():
    events = [
        {
            "event_id": "candidate",
            "event_type": "goal_candidate",
            "timestamp": 50.0,
            "confidence": 0.65,
            "entities": {"resolution_status": "candidate"},
        },
        {
            "event_id": "confirmed",
            "event_type": "goal",
            "timestamp": 100.0,
            "confidence": 0.95,
            "entities": {"resolution_status": "confirmed"},
        },
    ]
    keyframes = [
        {"keyframe_id": "k1", "timestamp": 90.0, "image_path": "90.jpg"},
        {"keyframe_id": "k2", "timestamp": 100.0, "image_path": "100.jpg"},
        {"keyframe_id": "k3", "timestamp": 110.0, "image_path": "110.jpg"},
    ]

    manifest = select_keyframes_for_events(events, keyframes)

    assert [entry["event_id"] for entry in manifest] == ["confirmed"]
