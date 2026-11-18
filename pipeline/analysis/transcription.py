import json
import os
import sys
from pathlib import Path

import av


if sys.platform == "win32":
    site_packages = Path(sys.prefix) / "Lib" / "site-packages"
    nvidia_bin_dirs = sorted((site_packages / "nvidia").glob("*/bin"))

    for bin_dir in nvidia_bin_dirs:
        bin_path = str(bin_dir)
        os.environ["PATH"] = bin_path + os.pathsep + os.environ.get("PATH", "")
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(bin_path)

import ctranslate2
from faster_whisper import WhisperModel


def _patch_av_metadata_errors() -> None:
    original_open = av.open

    def compatible_open(*args, **kwargs):
        kwargs.pop("metadata_errors", None)
        return original_open(*args, **kwargs)

    av.open = compatible_open


_patch_av_metadata_errors()


def transcribe_audio(
    audio_path: str,
    model_size: str = "small",
    language: str = "en",
    device: str = "auto",
    compute_type: str | None = None,
) -> list[dict]:
    if device == "auto":
        device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"

    if compute_type is None:
        compute_type = "float16" if device == "cuda" else "int8"

    model = WhisperModel(
        model_size,
        device=device,
        compute_type=compute_type,
    )

    segments, info = model.transcribe(
        audio_path,
        language=language,
        beam_size=5,
        vad_filter=True,
    )

    results = []

    for index, segment in enumerate(segments):
        results.append({
            "segment_id": f"transcript_{index + 1:05d}",
            "start_time": round(segment.start, 3),
            "end_time": round(segment.end, 3),
            "text": segment.text.strip(),
        })

    return results


def save_transcription(segments: list[dict],output_path: str,) -> None:

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(segments, f, indent=4, ensure_ascii=False)