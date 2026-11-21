import json
import re
import time
from pathlib import Path

from pipeline.editing.commentary import load_sentences, snap_cuts
from pipeline.goal_sequences import analyzer
from pipeline.goal_sequences.boundaries import Boundaries, derive_boundaries
from pipeline.goal_sequences.context import GoalContext, candidate_timestamps, load_goal_context
from pipeline.goal_sequences.frames import (
    FEATURE_EXTRACTOR,
    compute_features,
    extract_frames,
    save_frames,
)
from pipeline.goal_sequences.selector import greedy_select, score_relevance, select_frames

DEFAULT_BUDGET = 18
REFINE_MAX_WIDTH = 3.0
REFINE_EXTEND = 20.0
MAX_REFINE_ROUNDS = 3
MAX_EXTENSION_BEFORE = 90.0
MAX_EXTENSION_AFTER = 90.0
FALLBACK_BEFORE, FALLBACK_AFTER = 20.0, 10.0


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name)


def _grid(start: float, end: float, step: float) -> list[float]:
    times, t = [], start
    while t <= end + 1e-6:
        times.append(round(t * 4) / 4)
        t += step
    return sorted(set(times))


def _refinement_ranges(b: Boundaries, earliest: float, latest: float, duration: float,
                       anchor: float) -> list[tuple[str, float, float, int]]:
    ranges = []
    if b.buildup_start is not None:
        br = b.buildup_start
        if br.open and earliest > max(0.0, anchor - MAX_EXTENSION_BEFORE):
            lo = max(0.0, anchor - MAX_EXTENSION_BEFORE, earliest - REFINE_EXTEND)
            ranges.append(("buildup_start", lo, earliest - 0.5, 5))
        elif not br.open and br.width > REFINE_MAX_WIDTH:
            ranges.append(("buildup_start", br.outside + 0.25, br.inside - 0.25, 4))
    if b.celebration_end is not None:
        br = b.celebration_end
        if br.open and latest < min(duration, anchor + MAX_EXTENSION_AFTER):
            hi = min(duration, anchor + MAX_EXTENSION_AFTER, latest + REFINE_EXTEND)
            ranges.append(("celebration_end", latest + 0.5, hi, 6))
        elif not br.open and br.width > REFINE_MAX_WIDTH:
            ranges.append(("celebration_end", br.inside + 0.25, br.outside - 0.25, 4))
    if b.goal is not None and not b.goal.open and b.goal.width > REFINE_MAX_WIDTH:
        ranges.append(("goal", b.goal.outside + 0.25, b.goal.inside - 0.25, 3))
    return [r for r in ranges if r[2] > r[1]]


def extract_goal_sequence(
    connection,
    cfg,
    event_id: str,
    client=None,
    model: str | None = None,
    budget: int = DEFAULT_BUDGET,
    refine: bool = True,
    thinking_level: str = "LOW",
    media_resolution: str = "MEDIA_RESOLUTION_LOW",
) -> dict:
    started = time.perf_counter()
    model = analyzer.resolve_model(model)
    ctx = load_goal_context(connection, event_id)
    duration = connection.execute(
        "SELECT duration_seconds FROM matches WHERE match_id = ?", (ctx.match_id,)
    ).fetchone()[0]
    out_dir = Path(cfg.artifact_dir) / "goal_sequences" / _safe(event_id)

    t0 = time.perf_counter()
    candidates = extract_frames(cfg.video_path, candidate_timestamps(ctx))
    compute_features(candidates)
    score_relevance(candidates, ctx)
    selected = select_frames(candidates, ctx, budget=budget)
    save_frames(selected, str(out_dir / "round0"))
    local_seconds = time.perf_counter() - t0

    labels, notes, usage0 = analyzer.label_frames(
        connection, ctx, selected, 0, client=client, model=model,
        thinking_level=thinking_level, media_resolution=media_resolution,
    )
    labelled = [(f.timestamp, lab, 0, f.path) for f, lab in zip(selected, labels)]
    boundaries = derive_boundaries([(t, lab) for t, lab, _, _ in labelled], REFINE_MAX_WIDTH)
    usages, all_notes = [usage0], [notes] if notes else []

    rounds = 1
    sent = list(selected)
    while refine and rounds <= MAX_REFINE_ROUNDS and boundaries.status != "no_goal_frame":
        times = [t for t, _, _, _ in labelled]
        ranges = _refinement_ranges(boundaries, min(times), max(times), duration, ctx.anchor)
        if not ranges:
            break
        new_frames = []
        for name, lo, hi, n in ranges:
            pool = extract_frames(cfg.video_path, _grid(lo, hi, 0.5))
            pool = [f for f in pool if all(abs(f.timestamp - s.timestamp) > 0.2 for s in sent)]
            compute_features(pool)
            for frame in pool:
                frame.relevance = 0.0
                frame.meta["refines"] = name
            new_frames.extend(greedy_select(pool, n, (lo, hi), sent + new_frames))
        new_frames.sort(key=lambda f: f.timestamp)
        if not new_frames:
            break
        save_frames(new_frames, str(out_dir / f"round{rounds}"))
        known = "; ".join(f"t={t:.1f}s {lab}" for t, lab, _, _ in sorted(labelled))
        extra = ("Refinement: these frames fill gaps or extend beyond frames already "
                 f"labelled as: {known}")
        labels_r, notes_r, usage_r = analyzer.label_frames(
            connection, ctx, new_frames, rounds, client=client, model=model,
            thinking_level=thinking_level, media_resolution=media_resolution,
            extra_context=extra,
        )
        labelled += [(f.timestamp, lab, rounds, f.path) for f, lab in zip(new_frames, labels_r)]
        sent += new_frames
        boundaries = derive_boundaries([(t, lab) for t, lab, _, _ in labelled], REFINE_MAX_WIDTH)
        usages.append(usage_r)
        if notes_r:
            all_notes.append(notes_r)
        rounds += 1

    if boundaries.status == "no_goal_frame":
        status = "fallback"
        buildup_start = max(0.0, ctx.anchor - FALLBACK_BEFORE)
        goal_time = ctx.anchor
        celebration_end = min(duration, ctx.anchor + FALLBACK_AFTER)
    else:
        status = boundaries.status
        goal_time = boundaries.goal.estimate
        buildup_start = boundaries.buildup_start.estimate
        celebration_end = (boundaries.celebration_end.estimate
                           if boundaries.celebration_end else goal_time + FALLBACK_AFTER)

    replays = boundaries.replays
    hard_max = min((s for s, _ in replays if s > goal_time), default=None)
    hard_min = max((e for _, e in replays if e < buildup_start), default=None)
    if hard_min is not None:
        hard_min += 0.5
    sentences = load_sentences(connection, ctx.match_id, buildup_start, celebration_end)
    cuts = snap_cuts(buildup_start, celebration_end, goal_time, sentences,
                     hard_min=hard_min, hard_max=hard_max)

    result = {
        "sequence_id": f"{event_id}:sequence",
        "clip_start": round(cuts.clip_start, 2),
        "clip_end": round(cuts.clip_end, 2),
        "cut_notes": cuts.notes,
        "event_id": event_id,
        "match_id": ctx.match_id,
        "status": status,
        "buildup_start": round(buildup_start, 2),
        "goal_time": round(goal_time, 2),
        "celebration_end": round(celebration_end, 2),
        "brackets": {
            name: (getattr(boundaries, name).as_dict() if getattr(boundaries, name) else None)
            for name in ("buildup_start", "goal", "celebration_end")
        },
        "replays": boundaries.replays,
        "issues": boundaries.issues,
        "notes": all_notes,
        "frame_labels": [{"t": t, "label": lab, "round": r, "path": p}
                         for t, lab, r, p in sorted(labelled)],
        "model": model,
        "prompt_version": analyzer.PROMPT_VERSION,
        "feature_extractor": FEATURE_EXTRACTOR,
        "budget": budget,
        "rounds": rounds,
        "frames_sent": len(labelled),
        "candidates_extracted": len(candidates),
        "local_seconds": round(local_seconds, 2),
        "total_seconds": round(time.perf_counter() - started, 2),
        "input_tokens": sum(u["input_tokens"] for u in usages),
        "output_tokens": sum(u["output_tokens"] for u in usages),
        "api_ms": sum(u["latency_ms"] for u in usages),
        "cache_hits": sum(1 for u in usages if u["cache_hit"]),
    }
    persist_goal_sequence(connection, result)
    return result


def persist_goal_sequence(connection, r: dict) -> None:
    connection.execute(
        """
        INSERT INTO goal_sequences (
            sequence_id, event_id, match_id, status, buildup_start, goal_time,
            celebration_end, brackets_json, replays_json, issues_json, frame_labels_json,
            model_name, prompt_version, feature_extractor, details_json,
            clip_start, clip_end, cut_notes_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(sequence_id) DO UPDATE SET
            status = excluded.status, buildup_start = excluded.buildup_start,
            goal_time = excluded.goal_time, celebration_end = excluded.celebration_end,
            clip_start = excluded.clip_start, clip_end = excluded.clip_end,
            cut_notes_json = excluded.cut_notes_json,
            brackets_json = excluded.brackets_json, replays_json = excluded.replays_json,
            issues_json = excluded.issues_json, frame_labels_json = excluded.frame_labels_json,
            model_name = excluded.model_name, prompt_version = excluded.prompt_version,
            feature_extractor = excluded.feature_extractor, details_json = excluded.details_json,
            created_at = CURRENT_TIMESTAMP
        """,
        (r["sequence_id"], r["event_id"], r["match_id"], r["status"], r["buildup_start"],
         r["goal_time"], r["celebration_end"], json.dumps(r["brackets"]),
         json.dumps(r["replays"]), json.dumps(r["issues"]), json.dumps(r["frame_labels"]),
         r["model"], r["prompt_version"], r["feature_extractor"],
         json.dumps({k: r[k] for k in ("notes", "budget", "rounds", "frames_sent",
                                       "candidates_extracted", "local_seconds", "total_seconds",
                                       "input_tokens", "output_tokens", "api_ms", "cache_hits")}),
         r["clip_start"], r["clip_end"], json.dumps(r["cut_notes"])),
    )
    connection.commit()


def goal_event_ids(connection, match_id: str) -> list[str]:
    return [
        row["event_id"]
        for row in connection.execute(
            "SELECT event_id FROM events WHERE match_id = ? AND event_type = 'goal'"
            " AND json_extract(entities_json, '$.resolution_status') IN ('confirmed', 'likely')"
            " ORDER BY timestamp",
            (match_id,),
        )
    ]
