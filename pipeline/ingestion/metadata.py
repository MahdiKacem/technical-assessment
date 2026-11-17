
import json
import subprocess
from pathlib import Path


def extract_metadata(video_path: str) -> dict:

    video_path = Path(video_path)

    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    command = [
        "ffprobe",
        "-v", "error",
        "-show_streams",
        "-show_format",
        "-of", "json",
        str(video_path)
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"FFprobe failed: {exc.stderr}"
        ) from exc

    probe_data = json.loads(result.stdout)

    video_streams = [
        s for s in probe_data["streams"]
        if s["codec_type"] == "video"
    ]

    audio_streams = [
        s for s in probe_data["streams"]
        if s["codec_type"] == "audio"
    ]

    if not video_streams:
        raise ValueError("No video stream found.")

    video = video_streams[0]
    audio = audio_streams[0] if audio_streams else None
    fmt = probe_data.get("format", {})

    metadata = {
        "filename": video_path.name,
        "file_size_bytes": int(fmt.get("size", 0)),
        "duration_seconds": float(fmt.get("duration", 0)),
        "video": {
            "codec": video.get("codec_name"),
            "width": video.get("width"),
            "height": video.get("height"),
            "fps": video.get("avg_frame_rate"),
            "pixel_format": video.get("pix_fmt"),
        },
        "audio": {
            "available": audio is not None,
            "codec": audio.get("codec_name") if audio else None,
            "sample_rate": audio.get("sample_rate") if audio else None,
            "channels": audio.get("channels") if audio else None,
        },
        "stream_counts": {
            "video": len(video_streams),
            "audio": len(audio_streams),
        }
    }

    return metadata


def save_metadata(metadata: dict, output_path: str) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=4)
