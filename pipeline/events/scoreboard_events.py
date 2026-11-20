def extract_scoreboard_events(connection, match_id: str) -> list[dict]:
    rows = connection.execute(
        """
        SELECT observation_id, timestamp, raw_text, home_score,
               away_score, confidence
        FROM scoreboard_observations
        WHERE match_id = ?
        ORDER BY timestamp
        """,
        (match_id,),
    ).fetchall()

    events = []
    previous = None
    stable_states = []

    for index, row in enumerate(rows):
        home = row["home_score"]
        away = row["away_score"]
        if home is None or away is None:
            continue
        if row["confidence"] is not None and row["confidence"] < 0.75:
            continue

        nearby = [
            candidate
            for candidate in rows[max(0, index - 1):index + 2]
            if candidate["home_score"] is not None
            and candidate["away_score"] is not None
            and (candidate["home_score"], candidate["away_score"])
            == (home, away)
        ]
        if len(nearby) >= 1:
            stable_states.append(row)

    deduplicated_states = []
    previous_stable_score = None
    for row in stable_states:
        score = (row["home_score"], row["away_score"])
        if score == previous_stable_score:
            continue
        deduplicated_states.append(row)
        previous_stable_score = score
    stable_states = deduplicated_states

    for row in stable_states:
        home = row["home_score"]
        away = row["away_score"]
        if home is None or away is None:
            continue

        score = (home, away)
        if previous is None:
            previous = score
            continue

        if score != previous:
            home_delta = home - previous[0]
            away_delta = away - previous[1]
            if home_delta > 0 or away_delta > 0:
                team = "home" if home_delta > 0 else "away"
                event_id = f"{match_id}:goal:{row['timestamp']}"
                evidence_id = f"{event_id}:scoreboard:{row['observation_id']}"
                events.append(
                    {
                        "event_id": event_id,
                        "event_type": "goal",
                        "timestamp": row["timestamp"],
                        "title": f"Goal - {team}",
                        "description": f"Score changed from {previous[0]}-{previous[1]} to {home}-{away}.",
                        "confidence": 0.95,
                        "entities": {
                            "team": team,
                            "previous_score": {"home": previous[0], "away": previous[1]},
                            "score": {"home": home, "away": away},
                        },
                        "evidence": [
                            {
                                "evidence_id": evidence_id,
                                "source_type": "scoreboard",
                                "source_id": row["observation_id"],
                                "source_timestamp": row["timestamp"],
                                "source_value": row["raw_text"],
                                "confidence": row["confidence"],
                                "weight": 1.0,
                                "details": {
                                    "previous_score": [previous[0], previous[1]],
                                    "score": [home, away],
                                },
                            }
                        ],
                    }
                )
        previous = score

    card_rows = connection.execute(
        """
        SELECT card_id, timestamp, card_type, team, player_name
        FROM card_events
        WHERE match_id = ?
        ORDER BY timestamp
        """,
        (match_id,),
    ).fetchall()

    seen = set()
    for row in card_rows:
        key = (row["card_type"], row["team"], row["player_name"])
        if key in seen:
            continue
        seen.add(key)

        event_type = f"{row['card_type']}_card"
        event_id = f"{match_id}:{event_type}:{row['timestamp']}"
        evidence_id = f"{event_id}:card:{row['card_id']}"
        player = row["player_name"]
        title = f"{row['card_type'].title()} card"
        if player:
            title += f" - {player}"

        events.append(
            {
                "event_id": event_id,
                "event_type": event_type,
                "timestamp": row["timestamp"],
                "title": title,
                "description": title,
                "confidence": 0.90,
                "entities": {
                    "team": row["team"],
                    "player": player,
                    "card_type": row["card_type"],
                },
                "evidence": [
                    {
                        "evidence_id": evidence_id,
                        "source_type": "scoreboard",
                        "source_id": row["card_id"],
                        "source_timestamp": row["timestamp"],
                        "source_value": row["card_type"],
                        "confidence": 0.90,
                        "weight": 1.0,
                        "details": {
                            "team": row["team"],
                            "player": row["player_name"],
                        },
                    }
                ],
            }
        )

    return sorted(events, key=lambda event: event["timestamp"])
