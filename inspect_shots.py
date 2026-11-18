import json

from pipeline.ingestion.shots import detect_shots, save_shots

shots = detect_shots("data/input/Barcelona vs Real Madrid (2017).mp4")

save_shots(
    shots,
    "data/artifacts/El classico 2017/index/shots.json"
)

print(f"Detected {len(shots)} shots")

for shot in shots[:10]:
    print(
        f'{shot["shot_id"]}: '
        f'{shot["start_time"]:.2f}s - '
        f'{shot["end_time"]:.2f}s '
        f'({shot["duration"]:.2f}s)'
    )