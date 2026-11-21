"""Football highlight pipeline - command-line entry point.

Indexing (run once, before queries):
    python run.py index                 # every indexing stage in order
    python run.py ingest                # metadata, audio, shots, windows, keyframes
    python run.py rosters
    python run.py audio                 # audio features + peaks
    python run.py transcribe
    python run.py scoreboard [--start S --end S --interval 2]
    python run.py events                # extraction, fusion, event frames, search index
    python run.py sequences [--event-id ID] [--model gemini-4-argon]   # goal boundaries
    python run.py embed [--limit N]

Querying:
    python run.py search "late goal" [--semantic] [--type goal] [--limit 5]
    python run.py brief "60s vertical: all goals ..." | --file brief.txt

Inspection:
    python run.py status                # row counts, stage timings, LLM usage
"""

import argparse
import json
import sys
from pathlib import Path

from pipeline import stages
from pipeline.config import load_config
from pipeline.database import get_connection, initialize_database


def cmd_index(cfg, args):
    for name in stages.INDEX_STAGES:
        if name in args.skip:
            print(f"[{name}] skipped")
            continue
        getattr(stages, f"run_{name}")(cfg)


def cmd_scoreboard(cfg, args):
    stages.run_scoreboard(cfg, sample_interval=args.interval,
                          start_time=args.start, end_time=args.end)


def cmd_transcribe(cfg, args):
    stages.run_transcribe(cfg, model_size=args.model_size)


def cmd_sequences(cfg, args):
    stages.run_sequences(cfg, event_ids=args.event_id or None, model=args.model,
                         budget=args.budget, refine=not args.no_refine,
                         media_resolution=args.media_resolution)


def cmd_embed(cfg, args):
    modalities = tuple(args.modality) if args.modality else ("text", "image")
    stages.run_embed(cfg, limit=args.limit, modalities=modalities)


def cmd_search(cfg, args):
    from pipeline.search import search_events

    import time

    query_vector = None
    with get_connection(cfg.db_path) as connection:
        if args.semantic and args.query:
            from pipeline.embeddings import MODEL_NAME, embed_query, make_gemini_client
            from pipeline.multimodal import record_embedding_usage

            started = time.perf_counter()
            result = embed_query(make_gemini_client(), args.query)
            query_vector = result.vector
            record_embedding_usage(connection, cfg.match_id, MODEL_NAME, "text", item_count=1,
                                   input_tokens=result.input_tokens, output_tokens=0,
                                   latency_ms=int((time.perf_counter() - started) * 1000))
        results = search_events(
            connection, cfg.match_id, query=args.query, query_vector=query_vector,
            event_types=args.event_types, statuses=args.statuses,
            start_time=args.start_time, end_time=args.end_time,
            limit=args.limit, include_context=not args.no_context,
        )
    print(json.dumps(results, indent=4, ensure_ascii=False))


def cmd_brief(cfg, args):
    from pipeline.briefs.parser import interpret_brief

    if args.file:
        raw_brief = Path(args.file).read_text(encoding="utf-8")
    elif args.text:
        raw_brief = args.text
    else:
        raise SystemExit("Provide brief text or --file.")

    initialize_database(cfg.db_path)
    with get_connection(cfg.db_path) as connection:
        brief_id, parsed, usage = interpret_brief(connection, cfg.match_id, raw_brief,
                                                  effort=args.effort)
    print(f"brief_id: {brief_id}")
    print(parsed.model_dump_json(indent=2))
    if usage["cache_hit"]:
        print(f"\n[cache hit] 0 tokens, {usage['latency_ms']} ms")
    else:
        print(f"\n[api] input={usage['input_tokens']} output={usage['output_tokens']} tokens,"
              f" cost=${usage['estimated_cost']:.4f}, api={usage['latency_ms']} ms,"
              f" total={usage['total_ms']} ms, request_id={usage['request_id']}")


STATUS_TABLES = [
    "matches", "shots", "windows", "keyframes", "teams", "players",
    "transcriptions", "audio_features", "audio_peaks", "scoreboard_observations",
    "card_events", "events", "event_evidence", "event_keyframes",
    "event_search_documents", "multimodal_embeddings", "creative_briefs",
    "goal_sequences", "frame_analyses",
]


def cmd_status(cfg, args):
    initialize_database(cfg.db_path)
    with get_connection(cfg.db_path) as c:
        print(f"Match: {cfg.match_id}\nDatabase: {cfg.db_path}\n\nRows:")
        for table in STATUS_TABLES:
            count = c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"  {table:<26}{count:>7}")

        print("\nEvents by type/status:")
        for row in c.execute(
            "SELECT event_type, json_extract(entities_json, '$.resolution_status') AS s,"
            " COUNT(*) AS n FROM events WHERE match_id = ? GROUP BY 1, 2 ORDER BY 1",
            (cfg.match_id,),
        ):
            print(f"  {row['event_type']:<26}{row['s'] or '-':<12}{row['n']:>5}")

        print("\nLatest stage runs:")
        for row in c.execute(
            "SELECT stage, status, elapsed_seconds, started_at FROM stage_runs s"
            " WHERE started_at = (SELECT MAX(started_at) FROM stage_runs WHERE stage = s.stage)"
            " ORDER BY started_at"
        ):
            elapsed = f"{row['elapsed_seconds']:.1f}s" if row["elapsed_seconds"] else "-"
            print(f"  {row['stage']:<14}{row['status']:<9}{elapsed:>10}  {row['started_at']}")

        print("\nLLM usage by stage:")
        for row in c.execute(
            "SELECT stage, model_name, COUNT(*) AS calls, SUM(cache_hit) AS hits,"
            " SUM(input_tokens) AS inp, SUM(output_tokens) AS outp,"
            " SUM(estimated_cost) AS cost FROM llm_usage GROUP BY 1, 2"
        ):
            print(f"  {row['stage']:<22}{row['model_name']:<18}calls={row['calls']}"
                  f" cache_hits={row['hits']} in={row['inp'] or 0} out={row['outp'] or 0}"
                  f" cost=${row['cost'] or 0:.4f}")

        print("\nEmbedding usage:")
        for row in c.execute(
            "SELECT model_name, modality, COUNT(*) AS runs, SUM(item_count) AS items,"
            " SUM(cache_hits) AS hits, SUM(input_tokens) AS inp,"
            " SUM(input_tokens IS NULL) AS untracked FROM embedding_usage GROUP BY 1, 2"
        ):
            print(f"  {row['model_name']:<22}{row['modality']:<11}runs={row['runs']}"
                  f" api_items={row['items']} cache_hits={row['hits']} in={row['inp'] or 0}"
                  + (f" (runs without token data: {row['untracked']})" if row["untracked"] else ""))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--match-id", help="Override MATCH_ID")
    parser.add_argument("--video", help="Override the match video path")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("index", help="Run every indexing stage")
    p.add_argument("--skip", action="append", default=[], choices=stages.INDEX_STAGES)
    p.set_defaults(func=cmd_index)

    for name in ["ingest", "rosters", "audio", "events"]:
        sub.add_parser(name).set_defaults(
            func=lambda cfg, args, n=name: getattr(stages, f"run_{n}")(cfg))

    p = sub.add_parser("transcribe")
    p.add_argument("--model-size", default="small")
    p.set_defaults(func=cmd_transcribe)

    p = sub.add_parser("scoreboard")
    p.add_argument("--interval", type=float, default=2.0)
    p.add_argument("--start", type=float, default=0.0)
    p.add_argument("--end", type=float)
    p.set_defaults(func=cmd_scoreboard)

    p = sub.add_parser("sequences", help="Buildup/goal/celebration boundaries (Gemini, stills only)")
    p.add_argument("--event-id", action="append", help="Default: all confirmed/likely goals")
    p.add_argument("--model", choices=["gemini-3.8-flash", "gemini-4-argon"])
    p.add_argument("--budget", type=int, default=18, help="Frames in the first round")
    p.add_argument("--no-refine", action="store_true")
    p.add_argument("--media-resolution", default="MEDIA_RESOLUTION_LOW",
                   choices=["MEDIA_RESOLUTION_LOW", "MEDIA_RESOLUTION_MEDIUM",
                            "MEDIA_RESOLUTION_HIGH"])
    p.set_defaults(func=cmd_sequences)

    p = sub.add_parser("embed")
    p.add_argument("--limit", type=int, help="Max new API calls this run")
    p.add_argument("--modality", action="append", choices=["text", "image"])
    p.set_defaults(func=cmd_embed)

    p = sub.add_parser("search")
    p.add_argument("query", nargs="?")
    p.add_argument("--semantic", action="store_true")
    p.add_argument("--type", dest="event_types", action="append")
    p.add_argument("--status", dest="statuses", action="append")
    p.add_argument("--start-time", type=float)
    p.add_argument("--end-time", type=float)
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--no-context", action="store_true")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("brief")
    p.add_argument("text", nargs="?")
    p.add_argument("--file")
    p.add_argument("--effort", default="low", choices=["low", "medium", "high"])
    p.set_defaults(func=cmd_brief)

    sub.add_parser("status").set_defaults(func=cmd_status)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    cfg = load_config(args.match_id, args.video)
    args.func(cfg, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
