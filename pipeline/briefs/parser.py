import hashlib
import json
import os
import time
import unicodedata

from pipeline.briefs.schema import (
    SCHEMA_VERSION,
    BriefInterpretation,
    BriefLLMOutput,
    EventRequest,
    ParsedBrief,
    to_interpretation,
)

PROMPT_VERSION = "brief-prompt-v3"
DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_EFFORT = "low"
MAX_TOKENS = 4000
STAGE = "brief_interpretation"

PRICING = {
    "claude-opus-5-5": {"input": 4.00, "output": 20.00, "cache_read": 0.20},
}

DEFAULT_EVENT_REQUESTS = [
    EventRequest(category="goal", count=None, selection="all", team=None,
                 player=None, search_query="goal scored", required=False),
    EventRequest(category="red_card", count=None, selection="all", team=None,
                 player=None, search_query="red card sending off", required=False),
    EventRequest(category="near_miss", count=None, selection="best", team=None,
                 player=None, search_query="near miss, shot just wide or saved",
                 required=False),
]

SYSTEM_PROMPT = """Convert a football highlight creative brief into the JSON schema.
Record only what the brief states or clearly implies; never invent counts, durations, teams or players.
When the brief is silent: integers -1, strings "", enums "unspecified" (team_priority "none").
Fields:
- count: number explicitly requested. "All goals" -> selection all, count -1. "Best two near misses" -> best, 2.
- selection: all | best (most notable) | first | last | unspecified.
- team, priority_team: a team name copied exactly from the roster. player: a name copied exactly from the roster. Someone not in the roster -> "" plus an ambiguity.
- team_priority named_team requires priority_team.
- search_query: short English phrase describing the moment.
- required: the brief says it must be included.
- One event_request per moment type. Celebrations after goals -> include_celebration "yes", not a separate request, unless asked for on their own.
- match_minute_start/end: match clock minutes. "Final 10 minutes" -> 80, 90.
- exclude_replays, include_buildup, include_celebration: yes | no | unspecified.
- ambiguities: only points a human must decide (unknown names, conflicting or unclear requests). At most 3, under 15 words each. Never restate a mapping you made."""


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.casefold().strip()


def load_roster_context(connection, match_id: str) -> dict:
    teams = [
        dict(row)
        for row in connection.execute(
            "SELECT team_id, name, side FROM teams WHERE match_id = ? ORDER BY name",
            (match_id,),
        )
    ]
    players = [
        dict(row)
        for row in connection.execute(
            """
            SELECT p.player_id, p.name, p.shirt_number, t.name AS team_name
            FROM players p LEFT JOIN teams t ON t.team_id = p.team_id
            WHERE p.match_id = ?
            ORDER BY t.name, p.shirt_number
            """,
            (match_id,),
        )
    ]
    return {"teams": teams, "players": players}


def format_roster(roster: dict) -> str:
    lines = []
    for team in roster["teams"]:
        side = f" ({team['side']})" if team.get("side") else ""
        names = ", ".join(
            f"{p['shirt_number']} {p['name']}"
            for p in roster["players"]
            if p["team_name"] == team["name"]
        )
        lines.append(f"{team['name']}{side}: {names}")
    return "\n".join(lines)


def build_cache_key(raw_brief: str, roster_text: str, model: str, effort: str) -> str:
    payload = json.dumps(
        [raw_brief.strip(), roster_text, model, effort, PROMPT_VERSION, SCHEMA_VERSION]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_against_roster(
    interpretation: BriefInterpretation, roster: dict
) -> ParsedBrief:
    parsed = ParsedBrief(**interpretation.model_dump())
    team_lookup = {_normalize(t["name"]): t["name"] for t in roster["teams"]}
    players = roster["players"]

    def resolve_team(name: str | None, where: str) -> str | None:
        if name is None:
            return None
        match = team_lookup.get(_normalize(name))
        if match is None:
            parsed.ambiguities.append(f"Unknown team '{name}' in {where}; ignored.")
        return match

    def resolve_player(name: str) -> dict | None:
        key = _normalize(name)
        exact = [p for p in players if _normalize(p["name"]) == key]
        if len(exact) == 1:
            return exact[0]
        partial = [p for p in players if key in _normalize(p["name"])]
        return partial[0] if len(partial) == 1 else None

    parsed.priority_team = resolve_team(parsed.priority_team, "priority_team")
    if parsed.team_priority == "named_team" and parsed.priority_team is None:
        parsed.team_priority = "none"

    for request in parsed.event_requests:
        request.team = resolve_team(request.team, f"{request.category} request")
        if request.player is None:
            continue
        player = resolve_player(request.player)
        if player is None:
            parsed.ambiguities.append(
                f"Player '{request.player}' not uniquely found in roster; ignored."
            )
            request.player = None
            continue
        request.player = player["name"]
        parsed.resolved_player_ids[player["name"]] = player["player_id"]
        if request.team is None:
            request.team = player["team_name"]

    return parsed


def apply_defaults(parsed: ParsedBrief) -> ParsedBrief:
    if parsed.aspect_ratio is None:
        parsed.aspect_ratio = "9:16"
        parsed.applied_defaults.append("aspect_ratio=9:16 (assessment output format)")
    if parsed.exclude_replays is None:
        parsed.exclude_replays = True
        parsed.applied_defaults.append("exclude_replays=true (replays never used in edit)")
    if not parsed.event_requests:
        parsed.event_requests = [r.model_copy() for r in DEFAULT_EVENT_REQUESTS]
        parsed.applied_defaults.append(
            "event_requests=goal(all), red_card(all), near_miss(best): "
            "brief requested no specific moments"
        )
    return parsed


def apply_policies(parsed: ParsedBrief) -> ParsedBrief:
    if parsed.exclude_replays is False:
        parsed.exclude_replays = True
        parsed.policy_overrides.append(
            "exclude_replays: brief allowed replays, but replays are never used "
            "in the edit (project rule)"
        )
    return parsed


def postprocess(llm_output: BriefLLMOutput, roster: dict) -> ParsedBrief:
    parsed = validate_against_roster(to_interpretation(llm_output), roster)
    return apply_policies(apply_defaults(parsed))


def estimate_cost(model: str, input_tokens: int, output_tokens: int, cache_read: int) -> float | None:
    price = PRICING.get(model)
    if price is None:
        return None
    return (
        input_tokens * price["input"]
        + output_tokens * price["output"]
        + cache_read * price["cache_read"]
    ) / 1_000_000


def record_llm_usage(connection, **fields) -> None:
    columns = ", ".join(fields)
    placeholders = ", ".join("?" for _ in fields)
    connection.execute(
        f"INSERT INTO llm_usage ({columns}) VALUES ({placeholders})",
        tuple(fields.values()),
    )
    connection.commit()


def make_client():
    import anthropic
    from dotenv import load_dotenv

    load_dotenv()
    api_key = os.getenv("CLAUDE_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("CLAUDE_API_KEY is not set (see .env.example).")
    return anthropic.Anthropic(api_key=api_key, max_retries=2, timeout=120.0)


def interpret_brief(
    connection,
    match_id: str,
    raw_brief: str,
    client=None,
    model: str | None = None,
    effort: str = DEFAULT_EFFORT,
) -> tuple[str, ParsedBrief, dict]:
    if not raw_brief.strip():
        raise ValueError("Creative brief is empty.")
    model = model or os.getenv("CLAUDE_MODEL", DEFAULT_MODEL)

    started = time.perf_counter()
    roster = load_roster_context(connection, match_id)
    roster_text = format_roster(roster)
    cache_key = build_cache_key(raw_brief, roster_text, model, effort)
    brief_id = f"{match_id}:brief:{cache_key[:16]}"
    base_log = dict(stage=STAGE, match_id=match_id, ref_id=brief_id,
                    model_name=model, prompt_version=PROMPT_VERSION)

    cached = connection.execute(
        "SELECT llm_output_json FROM creative_briefs WHERE cache_key = ?",
        (cache_key,),
    ).fetchone()
    if cached is not None and cached["llm_output_json"]:
        parsed = postprocess(BriefLLMOutput.model_validate_json(cached["llm_output_json"]), roster)
        connection.execute(
            "UPDATE creative_briefs SET parsed_json = ? WHERE brief_id = ?",
            (parsed.model_dump_json(), brief_id),
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        record_llm_usage(connection, usage_id=f"{brief_id}:usage:{time.time_ns()}",
                         **base_log, input_tokens=0, output_tokens=0,
                         latency_ms=latency_ms, estimated_cost=0.0, cache_hit=1, success=1)
        usage = {"cache_hit": True, "input_tokens": 0, "output_tokens": 0,
                 "estimated_cost": 0.0, "latency_ms": latency_ms}
        return brief_id, parsed, usage

    client = client or make_client()
    user_message = f"Roster:\n{roster_text}\n\nCreative brief:\n{raw_brief.strip()}"

    api_started = time.perf_counter()
    try:
        response = client.messages.parse(
            model=model,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            output_config={"effort": effort},
            output_format=BriefLLMOutput,
            messages=[{"role": "user", "content": user_message}],
        )
    except Exception as error:
        record_llm_usage(connection, usage_id=f"{brief_id}:usage:{time.time_ns()}",
                         **base_log,
                         latency_ms=int((time.perf_counter() - api_started) * 1000),
                         cache_hit=0, success=0,
                         error=f"{type(error).__name__}: {error}"[:500])
        raise
    latency_ms = int((time.perf_counter() - api_started) * 1000)

    u = response.usage
    input_tokens = (u.input_tokens or 0) + (getattr(u, "cache_creation_input_tokens", 0) or 0)
    cache_read = getattr(u, "cache_read_input_tokens", 0) or 0
    output_tokens = u.output_tokens or 0
    cost = estimate_cost(model, input_tokens, output_tokens, cache_read)
    request_id = getattr(response, "_request_id", None)
    ok = response.stop_reason == "end_turn" and response.parsed_output is not None

    record_llm_usage(connection, usage_id=f"{brief_id}:usage:{time.time_ns()}",
                     **base_log, input_tokens=input_tokens, output_tokens=output_tokens,
                     cache_read_tokens=cache_read, latency_ms=latency_ms,
                     estimated_cost=cost, cache_hit=0, success=1 if ok else 0,
                     error=None if ok else f"stop_reason={response.stop_reason}",
                     request_id=request_id, stop_reason=response.stop_reason)
    if not ok:
        raise RuntimeError(
            f"Brief interpretation failed (stop_reason={response.stop_reason})."
        )

    llm_output: BriefLLMOutput = response.parsed_output
    parsed = postprocess(llm_output, roster)
    connection.execute(
        """
        INSERT INTO creative_briefs (
            brief_id, match_id, raw_text, cache_key, llm_output_json, parsed_json,
            model_name, prompt_version, schema_version, effort
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(brief_id) DO UPDATE SET
            llm_output_json = excluded.llm_output_json,
            parsed_json = excluded.parsed_json,
            cache_key = excluded.cache_key,
            prompt_version = excluded.prompt_version,
            schema_version = excluded.schema_version
        """,
        (brief_id, match_id, raw_brief.strip(), cache_key, llm_output.model_dump_json(),
         parsed.model_dump_json(), model, PROMPT_VERSION, SCHEMA_VERSION, effort),
    )
    connection.commit()

    usage = {"cache_hit": False, "input_tokens": input_tokens,
             "output_tokens": output_tokens, "cache_read_tokens": cache_read,
             "estimated_cost": cost, "latency_ms": latency_ms,
             "total_ms": int((time.perf_counter() - started) * 1000),
             "request_id": request_id}
    return brief_id, parsed, usage
