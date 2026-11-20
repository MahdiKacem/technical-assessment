import json
from pipeline.analysis.scoreboard_parser import (parse_scoreboard,)

MATCH_DIR = "data/artifacts/El classico 2017"

with open(
    f"{MATCH_DIR}/signals/scoreboard_ocr.json",
    "r",
    encoding="utf-8",
) as f:
    observations = json.load(f)

parsed = parse_scoreboard(observations)

with open(
    f"{MATCH_DIR}/signals/scoreboard_parsed.json",
    "w",
    encoding="utf-8",
) as f:
    json.dump(parsed, f, indent=4, ensure_ascii=False)

for item in parsed:
    if item["score_candidates"] or item["clock_candidates"]:
        print(
            f"{item['timestamp']:.1f}s | "
            f"Scores: {item['score_candidates']} | "
            f"Clocks: {item['clock_candidates']} | "
            f"Text: {item['raw_text']}"
        )

print(f"\nProcessed {len(parsed)} frames.")