from pipeline.ingestion.metadata import extract_metadata, save_metadata
import json

def test_extract_metadata():
    metadata = extract_metadata("data/input/Barcelona vs Real Madrid (2017).mp4")
    save_metadata(
    metadata,
        "data/artifacts/El classico 2017/video_metadata.json"
    )

    assert metadata["duration_seconds"] > 0
    assert metadata["video"]["width"] > 0
    assert metadata["video"]["height"] > 0
    assert metadata["video"]["codec"] is not None

