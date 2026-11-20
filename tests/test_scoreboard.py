import numpy as np

from pipeline.analysis.scoreboard_ocr import crop_scoreboard
from pipeline.analysis.scoreboard_parser import parse_scoreboard
from pipeline.normalization import normalize_name, resolve_player_name


def test_crop_scoreboard_uses_relative_video_region():
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    crop, left, top = crop_scoreboard(
        frame,
        (0.055, 0.035, 0.33, 0.12),
    )

    assert crop.shape == (86, 422, 3)
    assert (left, top) == (70, 25)


def test_parse_scoreboard_detects_1_0_without_decimal_clock_false_match():
    observations = [
        {
            "timestamp": 1955.25,
            "text": "27.52",
            "bbox": [[106, 42], [184, 42], [184, 72], [106, 72]],
        },
        {
            "timestamp": 1955.25,
            "text": "RMA",
            "bbox": [[197, 43], [247, 43], [247, 63], [197, 63]],
        },
        {
            "timestamp": 1955.25,
            "text": "1 0",
            "bbox": [[265, 43], [319, 43], [319, 67], [265, 67]],
        },
        {
            "timestamp": 1955.25,
            "text": "BAR",
            "bbox": [[339, 43], [387, 43], [387, 63], [339, 63]],
        },
    ]

    parsed = parse_scoreboard(observations)

    assert parsed[0]["score_candidates"] == [{"home": 1, "away": 0}]


def test_parse_scoreboard_detects_red_card_for_rma_player():
    observations = [
        {
            "timestamp": 5187.25,
            "text": "RMA",
            "bbox": [[127, 43], [177, 43], [177, 63], [127, 63]],
        },
        {
            "timestamp": 5187.25,
            "text": "SERgio RAMOS",
            "bbox": [[107, 82], [241, 82], [241, 102], [107, 102]],
        },
        {
            "timestamp": 5187.25,
            "text": "4",
            "bbox": [[77, 82], [95, 82], [95, 102], [77, 102]],
        },
        {
            "timestamp": 5187.25,
            "text": "arjeia Roja",
            "bbox": [[107, 106], [204, 106], [204, 126], [107, 126]],
        },
        {
            "timestamp": 5187.25,
            "text": "BAR",
            "bbox": [[270, 43], [316, 43], [316, 63], [270, 63]],
        },
    ]

    parsed = parse_scoreboard(observations)

    assert parsed[0]["card_candidates"] == [
        {
            "type": "red",
            "team": "RMA",
            "player": "SERGIO RAMOS",
        }
    ]


def test_normalize_name_handles_accents_and_punctuation():
    assert normalize_name("Marc-André ter Stegen") == "MARC ANDRE TER STEGEN"
    assert normalize_name("Ivan Rakitić") == "IVAN RAKITIC"


def test_resolve_player_name_matches_roster_spelling():
    players = [
        {"name": "Ivan Rakitić", "shirt_number": 4},
        {"name": "Lionel Messi", "shirt_number": 10},
        {"name": "Sergio Ramos", "shirt_number": 4},
    ]

    resolved = resolve_player_name("SERgio RAMOU", players)

    assert resolved is not None
    assert resolved["name"] == "Sergio Ramos"


def test_stabilize_rejects_single_frame_score_reversal():
    observations = [
        {
            "timestamp": 4912.0,
            "text": "RMA",
            "bbox": [[197, 43], [247, 43], [247, 63], [197, 63]],
        },
        {
            "timestamp": 4912.0,
            "text": "2",
            "bbox": [[265, 43], [280, 43], [280, 67], [265, 67]],
        },
        {
            "timestamp": 4912.0,
            "text": "1",
            "bbox": [[299, 43], [319, 43], [319, 67], [299, 67]],
        },
        {
            "timestamp": 4912.5,
            "text": "1 2",
            "bbox": [[265, 43], [319, 43], [319, 67], [265, 67]],
        },
    ]

    parsed = parse_scoreboard(observations, stabilize=True)
    frame_scores = [
        score
        for item in parsed
        for score in item["score_candidates"]
    ]

    assert frame_scores == []


def test_parse_scoreboard_uses_generic_team_labels():
    observations = [
        {
            "timestamp": 100.0,
            "text": "HOME",
            "bbox": [[100, 43], [160, 43], [160, 63], [100, 63]],
        },
        {
            "timestamp": 100.0,
            "text": "AWAY",
            "bbox": [[220, 43], [280, 43], [280, 63], [220, 63]],
        },
        {
            "timestamp": 100.0,
            "text": "TARJETA ROJA",
            "bbox": [[90, 82], [180, 82], [180, 102], [90, 102]],
        },
        {
            "timestamp": 100.0,
            "text": "SERGIO RAMOS",
            "bbox": [[90, 65], [200, 65], [200, 78], [90, 78]],
        },
    ]

    parsed = parse_scoreboard(
        observations,
        team_labels={"left": "HOME", "right": "AWAY"},
        players=[{"name": "Sergio Ramos", "shirt_number": 4}],
    )

    assert parsed[0]["card_candidates"][0]["team"] == "HOME"
    assert parsed[0]["card_candidates"][0]["player"] == "Sergio Ramos"
