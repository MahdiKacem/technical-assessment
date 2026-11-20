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
        red_card = bool(
            re.search(r"\b(?:TARJETA\s+ROJA|RED\s+CARD|ROJA)\b", normalized)
        )
        yellow_card = bool(
            re.search(
                r"\b(?:TARJETA\s+AMARILLA|YELLOW\s+CARD|AMARILLA)\b",
                normalized,
            )
        )

        card_items = [
            item
            for item in items
            if re.search(
                r"ROJA|ROJO|RED|AMARILLA|AMARILLO|YELLOW|TARJETA|CARD",
                item["text"].upper(),
            )
        ]

        rma_x = None
        bar_x = None
        for item in items:
            text = item["text"].upper()
            center_x = sum(point[0] for point in item["bbox"]) / len(item["bbox"])
            if text == "RMA":
                rma_x = center_x
            elif text == "BAR":
                bar_x = center_x

        team = None
        card_x = None
        if card_items:
            card_x = sum(
                sum(point[0] for point in item["bbox"]) / len(item["bbox"])
                for item in card_items
            ) / len(card_items)
        if rma_x is not None and bar_x is not None and card_x is not None:
            team = "RMA" if abs(card_x - rma_x) < abs(card_x - bar_x) else "BAR"
        elif rma_x is not None:
            team = "RMA"
        elif bar_x is not None:
            team = "BAR"

        player_name = None
        player_match = re.search(
            r"([A-Z][A-Z\s]+?)\s+(?:TARJETA\s+(?:ROJA|AMARILLA)|"
            r"(?:RED|YELLOW)\s+CARD)",
            normalized,
        )
        if player_match:
            player_name = re.sub(
                r"\b(?:RMA|BAR|[0-9]+(?:[.: -][0-9]+)*)\b",
                "",
                player_match.group(1),
            )
            player_name = " ".join(player_name.split())
            if not player_name:
                player_name = None

        if player_name is None:
            card_phrase_item = None
            for item in items:
                item_text = item["text"].upper()
                if re.search(
                    r"ROJA|ROJO|RED|AMARILLA|AMARILLO|YELLOW|TARJETA|CARD",
                    item_text,
                ):
                    card_phrase_item = item
                    break

            if card_phrase_item is not None:
                card_y = sum(
                    point[1] for point in card_phrase_item["bbox"]
                ) / len(card_phrase_item["bbox"])

                candidates = []
                for item in items:
                    item_text = re.sub(r"[^A-Z\s]", "", item["text"].upper()).strip()
                    words = item_text.split()
                    item_y = sum(
                        point[1] for point in item["bbox"]
                    ) / len(item["bbox"])
                    if (
                        len(words) >= 2
                        and item_y < card_y
                        and item_text not in {"RMA", "BAR", "LALIGA", "SANTANDER"}
                    ):
                        candidates.append(item_text)

                if candidates:
                    player_name = " ".join(candidates[-1].split())

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

        cards = []
        if red_card:
            cards.append({
                "type": "red",
                "team": team,
                "player": player_name,
            })
        if yellow_card:
            cards.append({
                "type": "yellow",
                "team": team,
                "player": player_name,
            })

        parsed.append({
            "timestamp": timestamp,
            "raw_text": combined_text,
            "score_candidates": scores,
            "clock_candidates": clocks,
            "card_candidates": cards,
        })

    return parsed