from pipeline.ingestion.windows import generate_windows


def test_long_shot_is_split():
    shots = [{
        "shot_id": "shot_00001",
        "start_time": 0.0,
        "end_time": 14.0,
        "duration": 14.0
    }]

    windows = generate_windows(shots)

    assert len(windows) == 4

    assert windows[0]["start_time"] == 0.0
    assert windows[0]["end_time"] == 5.0

    assert windows[1]["start_time"] == 4.0
    assert windows[1]["end_time"] == 9.0

    assert windows[2]["start_time"] == 8.0
    assert windows[2]["end_time"] == 13.0

    assert windows[3]["start_time"] == 12.0
    assert windows[3]["end_time"] == 14.0


def test_short_shot_is_not_split():
    shots = [{
        "shot_id": "shot_00002",
        "start_time": 20.0,
        "end_time": 25.0,
        "duration": 5.0
    }]

    windows = generate_windows(shots)

    assert len(windows) == 1
    assert windows[0]["start_time"] == 20.0
    assert windows[0]["end_time"] == 25.0


def test_windows_never_cross_shot_boundaries():
    shots = [
        {
            "shot_id": "shot_00001",
            "start_time": 0.0,
            "end_time": 14.0,
            "duration": 14.0
        },
        {
            "shot_id": "shot_00002",
            "start_time": 14.0,
            "end_time": 22.0,
            "duration": 8.0
        }
    ]

    windows = generate_windows(shots)

    for window in windows:
        parent = next(
            s for s in shots
            if s["shot_id"] == window["shot_id"]
        )

        assert window["start_time"] >= parent["start_time"]
        assert window["end_time"] <= parent["end_time"]