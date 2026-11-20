import difflib
import re
import unicodedata


def normalize_name(name: str) -> str:
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", name)
    text = "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )
    text = text.upper()
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return " ".join(text.split())


def resolve_player_name(
    raw_name: str,
    players: list[dict],
    minimum_ratio: float = 0.78,
) -> dict | None:
    normalized_raw = normalize_name(raw_name)
    if not normalized_raw:
        return None

    candidates = []
    for player in players:
        player_name = player.get("name") or ""
        normalized_player = normalize_name(player_name)
        if not normalized_player:
            continue

        ratio = difflib.SequenceMatcher(
            None,
            normalized_raw,
            normalized_player,
        ).ratio()

        raw_parts = set(normalized_raw.split())
        player_parts = set(normalized_player.split())
        overlap = len(raw_parts & player_parts) / max(
            1,
            len(raw_parts | player_parts),
        )
        score = max(ratio, overlap)
        candidates.append((score, player))

    if not candidates:
        return None

    score, player = max(candidates, key=lambda candidate: candidate[0])
    if score < minimum_ratio:
        return None
    resolved = dict(player)
    resolved["match_confidence"] = round(score, 3)
    return resolved
