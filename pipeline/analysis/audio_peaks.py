import json
from pathlib import Path

import numpy as np


def detect_audio_peaks(features: list[dict], baseline_window: int = 60, threshold: float = 2.5, min_distance: float = 5.0,) -> list[dict]:
    if baseline_window < 3:
        raise ValueError("Baseline window must be at least 3.")

    if not features:
        return []

    rms = np.array(
        [item["rms"] for item in features],
        dtype=float,
    )

    timestamps = np.array(
        [item["center_time"] for item in features],
        dtype=float,
    )

    peaks = []

    for i in range(len(rms)):
        start = max(0, i - baseline_window // 2)
        end = min(len(rms), i + baseline_window // 2 + 1)

        baseline = rms[start:end]

        mean = np.mean(baseline)
        std = np.std(baseline)

        if std < 1e-8:
            continue

        z_score = (rms[i] - mean) / std

        if z_score >= threshold:
            peaks.append({
                "timestamp": float(timestamps[i]),
                "rms": float(rms[i]),
                "z_score": float(z_score),
            })

    #merge nearby peaks, keeping the strongest representative
    merged = []

    for peak in peaks:
        if (
            merged
            and peak["timestamp"] - merged[-1]["timestamp"]
            < min_distance
        ):
            if peak["z_score"] > merged[-1]["z_score"]:
                merged[-1] = peak
        else:
            merged.append(peak)

    for index, peak in enumerate(merged, start=1):
        peak["peak_id"] = f"audio_peak_{index:05d}"

    return merged


def save_audio_peaks(peaks: list[dict], output_path: str,) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(peaks, f, indent=4)