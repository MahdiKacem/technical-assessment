from typing import Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "brief-v2"

EventCategory = Literal[
    "goal", "near_miss", "red_card", "yellow_card", "celebration",
    "save", "foul", "substitution", "other",
]
Selection = Literal["all", "best", "first", "last", "unspecified"]
AspectRatio = Literal["9:16", "16:9", "1:1"]
TeamPriority = Literal["winning_team", "losing_team", "named_team", "none"]
Ordering = Literal["chronological", "end_with_winning_goal", "best_first", "unspecified"]
Pacing = Literal["energetic", "calm", "neutral", "unspecified"]
YesNo = Literal["yes", "no", "unspecified"]


class LLMEventRequest(BaseModel):
    category: EventCategory
    count: int
    selection: Selection
    team: str
    player: str
    search_query: str
    required: bool


class BriefLLMOutput(BaseModel):
    target_duration_seconds: int
    aspect_ratio: Literal["9:16", "16:9", "1:1", "unspecified"]
    event_requests: list[LLMEventRequest]
    team_priority: TeamPriority
    priority_team: str
    ordering: Ordering
    match_minute_start: int
    match_minute_end: int
    exclude_replays: YesNo
    include_buildup: YesNo
    include_celebration: YesNo
    pacing: Pacing
    ambiguities: list[str]


class EventRequest(BaseModel):
    category: EventCategory
    count: int | None
    selection: Selection
    team: str | None
    player: str | None
    search_query: str
    required: bool


class BriefInterpretation(BaseModel):
    target_duration_seconds: int | None
    aspect_ratio: AspectRatio | None
    event_requests: list[EventRequest]
    team_priority: TeamPriority
    priority_team: str | None
    ordering: Ordering
    match_minute_start: int | None
    match_minute_end: int | None
    exclude_replays: bool | None
    include_buildup: bool | None
    include_celebration: bool | None
    pacing: Pacing
    ambiguities: list[str]


class ParsedBrief(BriefInterpretation):
    schema_version: str = SCHEMA_VERSION
    resolved_player_ids: dict[str, str] = Field(default_factory=dict)
    applied_defaults: list[str] = Field(default_factory=list)
    policy_overrides: list[str] = Field(default_factory=list)


def _int(value: int) -> int | None:
    return value if value >= 0 else None


def _positive(value: int) -> int | None:
    return value if value > 0 else None


def _text(value: str) -> str | None:
    value = value.strip()
    return value or None


def _yes_no(value: str) -> bool | None:
    return {"yes": True, "no": False}.get(value)


def to_interpretation(output: BriefLLMOutput) -> BriefInterpretation:
    return BriefInterpretation(
        target_duration_seconds=_positive(output.target_duration_seconds),
        aspect_ratio=None if output.aspect_ratio == "unspecified" else output.aspect_ratio,
        event_requests=[
            EventRequest(
                category=r.category,
                count=_positive(r.count),
                selection=r.selection,
                team=_text(r.team),
                player=_text(r.player),
                search_query=r.search_query.strip(),
                required=r.required,
            )
            for r in output.event_requests
        ],
        team_priority=output.team_priority,
        priority_team=_text(output.priority_team),
        ordering=output.ordering,
        match_minute_start=_int(output.match_minute_start),
        match_minute_end=_int(output.match_minute_end),
        exclude_replays=_yes_no(output.exclude_replays),
        include_buildup=_yes_no(output.include_buildup),
        include_celebration=_yes_no(output.include_celebration),
        pacing=output.pacing,
        ambiguities=list(output.ambiguities),
    )
