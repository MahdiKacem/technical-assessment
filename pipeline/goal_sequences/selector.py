import math

import numpy as np

from pipeline.goal_sequences.context import GoalContext
from pipeline.goal_sequences.frames import Frame

W_EVENT, W_TEMPORAL, W_NOVELTY = 0.35, 0.40, 0.25
RELEVANCE_SIGMA = 4.0

PHASES = [
    ("pre", -math.inf, -10.0, 0.45),
    ("around", -10.0, 3.0, 0.25),
    ("post", 3.0, math.inf, 0.30),
]


def score_relevance(frames: list[Frame], ctx: GoalContext) -> None:
    points = ctx.relevance_points()
    for frame in frames:
        frame.relevance = sum(
            p.weight * math.exp(-((frame.timestamp - p.timestamp) ** 2) / (2 * RELEVANCE_SIGMA ** 2))
            for p in points
        )
    top = max((f.relevance for f in frames), default=0.0)
    if top > 0:
        for frame in frames:
            frame.relevance /= top


def _cos(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


def greedy_select(candidates: list[Frame], budget: int, span: tuple[float, float],
                  already: list[Frame]) -> list[Frame]:
    selected: list[Frame] = []
    pool = list(candidates)
    length = max(span[1] - span[0], 1e-6)
    ideal_gap = length / max(budget, 1)
    while pool and len(selected) < budget:
        chosen = already + selected
        best, best_score = None, -math.inf
        for frame in pool:
            if chosen:
                gap = min(abs(frame.timestamp - c.timestamp) for c in chosen)
                coverage = min(1.0, gap / ideal_gap)
                novelty = 1.0 - max(_cos(frame.feature, c.feature) for c in chosen)
                novelty = max(0.0, min(1.0, novelty * 2.0))
            else:
                coverage, novelty = 1.0, 1.0
            score = W_EVENT * frame.relevance + W_TEMPORAL * coverage + W_NOVELTY * novelty
            if score > best_score:
                best, best_score = frame, score
        selected.append(best)
        pool.remove(best)
    return selected


def select_frames(frames: list[Frame], ctx: GoalContext, budget: int = 18) -> list[Frame]:
    if not frames:
        return []
    by_time = sorted(frames, key=lambda f: f.timestamp)
    forced = {id(by_time[0]): by_time[0], id(by_time[-1]): by_time[-1]}
    strongest = max(ctx.relevance_points(), key=lambda p: p.weight, default=None)
    if strongest is not None:
        nearest = min(by_time, key=lambda f: abs(f.timestamp - strongest.timestamp))
        forced[id(nearest)] = nearest
    selected = list(forced.values())

    remaining = max(0, budget - len(selected))
    for name, lo, hi, share in PHASES:
        start, end = ctx.anchor + lo, ctx.anchor + hi
        phase_frames = [f for f in by_time if start <= f.timestamp < end and id(f) not in forced]
        if not phase_frames:
            continue
        span = (max(start, ctx.window_start), min(end, ctx.window_end))
        picked = greedy_select(phase_frames, round(remaining * share), span, selected)
        for frame in picked:
            frame.meta["phase"] = name
        selected.extend(picked)

    return sorted(selected, key=lambda f: f.timestamp)
