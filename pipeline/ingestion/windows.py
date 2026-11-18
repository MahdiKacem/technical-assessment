import json
from pathlib import Path

def generate_windows(shots: list[dict], window_duration: float = 5.0, overlap: float = 1.0, split_threshold: float = 10.0) -> list[dict]:
    if window_duration <= 0:
        raise ValueError("Window duration must be positive.")

    if overlap < 0 or overlap >= window_duration:
        raise ValueError(
            "Overlap must be non-negative and smaller than window duration."
        )

    windows = []
    window_index = 1

    step = window_duration - overlap

    for shot in shots:
        shot_start = shot["start_time"]
        shot_end = shot["end_time"]
        shot_duration = shot_end - shot_start

        if shot_duration <= 0:
            raise ValueError("Shot duration must be positive.")

        if shot_duration <= split_threshold:
            windows.append({
                "window_id": f"window_{window_index:06d}",
                "shot_id": shot["shot_id"],
                "start_time": shot_start,
                "end_time": shot_end,
                "duration": shot_duration
            })

            window_index += 1
            continue

        current_start = shot_start

        while current_start < shot_end:
            current_end = min(
                current_start + window_duration,
                shot_end
            )

            windows.append({
                "window_id": f"window_{window_index:06d}",
                "shot_id": shot["shot_id"],
                "start_time": current_start,
                "end_time": current_end,
                "duration": current_end - current_start
            })

            window_index += 1
            current_start += step

    return windows


def save_windows(windows: list[dict], output_path: str) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(windows, f, indent=4)
