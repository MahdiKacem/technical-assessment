from types import SimpleNamespace

import pytest

from pipeline.briefs import parser as brief_parser
from pipeline.briefs.parser import interpret_brief
from pipeline.briefs.schema import BriefLLMOutput, LLMEventRequest, to_interpretation
from pipeline.database import get_connection, initialize_database, insert_match


def _request(**overrides) -> LLMEventRequest:
    data = dict(category="goal", count=-1, selection="all", team="", player="",
                search_query="goal", required=True)
    data.update(overrides)
    return LLMEventRequest(**data)


def _output(**overrides) -> BriefLLMOutput:
    data = dict(
        target_duration_seconds=60,
        aspect_ratio="unspecified",
        event_requests=[
            _request(player="messi"),
            _request(category="near_miss", count=2, selection="best",
                     team="Atletico", search_query="shot just wide", required=False),
        ],
        team_priority="named_team",
        priority_team="barcelona",
        ordering="end_with_winning_goal",
        match_minute_start=-1,
        match_minute_end=-1,
        exclude_replays="unspecified",
        include_buildup="yes",
        include_celebration="yes",
        pacing="energetic",
        ambiguities=[],
    )
    data.update(overrides)
    return BriefLLMOutput(**data)


class FakeMessages:
    def __init__(self, output, stop_reason="end_turn"):
        self.output = output
        self.stop_reason = stop_reason
        self.calls = 0

    def parse(self, **kwargs):
        self.calls += 1
        assert kwargs["output_format"] is BriefLLMOutput
        assert "temperature" not in kwargs
        return SimpleNamespace(
            parsed_output=self.output,
            stop_reason=self.stop_reason,
            usage=SimpleNamespace(input_tokens=900, output_tokens=300,
                                  cache_creation_input_tokens=0,
                                  cache_read_input_tokens=0),
            _request_id="req_test",
        )


def _client(output, **kwargs):
    return SimpleNamespace(messages=FakeMessages(output, **kwargs))


@pytest.fixture
def connection(tmp_path):
    db_path = str(tmp_path / "match.db")
    initialize_database(db_path)
    with get_connection(db_path) as conn:
        insert_match(conn, "m", "m.mp4", {"duration_seconds": 100.0})
        conn.executemany(
            "INSERT INTO teams (team_id, match_id, name, side) VALUES (?, 'm', ?, ?)",
            [("t1", "Barcelona", "away"), ("t2", "Real Madrid", "home")],
        )
        conn.executemany(
            "INSERT INTO players (player_id, match_id, team_id, shirt_number, name)"
            " VALUES (?, 'm', ?, ?, ?)",
            [("p10", "t1", 10, "Lionel Messi"), ("p7", "t2", 7, "Cristiano Ronaldo")],
        )
        yield conn


def test_sentinels_become_none():
    interp = to_interpretation(_output(match_minute_start=0, match_minute_end=10))
    assert interp.aspect_ratio is None and interp.exclude_replays is None
    assert interp.include_buildup is True
    assert interp.match_minute_start == 0
    goal, near_miss = interp.event_requests
    assert goal.count is None and goal.team is None
    assert near_miss.count == 2
    assert to_interpretation(_output(match_minute_start=-1)).match_minute_start is None


def test_roster_validation_and_defaults(connection):
    brief_id, parsed, usage = interpret_brief(connection, "m", "brief",
                                              client=_client(_output()),
                                              model="claude-opus-5-5")
    goal, near_miss = parsed.event_requests
    assert goal.player == "Lionel Messi" and goal.team == "Barcelona"
    assert parsed.resolved_player_ids == {"Lionel Messi": "p10"}
    assert near_miss.team is None
    assert any("Atletico" in a for a in parsed.ambiguities)
    assert parsed.priority_team == "Barcelona"
    assert parsed.aspect_ratio == "9:16" and parsed.exclude_replays is True
    assert len(parsed.applied_defaults) == 2 and parsed.policy_overrides == []
    assert usage["input_tokens"] == 900 and usage["estimated_cost"] > 0


def test_brief_allowing_replays_is_overridden_and_recorded(connection):
    _, parsed, _ = interpret_brief(connection, "m", "replays are fine",
                                   client=_client(_output(exclude_replays="no")),
                                   model="claude-opus-5-5")
    assert parsed.exclude_replays is True
    assert len(parsed.policy_overrides) == 1
    assert not any("exclude_replays" in d for d in parsed.applied_defaults)


def test_empty_brief_requests_get_default_set(connection):
    _, parsed, _ = interpret_brief(connection, "m", "make something exciting",
                                   client=_client(_output(event_requests=[])),
                                   model="claude-opus-5-5")
    assert [r.category for r in parsed.event_requests] == ["goal", "red_card", "near_miss"]
    assert all(not r.required for r in parsed.event_requests)
    assert any("event_requests" in d for d in parsed.applied_defaults)


def test_cache_hit_reapplies_postprocessing(connection, monkeypatch):
    client = _client(_output(event_requests=[]))
    first_id, _, _ = interpret_brief(connection, "m", "brief", client=client,
                                     model="claude-opus-5-5")
    monkeypatch.setattr(brief_parser, "DEFAULT_EVENT_REQUESTS",
                        brief_parser.DEFAULT_EVENT_REQUESTS[:1])
    second_id, parsed, usage = interpret_brief(connection, "m", "  brief ",
                                               client=client, model="claude-opus-5-5")
    assert client.messages.calls == 1
    assert second_id == first_id and usage["cache_hit"] is True
    assert [r.category for r in parsed.event_requests] == ["goal"]
    rows = connection.execute(
        "SELECT cache_hit, input_tokens FROM llm_usage ORDER BY rowid"
    ).fetchall()
    assert [tuple(r) for r in rows] == [(0, 900), (1, 0)]


def test_unknown_named_team_falls_back_to_no_priority(connection):
    output = _output(priority_team="Chelsea", event_requests=[])
    _, parsed, _ = interpret_brief(connection, "m", "b2", client=_client(output),
                                   model="claude-opus-5-5")
    assert parsed.team_priority == "none" and parsed.priority_team is None


def test_refusal_is_logged_and_raised(connection):
    with pytest.raises(RuntimeError):
        interpret_brief(connection, "m", "b3",
                        client=_client(None, stop_reason="refusal"),
                        model="claude-opus-5-5")
    row = connection.execute("SELECT success, error FROM llm_usage").fetchone()
    assert row["success"] == 0 and "refusal" in row["error"]
    assert connection.execute("SELECT COUNT(*) FROM creative_briefs").fetchone()[0] == 0
