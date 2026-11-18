import json
from pathlib import Path
import cv2

def extract_keyframes(video_path: str, windows: list[dict], output_dir: str, max_width: int = 960, jpeg_quality: int = 85) -> list[dict]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    keyframes = []

    try:
        for index, window in enumerate(windows, start=1):
            #extract the middle timestamp of the window
            timestamp = (
                window["start_time"] + window["end_time"]
            ) / 2

            #seek to the requested timestamp
            cap.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)

            success, frame = cap.read()

            if not success:
                raise RuntimeError(
                    f"Could not extract frame at {timestamp:.2f}s"
                )

            #resize while preserving the aspect ratio
            height, width = frame.shape[:2]

            if width > max_width:
                new_height = int(height * max_width / width)
                frame = cv2.resize(
                    frame,
                    (max_width, new_height),
                    interpolation=cv2.INTER_AREA,
                )

            keyframe_id = f"keyframe_{index:06d}"
            filename = f"{keyframe_id}.jpg"
            image_path = output_dir / filename

            saved = cv2.imwrite(
                str(image_path),
                frame,
                [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality],
            )

            if not saved:
                raise RuntimeError(
                    f"Could not save keyframe: {image_path}"
                )

            keyframes.append({
                "keyframe_id": keyframe_id,
                "window_id": window["window_id"],
                "shot_id": window["shot_id"],
                "timestamp": round(timestamp, 3),
                "image_path": f"keyframes/{filename}",
            })

    finally:
        cap.release()

    return keyframes


def save_keyframes(
    keyframes: list[dict],
    output_path: str,
) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(keyframes, f, indent=4)