import numpy as np

from pipeline.analysis.scoreboard_ocr import crop_scoreboard
from pipeline.analysis.scoreboard_parser import parse_scoreboard


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
