import cv2
import re
from pathlib import Path


ROLE_OFFSETS = {
    "goal": (-10.0, 0.0, 10.0),
    "red_card": (-5.0, 0.0, 10.0),
    "yellow_card": (-5.0, 0.0, 10.0),
    "substitution": (-15.0, 0.0, 15.0),
    "near_miss": (-5.0, 0.0, 5.0),
}


def nearest_keyframe(keyframes: list[dict], target: float) -> dict | None:
    if not keyframes:
        return None
    return min(
        keyframes,
        key=lambda keyframe: abs(keyframe["timestamp"] - target),
    )


def select_event_keyframes(
    event: dict,
    keyframes: list[dict],
) -> list[dict]:
    event_type = event["event_type"].replace("_candidate", "")
    offsets = ROLE_OFFSETS.get(event_type, (-10.0, 0.0, 10.0))
    timestamp = event["timestamp"]
    roles = ("before", "at_event", "after")
    selected = []
    selected_ids = set()

    for role, offset in zip(roles, offsets):
        target = timestamp + offset
        keyframe = nearest_keyframe(keyframes, target)
        if keyframe is None:
            continue
        if keyframe["keyframe_id"] in selected_ids:
            continue

        selected_ids.add(keyframe["keyframe_id"])
        selected.append(
            {
                "keyframe_id": keyframe["keyframe_id"],
                "timestamp": keyframe["timestamp"],
                "image_path": keyframe["image_path"],
                "role": role,
                "target_timestamp": round(target, 3),
            }
        )

    return selected


def select_keyframes_for_events(
    events: list[dict],
    keyframes: list[dict],
) -> list[dict]:
    manifest = []

    for event in events:
        entities = event.get("entities") or {}
        status = entities.get("resolution_status")
        event_type = event["event_type"].replace("_candidate", "")

        should_select = (
            status in {"confirmed", "likely"}
            or event_type in {"red_card", "yellow_card", "substitution"}
            or event["confidence"] >= 0.70
        )
        if not should_select:
            continue

        timestamp = event["timestamp"]
        evidence_timestamp = timestamp
        for evidence in event.get("evidence") or []:
            if evidence.get("source_type") == "scoreboard":
                evidence_timestamp = evidence.get(
                    "source_timestamp",
                    evidence_timestamp,
                )
                break

        event_selection = dict(event)
        event_selection["timestamp"] = timestamp
        selected = select_event_keyframes(event_selection, keyframes)
        for frame in selected:
            if frame["role"] == "at_event":
                frame["target_timestamp"] = round(evidence_timestamp, 3)

        manifest.append(
            {
                "event_id": event["event_id"],
                "event_type": event["event_type"],
                "timestamp": event["timestamp"],
                "confidence": event["confidence"],
                "keyframes": selected,
            }
        )

    return manifest


def extract_event_frames(
    video_path: str,
    manifest: list[dict],
    output_dir: str,
) -> list[dict]:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        for entry in manifest:
            safe_event_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", entry["event_id"])
            event_dir = output_dir / safe_event_id
            event_dir.mkdir(parents=True, exist_ok=True)

            for frame in entry["keyframes"]:
                target = float(frame["target_timestamp"])
                cap.set(cv2.CAP_PROP_POS_MSEC, target * 1000)
                success, image = cap.read()
                if not success:
                    continue

                relative_path = (
                    Path(Path(output_dir).name)
                    / safe_event_id
                    / f"{frame['role']}.jpg"
                )
                image_path = event_dir / f"{frame['role']}.jpg"
                cv2.imwrite(str(image_path), image)
                frame["keyframe_id"] = (
                    f"{entry['event_id']}:{frame['role']}"
                )
                frame["timestamp"] = round(target, 3)
                frame["image_path"] = relative_path.as_posix()
    finally:
        cap.release()

    return manifest
