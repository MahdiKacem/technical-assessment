
from pathlib import Path

from pipeline.ingestion.audio import extract_audio


def test_extract_audio():
    output = extract_audio(
        video_path="data/input/Barcelona vs Real Madrid (2017).mp4",
        output_path="data/artifacts/El classico 2017/audio/audio.wav"
    )

    assert output.exists()
    assert output.stat().st_size > 0
