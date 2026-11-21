import hashlib
import json
import os
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from pipeline.goal_sequences.context import GoalContext

ALLOWED_MODELS = {"gemini-3.8-flash", "gemini-4-argon"}
DEFAULT_MODEL = "gemini-3.8-flash"
PROMPT_VERSION = "goal-seq-v2"
STAGE = "goal_sequence"

Label = Literal["buildup", "goal", "celebration", "reaction", "replay", "other_play",
                "stoppage", "unclear"]


class FrameLabels(BaseModel):
    labels: list[Label]
    notes: str


SYSTEM_INSTRUCTION = """You label still frames from a football broadcast around one goal.
Frames are in time order; each has its video timestamp. Give exactly one label per frame, in the same order.
Labels:
- buildup: live play that is part of the attacking move ending in this goal. For a set piece (corner, free kick), buildup starts when the ball is kicked; players waiting for it are stoppage.
- goal: the shot that scores, or the ball going into the net, in live play.
- celebration: players celebrating this goal, live (not slow motion).
- reaction: other live shots reacting to this goal: fans, either bench or coach, goalkeeper, scorer name graphic.
- replay: any re-showing of earlier action: slow motion, replay graphic or wipe, a second angle of the goal.
- other_play: live play that is not part of the scoring move (earlier possession, the other team attacking).
- stoppage: no live play and not reacting to the goal: restart set-up, kick-off, players walking back to position.
- unclear: cannot tell from this frame.
Use the timeline evidence (commentary, loudness, scoreboard) only as context; label what each frame shows.
notes: at most 25 words, only if something is ambiguous."""


def resolve_model(model: str | None) -> str:
    model = model or os.getenv("GEMINI_PERCEPTION_MODEL", DEFAULT_MODEL)
    if model not in ALLOWED_MODELS:
        raise ValueError(f"Model '{model}' not allowed; use one of {sorted(ALLOWED_MODELS)}.")
    return model


def _image_part(path: str):
    from google.genai import types

    if Path(path).suffix.lower() not in {".jpg", ".jpeg"}:
        raise ValueError(f"Only still JPEG frames may be sent, got {path}")
    return types.Part.from_bytes(data=Path(path).read_bytes(), mime_type="image/jpeg")


def build_context_text(ctx: GoalContext, extra: str = "") -> str:
    lines = [
        f"Event: {ctx.description}. First evidence of the goal at t={ctx.anchor:.1f}s.",
        f"Window: t={ctx.window_start:.1f}s to t={ctx.window_end:.1f}s.",
        "Timeline evidence:",
    ]
    for e in ctx.evidence:
        lines.append(f"  t={e.timestamp:.1f}s {e.kind}: {e.text[:120]}")
    if ctx.shot_cuts:
        lines.append("Camera cuts at: " + ", ".join(f"{c:.1f}" for c in ctx.shot_cuts))
    if extra:
        lines.append(extra)
    return "\n".join(lines)


def request_hash(model: str, context_text: str, frames: list) -> str:
    payload = json.dumps([model, PROMPT_VERSION, context_text,
                          [(f.timestamp, f.content_hash) for f in frames]])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _record_usage(connection, **fields) -> None:
    columns = ", ".join(fields)
    connection.execute(
        f"INSERT INTO llm_usage ({columns}) VALUES ({', '.join('?' for _ in fields)})",
        tuple(fields.values()),
    )
    connection.commit()


def label_frames(
    connection,
    ctx: GoalContext,
    frames: list,
    round_index: int,
    client=None,
    model: str | None = None,
    thinking_level: str = "LOW",
    media_resolution: str = "MEDIA_RESOLUTION_LOW",
    extra_context: str = "",
) -> tuple[list[str], str, dict]:
    model = resolve_model(model)
    context_text = build_context_text(ctx, extra_context)
    key = request_hash(model, context_text, frames)
    base_log = dict(stage=STAGE, match_id=ctx.match_id, ref_id=ctx.event_id,
                    model_name=model, prompt_version=PROMPT_VERSION)

    cached = connection.execute(
        "SELECT response_json FROM frame_analyses WHERE analysis_id = ?", (key,)
    ).fetchone()
    if cached:
        result = FrameLabels.model_validate_json(cached["response_json"])
        _record_usage(connection, usage_id=f"{key[:16]}:usage:{time.time_ns()}", **base_log,
                      input_tokens=0, output_tokens=0, latency_ms=0, cache_hit=1, success=1)
        return list(result.labels), result.notes, {"cache_hit": True, "input_tokens": 0,
                                                   "output_tokens": 0, "latency_ms": 0}

    from google.genai import types

    if client is None:
        from pipeline.embeddings import make_gemini_client
        client = make_gemini_client()

    contents = [context_text, f"{len(frames)} frames follow."]
    for i, frame in enumerate(frames):
        contents.append(f"Frame {i + 1} | t={frame.timestamp:.2f}s")
        contents.append(_image_part(frame.path))

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        response_mime_type="application/json",
        response_schema=FrameLabels,
        thinking_config=types.ThinkingConfig(thinking_level=thinking_level),
        media_resolution=media_resolution,
    )

    started = time.perf_counter()
    try:
        response = client.models.generate_content(model=model, contents=contents, config=config)
    except Exception as error:
        _record_usage(connection, usage_id=f"{key[:16]}:usage:{time.time_ns()}", **base_log,
                      latency_ms=int((time.perf_counter() - started) * 1000), cache_hit=0,
                      success=0, error=f"{type(error).__name__}: {error}"[:500])
        raise
    latency_ms = int((time.perf_counter() - started) * 1000)

    meta = response.usage_metadata
    input_tokens = meta.prompt_token_count or 0
    output_tokens = (meta.candidates_token_count or 0) + (meta.thoughts_token_count or 0)
    result = response.parsed
    ok = isinstance(result, FrameLabels) and len(result.labels) == len(frames)
    _record_usage(connection, usage_id=f"{key[:16]}:usage:{time.time_ns()}", **base_log,
                  input_tokens=input_tokens, output_tokens=output_tokens,
                  latency_ms=latency_ms, cache_hit=0, success=1 if ok else 0,
                  error=None if ok else f"bad response: {str(response.text)[:300]}",
                  stop_reason=str(response.candidates[0].finish_reason) if response.candidates else None)
    if not ok:
        raise RuntimeError("Gemini returned labels that do not match the frames sent.")

    connection.execute(
        "INSERT INTO frame_analyses (analysis_id, event_id, round_index, model_name,"
        " prompt_version, context_text, frames_json, response_json, input_tokens,"
        " output_tokens, thoughts_tokens, latency_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (key, ctx.event_id, round_index, model, PROMPT_VERSION, context_text,
         json.dumps([{"timestamp": f.timestamp, "path": f.path, "sha256": f.content_hash}
                     for f in frames]),
         result.model_dump_json(), input_tokens, meta.candidates_token_count or 0,
         meta.thoughts_token_count or 0, latency_ms),
    )
    connection.commit()
    return list(result.labels), result.notes, {
        "cache_hit": False, "input_tokens": input_tokens, "output_tokens": output_tokens,
        "thoughts_tokens": meta.thoughts_token_count or 0, "latency_ms": latency_ms,
    }
