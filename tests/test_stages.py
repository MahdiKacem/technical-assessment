import pytest

from pipeline.config import MatchConfig
from pipeline.database import get_connection
from pipeline.stages import INDEX_STAGES, timed_stage
from run import build_parser


def test_timed_stage_records_success_and_failure(tmp_path):
    cfg = MatchConfig(match_id="m", artifacts_root=str(tmp_path))

    with timed_stage(cfg, "demo", {"x": 1}) as summary:
        summary["rows"] = 3
    with pytest.raises(ValueError):
        with timed_stage(cfg, "demo"):
            raise ValueError("boom")

    with get_connection(cfg.db_path) as connection:
        rows = connection.execute(
            "SELECT status, summary_json, error, elapsed_seconds FROM stage_runs"
            " ORDER BY rowid"
        ).fetchall()
    assert [r["status"] for r in rows] == ["success", "failed"]
    assert rows[0]["summary_json"] == '{"rows": 3}'
    assert "boom" in rows[1]["error"]
    assert all(r["elapsed_seconds"] is not None for r in rows)


def test_cli_parses_every_stage():
    parser = build_parser()
    for stage in INDEX_STAGES:
        assert parser.parse_args([stage]).command == stage
    args = parser.parse_args(["index", "--skip", "transcribe", "--skip", "embed"])
    assert args.skip == ["transcribe", "embed"]
    args = parser.parse_args(["search", "goal", "--type", "goal", "--limit", "3"])
    assert args.event_types == ["goal"] and args.limit == 3
