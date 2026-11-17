import subprocess
from pathlib import Path

def extract_audio(video_path: str, output_path: str) -> Path:

    video_path = Path(video_path)
    output_path = Path(output_path)

    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        "ffmpeg",
        "-y", 
        "-i", str(video_path),
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-c:a", "pcm_s16le",
        str(output_path)
    ]

    try:
        subprocess.run(command, check=True, text=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Error occurred while extracting audio: {e}") from exec

    if not output_path.exists():
        raise RuntimeError("Audio file was not created.")

    return output_path