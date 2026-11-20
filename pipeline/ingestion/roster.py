import csv
import re
from pathlib import Path


def normalize_team_name(name: str) -> str:
    name = re.sub(r"^(?:FC|CF|AC|AFC)\s+", "", name.strip(), flags=re.I)
    name = re.sub(r"\s+FC$", "", name, flags=re.I)
    return name.strip()


def parse_roster_csv(csv_path: str) -> dict:
    path = Path(csv_path)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))

    team_name = None
    match_title = None
    header_index = None

    for index, row in enumerate(rows):
        cleaned = [cell.strip() for cell in row if cell.strip()]
        if not cleaned:
            continue

        if team_name is None:
            team_name = cleaned[0]

        title_match = re.search(
            r"(.+?)\s+\d+\s*[-:]\s*\d+\s+(.+?),",
            ",".join(row),
            re.I,
        )
        if title_match:
            match_title = ",".join(row).strip()

        normalized = [cell.strip().lower() for cell in row]
        if "player" in normalized and (
            "no." in normalized
            or "number" in normalized
            or "shirt" in normalized
        ):
            header_index = index
            break

    if team_name is None:
        team_name = path.stem
    team_name = normalize_team_name(team_name)

    players = []
    if header_index is not None:
        header = [cell.strip().lower() for cell in rows[header_index]]
        for row in rows[header_index + 1:]:
            if len(row) < 2:
                continue
            values = {
                header[index]: row[index].strip()
                for index in range(min(len(header), len(row)))
                if header[index]
            }
            name = (
                values.get("player")
                or values.get("name")
                or values.get("player name")
            )
            if not name:
                continue

            shirt = (
                values.get("no.")
                or values.get("number")
                or values.get("shirt")
                or values.get("shirt number")
            )
            try:
                shirt_number = int(shirt) if shirt else None
            except ValueError:
                shirt_number = None

            players.append(
                {
                    "shirt_number": shirt_number,
                    "name": name,
                    "position": values.get("position"),
                    "role": values.get("role"),
                }
            )

    teams = []
    left_team = None
    right_team = None
    if match_title:
        title_match = re.search(
            r"(.+?)\s+\d+\s*[-:]\s*\d+\s+(.+?),",
            match_title,
            re.I,
        )
        if title_match:
            left_team = normalize_team_name(title_match.group(1))
            right_team = normalize_team_name(title_match.group(2))

    side = None
    if left_team and normalize_team_name(team_name).lower() == left_team.lower():
        side = "home"
    elif right_team and normalize_team_name(team_name).lower() == right_team.lower():
        side = "away"

    teams = [{"name": team_name, "side": side}]

    return {
        "team_name": team_name,
        "match_title": match_title,
        "teams": teams,
        "players": players,
        "source_path": str(path),
    }
