import json
from pathlib import Path

import librosa
import numpy as np


def extract_audio_features(audio_path: str, frame_duration: float = 2.0, hop_duration: float = 1.0,) -> list[dict]:
    if frame_duration <= 0 or hop_duration <= 0:
        raise ValueError("Frame and hop durations must be positive.")

    if hop_duration > frame_duration:
        raise ValueError("Hop duration cannot exceed frame duration.")

    #load mono audio at its existing sample rate
    audio, sample_rate = librosa.load(
        audio_path,
        sr=None,
        mono=True,
    )

    frame_length = int(frame_duration * sample_rate)
    hop_length = int(hop_duration * sample_rate)

    #calculate audio features.
    rms = librosa.feature.rms(
        y=audio,
        frame_length=frame_length,
        hop_length=hop_length,
        center=False,
    )[0]

    zcr = librosa.feature.zero_crossing_rate(
        y=audio,
        frame_length=frame_length,
        hop_length=hop_length,
        center=False,
    )[0]

    spectral_centroid = librosa.feature.spectral_centroid(
        y=audio,
        sr=sample_rate,
        n_fft=frame_length,
        hop_length=hop_length,
        center=False,
    )[0]

    features = []

    for i in range(len(rms)):
        start_time = i * hop_duration
        end_time = start_time + frame_duration

        features.append({
            "start_time": round(start_time, 3),
            "end_time": round(end_time, 3),
            "center_time": round(
                (start_time + end_time) / 2, 3
            ),
            "rms": float(rms[i]),
            "zero_crossing_rate": float(zcr[i]),
            "spectral_centroid": float(spectral_centroid[i]),
        })

    return features

def save_audio_features(features: list[dict],output_path: str,) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(features, f, indent=4)