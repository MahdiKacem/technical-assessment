import re


WINDOWS = {
    "goal": (30.0, 30.0),
    "red_card": (20.0, 20.0),
    "yellow_card": (20.0, 20.0),
    "substitution": (30.0, 30.0),
    "near_miss": (15.0, 15.0),
}


def _status(confidence: float) -> str:
    if confidence >= 0.90:
        return "confirmed"
    if confidence >= 0.70:
        return "likely"
    if confidence >= 0.50:
        return "candidate"
    return "rejected"


def _unique_evidence(evidence: list[dict]) -> list[dict]:
    unique = []
    seen = set()
    for item in evidence:
        key = (
            item.get("source_type"),
            item.get("source_id"),
            item.get("source_timestamp"),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _entity_values(event: dict) -> set[str]:
    values = set()
    entities = event.get("entities") or {}
    for key in ("team", "player", "card_type"):
        value = entities.get(key)
        if value:
            values.add(str(value).lower())
    return values


def _evidence_conflict(primary: dict, candidate: dict) -> bool:
    primary_entities = _entity_values(primary)
    candidate_entities = _entity_values(candidate)
    if not primary_entities or not candidate_entities:
        return False
    shared = primary_entities & candidate_entities
    return bool(candidate_entities) and not shared


def _with_evidence_relation(evidence: dict, relation: str) -> dict:
    item = dict(evidence)
    details = dict(item.get("details") or {})
    details["relation"] = relation
    item["details"] = details
    return item


def _deduplicate_nearby(
    candidates: list[dict],
    window: float,
) -> list[dict]:
    merged = []

    for candidate in sorted(candidates, key=lambda item: item["timestamp"]):
        matching = None
        for existing in merged:
            if (
                existing["event_type"] == candidate["event_type"]
                and abs(existing["timestamp"] - candidate["timestamp"]) <= window
            ):
                matching = existing
                break

        if matching is None:
            merged.append(dict(candidate))
            continue

        evidence = list(matching.get("evidence") or [])
        evidence.extend(candidate.get("evidence") or [])
        matching["evidence"] = _unique_evidence(evidence)
        matching["timestamp"] = min(
            matching["timestamp"],
            candidate["timestamp"],
        )

    return merged


def fuse_events(events: list[dict]) -> list[dict]:
    scoreboards = [
        event for event in events
        if any(
            evidence.get("source_type") == "scoreboard"
            for evidence in event.get("evidence") or []
        )
    ]
    candidates = [
        event for event in events
        if event not in scoreboards
    ]

    fused = []
    used_candidate_ids = set()

    for primary in sorted(scoreboards, key=lambda item: item["timestamp"]):
        event_type = primary["event_type"]
        if event_type not in {"goal", "red_card", "yellow_card"}:
            continue

        if event_type == "goal":
            confidence = 0.95
        else:
            confidence = 0.90

        evidence = [
            _with_evidence_relation(item, "support")
            for item in primary.get("evidence") or []
        ]
        before, after = WINDOWS[event_type]
        start = primary["timestamp"] - before
        end = primary["timestamp"] + after
        contradicted = False

        for candidate in candidates:
            if candidate["timestamp"] < start or candidate["timestamp"] > end:
                continue

            candidate_type = candidate["event_type"]

            if candidate_type == "crowd_reaction":
                evidence.extend(
                    _with_evidence_relation(item, "support")
                    for item in candidate.get("evidence") or []
                )
                used_candidate_ids.add(candidate["event_id"])
                confidence = min(1.0, confidence + 0.03)
                continue

            if event_type == "goal":
                if candidate_type in {"goal", "goal_candidate"}:
                    for item in candidate.get("evidence") or []:
                        evidence_item = _with_evidence_relation(item, "support")
                        evidence.append(evidence_item)
                    confidence = min(1.0, confidence + 0.05)
                    used_candidate_ids.add(candidate["event_id"])
                elif candidate_type == "near_miss":
                    evidence.extend(
                        _with_evidence_relation(item, "contradict")
                        for item in candidate.get("evidence") or []
                    )
                    contradicted = True
                    confidence -= 0.30
                    used_candidate_ids.add(candidate["event_id"])
                continue

            if candidate_type in {
                f"{event_type}_candidate",
                event_type,
            }:
                if _evidence_conflict(primary, candidate):
                    evidence.extend(
                        _with_evidence_relation(item, "contradict")
                        for item in candidate.get("evidence") or []
                    )
                    confidence -= 0.30
                    contradicted = True
                else:
                    evidence.extend(
                        _with_evidence_relation(item, "support")
                        for item in candidate.get("evidence") or []
                    )
                    confidence = min(1.0, confidence + 0.05)
                used_candidate_ids.add(candidate["event_id"])

        evidence = _unique_evidence(evidence)
        confidence = max(0.0, min(1.0, confidence))
        status = "rejected" if contradicted and confidence < 0.90 else _status(confidence)

        fused_event = dict(primary)
        fused_event["confidence"] = confidence
        fused_event["evidence"] = evidence
        fused_event["entities"] = {
            **(primary.get("entities") or {}),
            "resolution_status": status,
            "fusion_reason": (
                "Scoreboard evidence with compatible support."
                if not contradicted
                else "Scoreboard evidence contradicted by near-miss or incompatible context."
            ),
        }
        fused.append(fused_event)

    remaining = []
    for candidate in candidates:
        if candidate["event_id"] in used_candidate_ids:
            continue

        event_type = candidate["event_type"]
        if event_type == "crowd_reaction":
            continue

        if event_type in {"goal_candidate", "red_card_candidate", "yellow_card_candidate",
                          "substitution_candidate", "near_miss"}:
            confidence = 0.75 if event_type == "near_miss" else 0.65
            status = _status(confidence)
            evidence = [
                _with_evidence_relation(item, "support")
                for item in candidate.get("evidence") or []
            ]
            remaining_event = dict(candidate)
            remaining_event["confidence"] = confidence
            remaining_event["evidence"] = evidence
            remaining_event["entities"] = {
                **(candidate.get("entities") or {}),
                "resolution_status": status,
            }
            remaining.append(remaining_event)
            continue

        if event_type in {"goal", "red_card", "yellow_card", "substitution", "var"}:
            confidence = 0.65
            evidence = [
                _with_evidence_relation(item, "support")
                for item in candidate.get("evidence") or []
            ]
            remaining_event = dict(candidate)
            remaining_event["event_type"] = f"{event_type}_candidate"
            remaining_event["event_id"] = f"{candidate['event_id']}:candidate"
            remaining_event["confidence"] = confidence
            remaining_event["evidence"] = evidence
            remaining_event["entities"] = {
                **(candidate.get("entities") or {}),
                "resolution_status": _status(confidence),
            }
            remaining.append(remaining_event)

    remaining = _deduplicate_nearby(remaining, 8.0)

    all_events = fused + remaining
    all_events.sort(key=lambda event: event["timestamp"])
    return all_events


def cluster_events(events: list[dict]) -> list[dict]:
    """Backward-compatible name; clustering now performs deterministic fusion."""
    return fuse_events(events)
