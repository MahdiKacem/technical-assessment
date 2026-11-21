from dataclasses import dataclass, field

WILDCARD = {"unclear"}
CELEBRATION_SEQUENCE = {"celebration", "reaction"}


@dataclass
class Bracket:
    outside: float | None
    inside: float

    @property
    def open(self) -> bool:
        return self.outside is None

    @property
    def width(self) -> float:
        return float("inf") if self.outside is None else abs(self.inside - self.outside)

    @property
    def estimate(self) -> float:
        return self.inside if self.outside is None else (self.inside + self.outside) / 2

    def as_dict(self) -> dict:
        return {"outside": self.outside, "inside": self.inside,
                "estimate": round(self.estimate, 2), "open": self.open}


@dataclass
class Boundaries:
    status: str
    goal: Bracket | None = None
    buildup_start: Bracket | None = None
    celebration_end: Bracket | None = None
    replays: list[tuple[float, float]] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


def derive_boundaries(labelled: list[tuple[float, str]], max_width: float = 3.0) -> Boundaries:
    labelled = sorted(labelled)
    times = [t for t, _ in labelled]
    labels = [lab for _, lab in labelled]

    replays, run_start = [], None
    for i, lab in enumerate(labels):
        if lab == "replay" and run_start is None:
            run_start = i
        if run_start is not None and (lab != "replay" or i == len(labels) - 1):
            end = i if lab == "replay" else i - 1
            replays.append((times[run_start], times[end]))
            run_start = None

    goal_idx = next((i for i, lab in enumerate(labels) if lab == "goal"), None)
    if goal_idx is None:
        cel = next((i for i, lab in enumerate(labels) if lab == "celebration"), None)
        if cel is None or cel == 0 or labels[cel - 1] not in {"buildup"}:
            return Boundaries(status="no_goal_frame", replays=replays,
                              issues=["no live goal frame and no buildup->celebration transition"])
        goal = Bracket(outside=times[cel - 1], inside=times[cel])
        goal_idx = cel - 1
    else:
        goal = Bracket(outside=times[goal_idx - 1] if goal_idx > 0 else None,
                       inside=times[goal_idx])

    i = goal_idx
    first_buildup = goal_idx
    while i - 1 >= 0 and labels[i - 1] in {"buildup", "goal"} | WILDCARD:
        i -= 1
        if labels[i] == "buildup":
            first_buildup = i
    outside = times[first_buildup - 1] if first_buildup > 0 else None
    buildup = Bracket(outside=outside, inside=times[first_buildup])

    j = goal_idx
    last_cel = None
    while j + 1 < len(labels) and labels[j + 1] in CELEBRATION_SEQUENCE | {"goal"} | WILDCARD:
        j += 1
        if labels[j] in CELEBRATION_SEQUENCE:
            last_cel = j

    issues = []
    celebration = None
    if last_cel is None:
        issues.append("no celebration frames after the goal")
    else:
        nxt = last_cel + 1
        celebration = Bracket(outside=times[nxt] if nxt < len(times) else None,
                              inside=times[last_cel])

    if first_buildup == goal_idx:
        issues.append("no buildup frames before the goal")
    for name, bracket in [("goal", goal), ("buildup_start", buildup),
                          ("celebration_end", celebration)]:
        if bracket is None:
            continue
        if bracket.open:
            issues.append(f"{name} reaches the window edge")
        elif bracket.width > max_width:
            issues.append(f"{name} bracket {bracket.width:.1f}s wide")

    return Boundaries(status="uncertain" if issues else "ok", goal=goal,
                      buildup_start=buildup, celebration_end=celebration,
                      replays=replays, issues=issues)
