import json

from pipeline.analysis.audio_peaks import (
    detect_audio_peaks,
    save_audio_peaks,
)

MATCH_DIR = "data/artifacts/El classico 2017"

with open(
    f"{MATCH_DIR}/signals/audio_features.json",
    "r",
    encoding="utf-8",
) as f:
    features = json.load(f)

peaks = detect_audio_peaks(features)

save_audio_peaks(
    peaks,
    f"{MATCH_DIR}/signals/audio_peaks.json",
)

print(f"Detected {len(peaks)} audio peaks.")

for peak in peaks:
    print(
        f"{peak['timestamp']:.2f}s | "
        f"RMS: {peak['rms']:.4f} | "
        f"Z-score: {peak['z_score']:.2f}"
    )