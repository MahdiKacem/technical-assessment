import re
from collections import defaultdict
from pipeline.normalization import normalize_name, resolve_player_name


SCORE_PATTERN = re.compile(
    r"(?<!\d)(\d{1,2})(?:\s*[-:]\s*|\s+)(\d{1,2})(?!\d)"
)

CLOCK_PATTERN = re.compile(r"(?<!\d)(\d{1,3}):([0-5]\d)(?!\d)")


def group_observations_by_timestamp(observations: list[dict],) -> dict:
    grouped = defaultdict(list)

    for observation in observations:
        grouped[observation["timestamp"]].append(observation)

    return grouped


def stabilize_score_candidates(
    parsed: list[dict],
    stability_window: float = 2.0,
    minimum_count: int = 2,
) -> list[dict]:
    for item in parsed:
        timestamp = item["timestamp"]
        neighborhood = [
            other
            for other in parsed
            if abs(other["timestamp"] - timestamp) <= stability_window
        ]

        stable_scores = []
        counts = defaultdict(int)
        for neighbor in neighborhood:
            for score in neighbor["score_candidates"]:
                counts[(score["home"], score["away"])] += 1

        for score in item["score_candidates"]:
            key = (score["home"], score["away"])
            if counts[key] >= minimum_count:
                stable_scores.append(score)

        item["score_candidates"] = stable_scores

    return parsed


def parse_scoreboard(
    observations: list[dict],
    team_labels: dict[str, str] | None = None,
    players: list[dict] | None = None,
    stabilize: bool = False,
) -> list[dict]:
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
        team_label_positions = {}
        for item in items:
            text = item["text"].upper()
            center_x = sum(point[0] for point in item["bbox"]) / len(item["bbox"])
            if text == "RMA":
                rma_x = center_x
            elif text == "BAR":
                bar_x = center_x
            team_label_positions[normalize_name(text)] = center_x

        left_team_label = None
        right_team_label = None
        if team_labels:
            left_team_label = team_labels.get("left")
            right_team_label = team_labels.get("right")

        team = None
        card_x = None
        if card_items:
            card_x = sum(
                sum(point[0] for point in item["bbox"]) / len(item["bbox"])
                for item in card_items
            ) / len(card_items)
        if card_x is not None:
            label_x_positions = []
            if left_team_label:
                left_x = team_label_positions.get(normalize_name(left_team_label))
                if left_x is not None:
                    label_x_positions.append((left_x, left_team_label))
            if right_team_label:
                right_x = team_label_positions.get(normalize_name(right_team_label))
                if right_x is not None:
                    label_x_positions.append((right_x, right_team_label))

            if label_x_positions:
                team = min(
                    label_x_positions,
                    key=lambda position: abs(card_x - position[0]),
                )[1]
            elif rma_x is not None and bar_x is not None:
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

        raw_player_name = player_name
        resolved_player = resolve_player_name(player_name, players or [])
        if resolved_player:
            player_name = resolved_player["name"]
        elif players:
            full_text = " ".join(
                item["text"] for item in items
            )
            for player in players:
                candidate = resolve_player_name(
                    full_text,
                    [player],
                    minimum_ratio=0.45,
                )
                if candidate:
                    raw_player_name = full_text
                    player_name = candidate["name"]
                    resolved_player = candidate
                    break

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

    if stabilize:
        return stabilize_score_candidates(parsed)
    return parsed