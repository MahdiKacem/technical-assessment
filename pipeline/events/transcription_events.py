import re


NEAR_MISS_PATTERN = re.compile(
    r"\b(?:"
    r"near miss|what a miss|wide of|just wide|(?:shot|effort|strike|header|attempt|dragging it|whistled).{0,30}\bwide\b|"
    r"off target|over (?:the )?crossbar|"
    r"hit(?:s)? (?:the )?(?:post|crossbar)|off the (?:post|crossbar)|"
    r"(?:well )?saved|save(?:d)? by|denied|blasts? (?:it )?over"
    r")\b",
    re.I,
)

NEAR_MISS_FALSE_POSITIVE_PATTERN = re.compile(
    r"\b(?:ball (?:is )?out wide|pass(?:ed)? out wide|get(?:s)? the ball out wide|"
    r"wide to|build(?:s)?(?: it)? wide|chance|counterattack)\b",
    re.I,
)


TRANSCRIPTION_PATTERNS = (
    ("near_miss", NEAR_MISS_PATTERN),
    ("goal", re.compile(r"\b(?:goal|scores?|header|equalizes?|levels?)\b", re.I)),
    ("red_card", re.compile(r"\b(?:red card|sent off|dismissed)\b", re.I)),
    ("yellow_card", re.compile(r"\b(?:yellow card|booked|caution)\b", re.I)),
    ("substitution", re.compile(r"\b(?:substitution|replaces?|comes on|comes off)\b", re.I)),
    ("var", re.compile(r"\b(?:var|video review|penalty review)\b", re.I)),
)


def extract_transcription_events(connection, match_id: str) -> list[dict]:
    rows = connection.execute(
        """
        SELECT segment_id, start_time, end_time, text
        FROM transcriptions
        WHERE match_id = ?
        ORDER BY start_time
        """,
        (match_id,),
    ).fetchall()

    events = []
    seen = set()

    for row in rows:
        is_near_miss = (
            bool(NEAR_MISS_PATTERN.search(row["text"]))
            and not bool(NEAR_MISS_FALSE_POSITIVE_PATTERN.search(row["text"]))
        )

        for event_type, pattern in TRANSCRIPTION_PATTERNS:
            if not pattern.search(row["text"]):
                continue
            if is_near_miss and event_type == "goal":
                continue

            key = (event_type, round(row["start_time"], 1))
            if key in seen:
                continue
            seen.add(key)

            timestamp = (row["start_time"] + row["end_time"]) / 2
            event_id = f"{match_id}:{event_type}:{timestamp}"
            evidence_id = f"{event_id}:transcription:{row['segment_id']}"
            events.append(
                {
                    "event_id": event_id,
                    "event_type": event_type,
                    "timestamp": timestamp,
                    "title": event_type.replace("_", " ").title(),
                    "description": row["text"],
                    "confidence": 0.65,
                    "entities": {},
                    "evidence": [
                        {
                            "evidence_id": evidence_id,
                            "source_type": "transcription",
                            "source_id": row["segment_id"],
                            "source_timestamp": timestamp,
                            "source_value": row["text"],
                            "confidence": 0.65,
                            "weight": 0.7,
                            "details": {
                                "start_time": row["start_time"],
                                "end_time": row["end_time"],
                                "matched_type": event_type,
                            },
                        }
                    ],
                }
            )

    return sorted(events, key=lambda event: event["timestamp"])
