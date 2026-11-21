from dataclasses import dataclass, field

SENTENCE_END = (".", "?", "!")
MAX_SHIFT_START = 6.0
MAX_TRIM_END = 8.0
MAX_EXTEND_END = 6.0
MIN_LEAD = 2.0
MIN_TAIL = 2.0
EDGE_MARGIN = 0.1


@dataclass
class Sentence:
    start: float
    end: float
    text: str


@dataclass
class CutResult:
    clip_start: float
    clip_end: float
    notes: list[str] = field(default_factory=list)


def build_sentences(segments: list[dict], max_gap: float = 1.0) -> list[Sentence]:
    sentences: list[Sentence] = []
    current: Sentence | None = None
    for seg in sorted(segments, key=lambda s: s["start_time"]):
        text = seg["text"].strip()
        if not text:
            continue
        if current is not None and seg["start_time"] - current.end > max_gap:
            sentences.append(current)
            current = None
        if current is None:
            current = Sentence(seg["start_time"], seg["end_time"], text)
        else:
            current.end = seg["end_time"]
            current.text = f"{current.text} {text}"
        if text.endswith(SENTENCE_END):
            sentences.append(current)
            current = None
    if current is not None:
        sentences.append(current)
    return sentences


def _inside(t: float, sentences: list[Sentence]) -> Sentence | None:
    for s in sentences:
        if s.start + EDGE_MARGIN < t < s.end - EDGE_MARGIN:
            return s
    return None


def snap_cuts(
    clip_start: float,
    clip_end: float,
    goal_time: float,
    sentences: list[Sentence],
    hard_min: float | None = None,
    hard_max: float | None = None,
) -> CutResult:
    result = CutResult(clip_start, clip_end)
    starts = sorted({s.start for s in sentences})
    ends = sorted({s.end for s in sentences})

    sentence = _inside(clip_start, sentences)
    if sentence is not None:
        lo = max(clip_start - MAX_SHIFT_START, hard_min if hard_min is not None else -1e9)
        hi = min(clip_start + MAX_SHIFT_START, goal_time - MIN_LEAD)
        options = [t for t in starts if lo <= t <= hi]
        if options:
            best = min(options, key=lambda t: (abs(t - clip_start), t))
            result.clip_start = best
            result.notes.append(
                f"start moved {best - clip_start:+.2f}s to sentence boundary "
                f"(was inside: \"{sentence.text[:60]}\")")
        else:
            result.notes.append(f"start is mid-sentence, no boundary within limits: "
                                f"\"{sentence.text[:60]}\"")

    sentence = _inside(clip_end, sentences)
    if sentence is not None:
        lo = max(clip_end - MAX_TRIM_END, goal_time + MIN_TAIL)
        hi = clip_end + MAX_EXTEND_END
        if hard_max is not None:
            hi = min(hi, hard_max)
        options = [t for t in ends if lo <= t <= hi]
        if options:
            best = min(options, key=lambda t: (abs(t - clip_end), -t))
            result.clip_end = best
            reason = ""
            if hard_max is not None and sentence.end > hard_max:
                reason = f"; sentence runs into the replay at {hard_max:.2f}s"
            result.notes.append(
                f"end moved {best - clip_end:+.2f}s to sentence boundary "
                f"(was inside: \"{sentence.text[:60]}\"{reason})")
        else:
            result.notes.append(f"end is mid-sentence, no boundary within limits: "
                                f"\"{sentence.text[:60]}\"")
    return result


def load_sentences(connection, match_id: str, start: float, end: float) -> list[Sentence]:
    rows = connection.execute(
        "SELECT start_time, end_time, text FROM transcriptions WHERE match_id = ?"
        " AND end_time >= ? AND start_time <= ? ORDER BY start_time",
        (match_id, start - 30.0, end + 30.0),
    ).fetchall()
    return build_sentences([dict(r) for r in rows])
