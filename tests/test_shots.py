from pipeline.ingestion.shots import detect_shots


def test_detect_shots():
    shots = detect_shots(
        video_path="data/input/Barcelona vs Real Madrid (2017).mp4"
    )

    assert len(shots) > 0

    for shot in shots:
        assert shot["end_time"] > shot["start_time"]
        assert shot["duration"] > 0
