from types import SimpleNamespace

import numpy as np
import pytest

from pipeline.database import get_connection, initialize_database
from pipeline.goal_sequences import analyzer
from pipeline.goal_sequences.boundaries import derive_boundaries
from pipeline.goal_sequences.context import EvidencePoint, GoalContext, candidate_timestamps
from pipeline.goal_sequences.frames import Frame, compute_features, save_frames
from pipeline.goal_sequences.selector import score_relevance, select_frames


def _labels(pairs):
    return [(float(t), lab) for t, lab in pairs]


def test_boundaries_from_labels_with_replay_after_celebration():
    b = derive_boundaries(_labels([
        (0, "other_play"), (3, "buildup"), (5, "buildup"), (7, "unclear"), (8, "goal"),
        (10, "celebration"), (12, "celebration"), (14, "replay"), (16, "replay"), (18, "stoppage"),
    ]))
    assert b.status == "ok"
    assert (b.buildup_start.outside, b.buildup_start.inside) == (0.0, 3.0)
    assert b.goal.inside == 8.0
    assert (b.celebration_end.inside, b.celebration_end.outside) == (12.0, 14.0)
    assert b.replays == [(14.0, 16.0)]


def test_open_and_wide_brackets_are_uncertain():
    b = derive_boundaries(_labels([
        (0, "buildup"), (4, "buildup"), (6, "goal"), (8, "celebration"), (20, "stoppage"),
    ]))
    assert b.status == "uncertain"
    assert b.buildup_start.open
    assert any("buildup_start reaches the window edge" in i for i in b.issues)
    assert any("celebration_end bracket 12.0s wide" in i for i in b.issues)


def test_reaction_shots_extend_celebration_until_replay():
    b = derive_boundaries(_labels([
        (0, "buildup"), (2, "goal"), (4, "celebration"), (6, "reaction"),
        (8, "unclear"), (10, "reaction"), (12, "replay"),
    ]))
    assert (b.celebration_end.inside, b.celebration_end.outside) == (10.0, 12.0)


def test_celebration_still_going_at_last_frame_extends_forward():
    from pipeline.goal_sequences.service import _refinement_ranges

    b = derive_boundaries(_labels([
        (60, "other_play"), (62, "buildup"), (64, "goal"), (66, "celebration"), (68, "reaction"),
    ]))
    assert b.celebration_end.open
    ranges = _refinement_ranges(b, earliest=60, latest=68, duration=6000, anchor=70)
    assert ("celebration_end", 68.5, 88.0, 6) in ranges
    assert not [r for r in _refinement_ranges(b, 60, 160, 6000, anchor=70)
                if r[0] == "celebration_end"]


def test_no_goal_frame_uses_buildup_to_celebration_transition_or_fails():
    b = derive_boundaries(_labels([(0, "buildup"), (2, "buildup"), (4, "celebration")]))
    assert b.goal.outside == 2.0 and b.goal.inside == 4.0
    assert derive_boundaries(_labels([(0, "stoppage"), (2, "replay")])).status == "no_goal_frame"


def _ctx():
    return GoalContext(
        event_id="e", match_id="m", anchor=100.0, window_start=55.0, window_end=130.0,
        description="goal",
        evidence=[EvidencePoint(95.0, "audio_peak", "peak", 1.0),
                  EvidencePoint(100.0, "scoreboard", "1-0", 1.0)],
        shot_cuts=[90.0],
    )


def _frames(ctx, step=1.0):
    rng = np.random.default_rng(0)
    frames = []
    for t in candidate_timestamps(ctx, step):
        image = np.full((90, 160, 3), 60, np.uint8)
        image[:, : int(t) % 160] = 200
        image += rng.integers(0, 5, image.shape, dtype=np.uint8)
        frames.append(Frame(timestamp=t, image=image))
    compute_features(frames)
    score_relevance(frames, ctx)
    return frames


def test_selection_respects_budget_edges_and_covers_buildup():
    ctx = _ctx()
    selected = select_frames(_frames(ctx), ctx, budget=18)
    times = [f.timestamp for f in selected]
    assert len(selected) <= 18 and times == sorted(times)
    assert times[0] == ctx.window_start and times[-1] == ctx.window_end
    assert sum(t < ctx.anchor - 10 for t in times) >= 6
    assert any(abs(t - 95.0) < 0.5 for t in times)


def test_candidates_include_cut_and_evidence_hints():
    times = candidate_timestamps(_ctx(), step=5.0)
    assert 90.5 in times and 95.0 in times and 100.0 in times


def test_only_jpeg_stills_can_be_sent(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00")
    with pytest.raises(ValueError):
        analyzer._image_part(str(video))


def test_model_allowlist():
    assert analyzer.resolve_model("gemini-4-argon") == "gemini-4-argon"
    with pytest.raises(ValueError):
        analyzer.resolve_model("gemini-2.5-flash")


class FakeModels:
    def __init__(self, labels):
        self.labels = labels
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append(contents)
        parsed = analyzer.FrameLabels(labels=self.labels, notes="")
        return SimpleNamespace(
            parsed=parsed, text=parsed.model_dump_json(),
            usage_metadata=SimpleNamespace(prompt_token_count=1500, candidates_token_count=40,
                                           thoughts_token_count=60),
            candidates=[SimpleNamespace(finish_reason="STOP")],
        )


def test_label_frames_sends_only_images_and_text_and_caches(tmp_path):
    db = str(tmp_path / "m.db")
    initialize_database(db)
    ctx = _ctx()
    frames = [Frame(timestamp=t, image=np.zeros((90, 160, 3), np.uint8)) for t in (60.0, 80.0, 99.0)]
    save_frames(frames, str(tmp_path / "frames"))
    fake = FakeModels(["buildup", "buildup", "goal"])
    client = SimpleNamespace(models=fake)

    with get_connection(db) as conn:
        labels, _, usage = analyzer.label_frames(conn, ctx, frames, 0, client=client,
                                                 model="gemini-3.8-flash")
        again, _, usage2 = analyzer.label_frames(conn, ctx, frames, 0, client=client,
                                                 model="gemini-3.8-flash")
        rows = conn.execute("SELECT cache_hit, input_tokens, output_tokens FROM llm_usage"
                            " ORDER BY rowid").fetchall()

    assert labels == again == ["buildup", "buildup", "goal"]
    assert len(fake.calls) == 1 and usage2["cache_hit"] is True
    parts = [c for c in fake.calls[0] if not isinstance(c, str)]
    assert len(parts) == 3
    assert all(p.inline_data.mime_type == "image/jpeg" for p in parts)
    assert [tuple(r) for r in rows] == [(0, 1500, 100), (1, 0, 0)]
