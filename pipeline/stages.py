import json
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from pipeline.config import MatchConfig
from pipeline.database import get_connection, initialize_database


def _write_json(data, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def _read_json(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"{path} not found - run the stage that produces it first.")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


@contextmanager
def timed_stage(cfg: MatchConfig, stage: str, params: dict | None = None):
    initialize_database(cfg.db_path)
    run_id = f"{stage}:{uuid.uuid4().hex[:12]}"
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    summary: dict = {}
    with get_connection(cfg.db_path) as connection:
        connection.execute(
            "INSERT INTO stage_runs (run_id, stage, match_id, started_at, status, params_json)"
            " VALUES (?, ?, ?, ?, 'running', ?)",
            (run_id, stage, cfg.match_id, started_at, json.dumps(params or {})),
        )
    print(f"[{stage}] started")
    started = time.perf_counter()
    status, error = "success", None
    try:
        yield summary
    except BaseException as exc:
        status, error = "failed", f"{type(exc).__name__}: {exc}"[:1000]
        raise
    finally:
        elapsed = round(time.perf_counter() - started, 3)
        with get_connection(cfg.db_path) as connection:
            connection.execute(
                "UPDATE stage_runs SET elapsed_seconds = ?, status = ?, summary_json = ?,"
                " error = ? WHERE run_id = ?",
                (elapsed, status, json.dumps(summary, default=str), error, run_id),
            )
        print(f"[{stage}] {status} in {elapsed:.1f}s {summary if summary else ''}")


def run_ingest(cfg: MatchConfig) -> dict:
    from pipeline.database import persist_ingestion
    from pipeline.ingestion.audio import extract_audio
    from pipeline.ingestion.keyframes import extract_keyframes
    from pipeline.ingestion.metadata import extract_metadata
    from pipeline.ingestion.shots import detect_shots
    from pipeline.ingestion.windows import generate_windows

    with timed_stage(cfg, "ingest", {"video": cfg.video_path}) as summary:
        metadata = extract_metadata(cfg.video_path)
        _write_json(metadata, cfg.artifact_dir / "video_metadata.json")

        extract_audio(cfg.video_path, cfg.audio_path)

        shots = detect_shots(cfg.video_path)
        _write_json(shots, cfg.index_dir / "shots.json")

        windows = generate_windows(shots)
        _write_json(windows, cfg.index_dir / "windows.json")

        keyframes = extract_keyframes(cfg.video_path, windows, cfg.keyframes_dir)
        _write_json(keyframes, cfg.index_dir / "keyframes.json")

        persist_ingestion(cfg.db_path, cfg.match_id, cfg.video_path, metadata,
                          shots, windows, keyframes)
        summary.update(shots=len(shots), windows=len(windows), keyframes=len(keyframes))
    return summary


def run_rosters(cfg: MatchConfig) -> dict:
    from pipeline.database import persist_rosters
    from pipeline.ingestion.roster import parse_roster_csv

    with timed_stage(cfg, "rosters", {"paths": cfg.roster_paths}) as summary:
        rosters = [parse_roster_csv(path) for path in cfg.roster_paths]
        persist_rosters(cfg.db_path, cfg.match_id, rosters)
        summary.update({r["team_name"]: len(r["players"]) for r in rosters})
    return summary


def run_audio(cfg: MatchConfig) -> dict:
    from pipeline.analysis.audio import extract_audio_features
    from pipeline.analysis.audio_peaks import detect_audio_peaks
    from pipeline.database import persist_audio

    with timed_stage(cfg, "audio") as summary:
        features = extract_audio_features(cfg.audio_path)
        _write_json(features, cfg.signals_dir / "audio_features.json")
        peaks = detect_audio_peaks(features)
        _write_json(peaks, cfg.signals_dir / "audio_peaks.json")
        persist_audio(cfg.db_path, cfg.match_id, features, peaks)
        summary.update(features=len(features), peaks=len(peaks))
    return summary


def run_transcribe(cfg: MatchConfig, model_size: str = "small", language: str = "en") -> dict:
    from pipeline.analysis.transcription import transcribe_audio
    from pipeline.database import persist_transcription

    params = {"engine": "faster-whisper", "model_size": model_size, "language": language}
    with timed_stage(cfg, "transcribe", params) as summary:
        segments = transcribe_audio(cfg.audio_path, model_size=model_size, language=language)
        _write_json(segments, cfg.signals_dir / "transcription.json")
        persist_transcription(cfg.db_path, cfg.match_id, segments)
        summary.update(segments=len(segments))
    return summary


def run_scoreboard(
    cfg: MatchConfig,
    sample_interval: float = 2.0,
    start_time: float = 0.0,
    end_time: float | None = None,
) -> dict:
    from pipeline.analysis.scoreboard_ocr import extract_scoreboard_observations
    from pipeline.database import (
        insert_card_events,
        insert_scoreboard_observations,
        parse_scoreboard_with_roster,
    )

    params = {"sample_interval": sample_interval, "start": start_time, "end": end_time}
    with timed_stage(cfg, "scoreboard", params) as summary:
        observations = extract_scoreboard_observations(
            cfg.video_path, sample_interval=sample_interval,
            start_time=start_time, end_time=end_time,
        )
        _write_json(observations, cfg.signals_dir / "scoreboard_ocr.json")

        with get_connection(cfg.db_path) as connection:
            parsed = parse_scoreboard_with_roster(connection, cfg.match_id, observations)
            insert_scoreboard_observations(connection, cfg.match_id, observations)
            insert_card_events(connection, cfg.match_id, parsed)
        _write_json(parsed, cfg.signals_dir / "scoreboard_parsed.json")

        summary.update(
            ocr_texts=len(observations),
            frames=len(parsed),
            frames_with_score=sum(1 for p in parsed if p.get("score_candidates")),
            card_mentions=sum(len(p.get("card_candidates") or []) for p in parsed),
        )
    return summary


def run_events(cfg: MatchConfig) -> dict:
    from pipeline.database import persist_event_keyframes, persist_events
    from pipeline.events import (
        cluster_events,
        extract_audio_events,
        extract_scoreboard_events,
        extract_transcription_events,
    )
    from pipeline.events.keyframe_context import (
        extract_event_frames,
        select_keyframes_for_events,
    )
    from pipeline.search import build_event_search_index

    with timed_stage(cfg, "events") as summary:
        with get_connection(cfg.db_path) as connection:
            events = []
            events.extend(extract_scoreboard_events(connection, cfg.match_id))
            events.extend(extract_audio_events(connection, cfg.match_id))
            events.extend(extract_transcription_events(connection, cfg.match_id))
        events.sort(key=lambda event: event["timestamp"])
        events = cluster_events(events)
        persist_events(cfg.db_path, cfg.match_id, events)
        _write_json(events, cfg.signals_dir / "events.json")

        keyframes = _read_json(cfg.index_dir / "keyframes.json")
        manifest = select_keyframes_for_events(events, keyframes)
        manifest = extract_event_frames(cfg.video_path, manifest, cfg.event_frames_dir)
        persist_event_keyframes(cfg.db_path, cfg.match_id, manifest)
        _write_json(manifest, cfg.signals_dir / "event_keyframes.json")

        with get_connection(cfg.db_path) as connection:
            indexed = build_event_search_index(connection, cfg.match_id)

        by_type: dict[str, int] = {}
        for event in events:
            by_type[event["event_type"]] = by_type.get(event["event_type"], 0) + 1
        summary.update(events=len(events), events_with_frames=len(manifest),
                       indexed=indexed, by_type=by_type)
    return summary


def build_embedding_documents(connection, match_id: str) -> list[dict]:
    from pipeline.multimodal import (
        build_event_text_document,
        build_transcript_window_document,
        get_event_keyframe_documents,
    )

    documents = []
    event_ids = [
        row["event_id"]
        for row in connection.execute(
            "SELECT event_id FROM events WHERE match_id = ? ORDER BY timestamp, event_id",
            (match_id,),
        )
    ]
    for event_id in event_ids:
        documents.append({
            "event_id": event_id, "modality": "text", "source_type": "event",
            "source_id": event_id, "timestamp": None,
            "content": build_event_text_document(connection, event_id),
        })
        documents.append({
            "event_id": event_id, "modality": "text", "source_type": "transcript_window",
            "source_id": f"{event_id}:transcript-window", "timestamp": None,
            "content": build_transcript_window_document(connection, event_id),
        })
        for keyframe in get_event_keyframe_documents(connection, event_id):
            documents.append({
                "event_id": event_id, "modality": "image", "source_type": "keyframe",
                "source_id": keyframe["event_keyframe_id"],
                "timestamp": keyframe["timestamp"],
                "image_path": keyframe["image_path"], "content": None,
            })
    return documents


def run_embed(cfg: MatchConfig, limit: int | None = None, modalities=("text", "image")) -> dict:
    from pipeline.embeddings import (
        MODEL_NAME,
        MODEL_VERSION,
        embed_document_text,
        embed_image,
        make_gemini_client,
    )
    from pipeline.multimodal import (
        find_cached_embedding,
        persist_embedding,
        record_embedding_usage,
    )

    params = {"model": MODEL_NAME, "limit": limit, "modalities": list(modalities)}
    with timed_stage(cfg, "embed", params) as summary:
        client = None
        api_calls = cache_hits = skipped = failed = 0
        input_tokens = {"text": 0, "image": 0}
        started = time.perf_counter()
        with get_connection(cfg.db_path) as connection:
            documents = [
                d for d in build_embedding_documents(connection, cfg.match_id)
                if d["modality"] in modalities
            ]
            _write_json(documents, cfg.signals_dir / "multimodal_documents.json")

            for doc in documents:
                if doc["modality"] == "image":
                    path = Path(doc["image_path"])
                    if not path.exists():
                        skipped += 1
                        continue
                    content = path.read_bytes()
                else:
                    content = doc["content"]
                    if not content:
                        skipped += 1
                        continue

                if find_cached_embedding(connection, doc["source_type"], doc["source_id"],
                                         MODEL_NAME, MODEL_VERSION, content):
                    cache_hits += 1
                    continue
                if limit is not None and api_calls >= limit:
                    skipped += 1
                    continue

                client = client or make_gemini_client()
                try:
                    if doc["modality"] == "image":
                        result = embed_image(client, content)
                    else:
                        result = embed_document_text(client, content)
                except Exception as exc:
                    failed += 1
                    print(f"  embedding failed for {doc['source_id']}: {exc}")
                    continue
                api_calls += 1
                input_tokens[doc["modality"]] += result.input_tokens or 0
                persist_embedding(connection, cfg.match_id, doc["event_id"],
                                  doc["source_type"], doc["source_id"], doc["timestamp"],
                                  doc["modality"], MODEL_NAME, MODEL_VERSION, content,
                                  result.vector)
                connection.commit()

            record_embedding_usage(
                connection, cfg.match_id, MODEL_NAME, "text_image",
                item_count=api_calls, cache_hits=cache_hits,
                input_tokens=sum(input_tokens.values()), output_tokens=0,
                latency_ms=int((time.perf_counter() - started) * 1000),
                success=failed == 0,
            )
        summary.update(documents=len(documents), api_calls=api_calls,
                       cache_hits=cache_hits, skipped=skipped, failed=failed,
                       input_tokens=input_tokens)
    return summary


def run_sequences(
    cfg: MatchConfig,
    event_ids: list[str] | None = None,
    model: str | None = None,
    budget: int = 18,
    refine: bool = True,
    media_resolution: str = "MEDIA_RESOLUTION_LOW",
) -> dict:
    from pipeline.goal_sequences.service import extract_goal_sequence, goal_event_ids

    params = {"event_ids": event_ids, "model": model, "budget": budget, "refine": refine,
              "media_resolution": media_resolution}
    with timed_stage(cfg, "sequences", params) as summary:
        results = []
        with get_connection(cfg.db_path) as connection:
            for event_id in event_ids or goal_event_ids(connection, cfg.match_id):
                r = extract_goal_sequence(connection, cfg, event_id, model=model,
                                          budget=budget, refine=refine,
                                          media_resolution=media_resolution)
                results.append(r)
                print(f"  {event_id}: {r['status']} buildup={r['buildup_start']}"
                      f" goal={r['goal_time']} celebration_end={r['celebration_end']}"
                      f" frames={r['frames_sent']} tokens={r['input_tokens']}/{r['output_tokens']}")
        _write_json(results, cfg.signals_dir / "goal_sequences.json")
        summary.update(goals=len(results),
                       statuses={s: sum(r["status"] == s for r in results)
                                 for s in {r["status"] for r in results}},
                       input_tokens=sum(r["input_tokens"] for r in results),
                       output_tokens=sum(r["output_tokens"] for r in results))
    return summary


INDEX_STAGES = ["ingest", "rosters", "audio", "transcribe", "scoreboard", "events",
                "sequences", "embed"]
