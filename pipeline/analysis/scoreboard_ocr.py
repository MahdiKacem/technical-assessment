import cv2
import easyocr
from pathlib import Path
import json

DEFAULT_SCOREBOARD_CROP = (0.055, 0.035, 0.33, 0.12)


def crop_scoreboard(frame, crop: tuple[float, float, float, float]):
    height, width = frame.shape[:2]
    left_ratio, top_ratio, width_ratio, height_ratio = crop

    left = max(0, int(left_ratio * width))
    top = max(0, int(top_ratio * height))
    right = min(width, int((left_ratio + width_ratio) * width))
    bottom = min(height, int((top_ratio + height_ratio) * height))

    if right <= left or bottom <= top:
        raise ValueError("Scoreboard crop must contain a non-empty frame region.")

    cropped = frame[top:bottom, left:right]
    return cropped, left, top


def extract_scoreboard_observations(
    video_path: str,
    sample_interval: float = 2.0,
    languages: list[str] | None = None,
    crop: tuple[float, float, float, float] = DEFAULT_SCOREBOARD_CROP,
    start_time: float = 0.0,
    end_time: float | None = None,
) -> list[dict]:
    if sample_interval <= 0:
        raise ValueError("sample_interval must be positive.")
    if start_time < 0:
        raise ValueError("start_time must be non-negative.")

    if languages is None:
        languages = ["en"]

    reader = easyocr.Reader(
        languages,
        gpu=True,
    )

    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)

    if fps <= 0 or frame_count <= 0:
        cap.release()
        raise RuntimeError("Invalid video metadata.")

    duration = frame_count / fps
    if end_time is None:
        end_time = duration
    if end_time < start_time:
        raise ValueError("end_time must be greater than or equal to start_time.")
    end_time = min(end_time, duration)

    observations = []
    timestamp = start_time

    try:
        while timestamp <= end_time:

            cap.set(
                cv2.CAP_PROP_POS_MSEC,
                timestamp * 1000,
            )

            success, frame = cap.read()

            if not success:
                timestamp += sample_interval
                continue

            scoreboard, crop_left, crop_top = crop_scoreboard(frame, crop)
            scale = 3
            scoreboard = cv2.resize(
                scoreboard,
                None,
                fx=scale,
                fy=scale,
                interpolation=cv2.INTER_CUBIC,
            )

            results = reader.readtext(scoreboard)

            for bbox, text, confidence in results:

                points = [
                    [
                        int(x / scale) + crop_left,
                        int(y / scale) + crop_top,
                    ]
                    for x, y in bbox
                ]

                observations.append({
                    "timestamp": round(timestamp, 3),
                    "text": text,
                    "confidence": float(confidence),
                    "bbox": points,
                })

            timestamp += sample_interval

    finally:
        cap.release()

    return observations

def save_scoreboard_observations(observations: list[dict], output_path: str) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(
            observations,
            f,
            indent=4,
            ensure_ascii=False,
        )