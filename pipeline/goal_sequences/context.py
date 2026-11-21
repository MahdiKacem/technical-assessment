import json
from dataclasses import dataclass, field

DEFAULT_BEFORE = 45.0
DEFAULT_AFTER = 30.0


@dataclass
class EvidencePoint:
    timestamp: float
    kind: str
    text: str
    weight: float


@dataclass
class GoalContext:
    event_id: str
    match_id: str
    anchor: float
    window_start: float
    window_end: float
    description: str
    evidence: list[EvidencePoint] = field(default_factory=list)
    shot_cuts: list[float] = field(default_factory=list)

    def relevance_points(self) -> list[EvidencePoint]:
        return [e for e in self.evidence if e.kind != "shot_cut"]


def load_goal_context(
    connection,
    event_id: str,
    before: float = DEFAULT_BEFORE,
    after: float = DEFAULT_AFTER,
) -> GoalContext:
    event = connection.execute(
        "SELECT e.*, m.duration_seconds FROM events e JOIN matches m USING (match_id)"
        " WHERE e.event_id = ?",
        (event_id,),
    ).fetchone()
    if event is None:
        raise ValueError(f"Unknown event: {event_id}")

    anchor = float(event["timestamp"])
    start = max(0.0, anchor - before)
    end = min(float(event["duration_seconds"]), anchor + after)
    match_id = event["match_id"]
    entities = json.loads(event["entities_json"] or "{}")
    description = event["description"] or event["title"] or event["event_type"]
    if entities.get("score"):
        description += f" (score after: {entities['score']})"

    ctx = GoalContext(event_id, match_id, anchor, start, end, description)

    for row in connection.execute(
        "SELECT timestamp, z_score FROM audio_peaks WHERE match_id = ?"
        " AND timestamp BETWEEN ? AND ? ORDER BY timestamp",
        (match_id, start, end),
    ):
        ctx.evidence.append(EvidencePoint(
            row["timestamp"], "audio_peak", f"loudness peak z={row['z_score']:.1f}",
            weight=min(1.0, row["z_score"] / 4.0),
        ))

    for row in connection.execute(
        "SELECT start_time, end_time, text FROM transcriptions WHERE match_id = ?"
        " AND end_time >= ? AND start_time <= ? ORDER BY start_time",
        (match_id, start, end),
    ):
        ctx.evidence.append(EvidencePoint(
            row["start_time"], "transcript", row["text"].strip(), weight=0.4,
        ))

    previous = None
    for row in connection.execute(
        "SELECT timestamp, home_score, away_score FROM scoreboard_observations"
        " WHERE match_id = ? AND timestamp BETWEEN ? AND ?"
        " AND home_score IS NOT NULL ORDER BY timestamp",
        (match_id, start, end),
    ):
        score = (row["home_score"], row["away_score"])
        if previous is not None and score != previous:
            ctx.evidence.append(EvidencePoint(
                row["timestamp"], "scoreboard",
                f"scoreboard first shows {score[0]}-{score[1]} (was {previous[0]}-{previous[1]})",
                weight=1.0,
            ))
        previous = score

    ctx.shot_cuts = [
        row["start_time"]
        for row in connection.execute(
            "SELECT start_time FROM shots WHERE match_id = ?"
            " AND start_time > ? AND start_time < ? ORDER BY start_time",
            (match_id, start, end),
        )
    ]
    ctx.evidence.sort(key=lambda e: e.timestamp)
    return ctx


def candidate_timestamps(ctx: GoalContext, step: float = 1.0) -> list[float]:
    times = []
    t = ctx.window_start
    while t <= ctx.window_end:
        times.append(t)
        t += step
    times.extend(e.timestamp for e in ctx.evidence)
    times.extend(c + 0.5 for c in ctx.shot_cuts)
    times = [min(max(t, ctx.window_start), ctx.window_end) for t in times]
    return sorted({round(t * 4) / 4 for t in times})
