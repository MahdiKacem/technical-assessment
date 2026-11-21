from types import SimpleNamespace

from pipeline.editing.commentary import build_sentences, snap_cuts
from pipeline.embeddings import embed_document_text

SEGMENTS = [
    {"start_time": 10.0, "end_time": 14.0, "text": "Corner for Madrid here."},
    {"start_time": 14.0, "end_time": 16.0, "text": "Since it's punched clear,"},
    {"start_time": 16.0, "end_time": 18.0, "text": "put back into the mix."},
    {"start_time": 18.0, "end_time": 22.0, "text": "And it's in!"},
    {"start_time": 22.0, "end_time": 25.0, "text": "For the scorer,"},
    {"start_time": 25.0, "end_time": 30.0, "text": "the first goal of the game."},
]


def test_segments_merge_into_sentences():
    sentences = build_sentences(SEGMENTS)
    assert [(s.start, s.end) for s in sentences] == [(10, 14), (14, 18), (18, 22), (22, 30)]
    assert sentences[1].text == "Since it's punched clear, put back into the mix."


def test_gap_closes_an_unfinished_sentence():
    sentences = build_sentences([
        {"start_time": 0.0, "end_time": 2.0, "text": "No full stop here"},
        {"start_time": 5.0, "end_time": 6.0, "text": "New sentence."},
    ])
    assert len(sentences) == 2


def test_cuts_already_between_sentences_are_kept():
    r = snap_cuts(14.0, 22.0, goal_time=19.0, sentences=build_sentences(SEGMENTS))
    assert (r.clip_start, r.clip_end) == (14.0, 22.0) and r.notes == []


def test_mid_sentence_cuts_move_to_nearest_boundary():
    r = snap_cuts(15.0, 28.0, goal_time=19.0, sentences=build_sentences(SEGMENTS))
    assert r.clip_start == 14.0
    assert r.clip_end == 30.0
    assert len(r.notes) == 2


def test_end_never_moves_into_a_replay():
    r = snap_cuts(14.0, 26.0, goal_time=19.0, sentences=build_sentences(SEGMENTS),
                  hard_max=27.0)
    assert r.clip_end == 22.0
    assert "runs into the replay" in r.notes[0]


def test_unfixable_cut_is_kept_and_flagged():
    long = [{"start_time": 0.0, "end_time": 60.0, "text": "One very long sentence."}]
    r = snap_cuts(20.0, 40.0, goal_time=30.0, sentences=build_sentences(long))
    assert (r.clip_start, r.clip_end) == (20.0, 40.0)
    assert all("mid-sentence" in n for n in r.notes)


def test_embedding_returns_token_count():
    response = SimpleNamespace(embeddings=[SimpleNamespace(values=[0.1, 0.2])],
                               usage_metadata=SimpleNamespace(prompt_token_count=13))
    client = SimpleNamespace(models=SimpleNamespace(embed_content=lambda **_: response))
    result = embed_document_text(client, "goal")
    assert result.vector == [0.1, 0.2] and result.input_tokens == 13
