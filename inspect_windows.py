import json

from pipeline.ingestion.windows import (
    generate_windows,
    save_windows
)

with open(
    "data/artifacts/El classico 2017/index/shots.json",
    "r",
    encoding="utf-8"
) as f:
    shots = json.load(f)

windows = generate_windows(shots)

save_windows(
    windows,
    "data/artifacts/El classico 2017/index/windows.json"
)

print(f"Total shots: {len(shots)}")
print(f"Total windows: {len(windows)}")

print("\nFirst 15 windows:")

for window in windows[:15]:
    print(
        f'{window["window_id"]} | '
        f'{window["shot_id"]} | '
        f'{window["start_time"]:.2f}s - '
        f'{window["end_time"]:.2f}s'
    )