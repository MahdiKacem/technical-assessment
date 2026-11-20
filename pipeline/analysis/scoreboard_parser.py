import re
from collections import defaultdict


SCORE_PATTERN = re.compile(
    r"(?<!\d)(\d{1,2})(?:\s*[-:]\s*|\s+)(\d{1,2})(?!\d)"
)

CLOCK_PATTERN = re.compile(r"(?<!\d)(\d{1,3}):([0-5]\d)(?!\d)")


def group_observations_by_timestamp(observations: list[dict],) -> dict:
    grouped = defaultdict(list)

    for observation in observations:
        grouped[observation["timestamp"]].append(observation)

    return grouped


def parse_scoreboard(observations: list[dict],) -> list[dict]:
    grouped = group_observations_by_timestamp(observations)
    parsed = []

    for timestamp, items in sorted(grouped.items()):

        # Sort detected text approximately in reading order.
        items = sorted(
            items,
            key=lambda item: (
                sum(point[1] for point in item["bbox"])
                / len(item["bbox"]),
                sum(point[0] for point in item["bbox"])
                / len(item["bbox"]),
            ),
        )

        combined_text = " ".join(
            item["text"] for item in items
        )

        # Normalize common OCR mistakes.
        normalized = combined_text.upper()
        normalized = normalized.replace("—", "-")
        normalized = normalized.replace("–", "-")
        normalized = normalized.replace("|", " ")
        normalized = re.sub(r"(?<!\d)\d+\.\d+(?!\d)", " ", normalized)

        score_matches = SCORE_PATTERN.findall(normalized)
        clock_matches = CLOCK_PATTERN.findall(normalized)

        scores = []

        for home, away in score_matches:
            home = int(home)
            away = int(away)

            # Avoid implausible football scores.
            if home <= 10 and away <= 10:
                scores.append({
                    "home": home,
                    "away": away,
                })

        clocks = [
            f"{minutes}:{seconds}"
            for minutes, seconds in clock_matches
        ]

        parsed.append({
            "timestamp": timestamp,
            "raw_text": combined_text,
            "score_candidates": scores,
            "clock_candidates": clocks,
        })

    return parsed