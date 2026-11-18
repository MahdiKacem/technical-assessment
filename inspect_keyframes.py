import json

from pipeline.ingestion.keyframes import (
    extract_keyframes,
    save_keyframes,
)

VIDEO_PATH = "data/input/Barcelona vs Real Madrid (2017).mp4"

ARTIFACT_DIR = "data/artifacts/El classico 2017"
INDEX_DIR = f"{ARTIFACT_DIR}/index"

with open(f"{INDEX_DIR}/windows.json", "r", encoding="utf-8") as f:
    windows = json.load(f)

keyframes = extract_keyframes(
    video_path=VIDEO_PATH,
    windows=windows,
    output_dir=f"{INDEX_DIR}/keyframes",
)

save_keyframes(
    keyframes,
    f"{INDEX_DIR}/keyframes.json",
)

print(f"Extracted {len(keyframes)} keyframes.")

for keyframe in keyframes[:10]:
    print(
        keyframe["keyframe_id"],
        f'{keyframe["timestamp"]:.2f}s',
        keyframe["image_path"],
    )