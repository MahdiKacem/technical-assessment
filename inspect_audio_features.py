import json

from pipeline.analysis.audio import (extract_audio_features,save_audio_features,)

MATCH_DIR = "data/artifacts/El classico 2017"

AUDIO_PATH = f"{MATCH_DIR}/audio/audio.wav"
OUTPUT_PATH = f"{MATCH_DIR}/signals/audio_features.json"

features = extract_audio_features(AUDIO_PATH)

save_audio_features(features, OUTPUT_PATH)

print(f"Extracted {len(features)} audio feature windows.")

for feature in features[:10]:
    print(
        f"{feature['start_time']:8.2f}s | "
        f"RMS: {feature['rms']:.5f} | "
        f"ZCR: {feature['zero_crossing_rate']:.5f} | "
        f"Centroid: {feature['spectral_centroid']:.2f}"
    )