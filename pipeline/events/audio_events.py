import json


def extract_audio_events(connection, match_id: str) -> list[dict]:
    rows = connection.execute(
        """
        SELECT peak_id, timestamp, rms, z_score
        FROM audio_peaks
        WHERE match_id = ?
        ORDER BY timestamp
        """,
        (match_id,),
    ).fetchall()

    events = []
    for row in rows:
        event_id = f"{match_id}:crowd_reaction:{row['timestamp']}"
        evidence_id = f"{event_id}:audio:{row['peak_id']}"
        confidence = min(0.85, 0.5 + float(row["z_score"]) * 0.08)
        events.append(
            {
                "event_id": event_id,
                "event_type": "crowd_reaction",
                "timestamp": row["timestamp"],
                "title": "Crowd reaction",
                "description": "Audio peak detected in the match audio.",
                "confidence": confidence,
                "entities": {},
                "evidence": [
                    {
                        "evidence_id": evidence_id,
                        "source_type": "audio",
                        "source_id": row["peak_id"],
                        "source_timestamp": row["timestamp"],
                        "source_value": json.dumps(
                            {"rms": row["rms"], "z_score": row["z_score"]}
                        ),
                        "confidence": confidence,
                        "weight": 0.6,
                        "details": {
                            "rms": row["rms"],
                            "z_score": row["z_score"],
                        },
                    }
                ],
            }
        )

    return events
