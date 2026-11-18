
import json
from pathlib import Path

from scenedetect import open_video, SceneManager
from scenedetect.detectors import ContentDetector


def detect_shots(video_path: str, threshold: float = 27.0, min_scene_len: int = 15) -> list[dict]:
    video_path = Path(video_path)

    if not video_path.exists():
        raise FileNotFoundError(
            f"Video not found: {video_path}"
        )

    video = open_video(str(video_path))

    scene_manager = SceneManager()

    scene_manager.add_detector(
        ContentDetector(
            threshold=threshold,
            min_scene_len=min_scene_len
        )
    )

    scene_manager.detect_scenes(video)

    scene_list = scene_manager.get_scene_list()

    shots = []

    for index, (start, end) in enumerate(scene_list):
        shots.append({
            "shot_id": f"shot_{index + 1:05d}",
            "start_time": start.get_seconds(),
            "end_time": end.get_seconds(),
            "duration": end.get_seconds() - start.get_seconds()
        })

    return shots


def save_shots(shots: list[dict], output_path: str) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(shots, f, indent=4)