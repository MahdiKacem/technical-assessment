import argparse
import json

from pipeline.database import get_connection
from pipeline.search import search_events


parser = argparse.ArgumentParser()
parser.add_argument("query", nargs="?", default=None)
parser.add_argument("--match-id", default="El classico 2017")
parser.add_argument("--database", default="data/artifacts/El classico 2017/match.db")
parser.add_argument("--type", dest="event_types", action="append")
parser.add_argument("--status", dest="statuses", action="append")
parser.add_argument("--start-time", type=float)
parser.add_argument("--end-time", type=float)
parser.add_argument("--limit", type=int, default=10)
parser.add_argument("--no-context", action="store_true")
args = parser.parse_args()

with get_connection(args.database) as connection:
    results = search_events(
        connection,
        args.match_id,
        query=args.query,
        event_types=args.event_types,
        statuses=args.statuses,
        start_time=args.start_time,
        end_time=args.end_time,
        limit=args.limit,
        include_context=not args.no_context,
    )

print(json.dumps(results, indent=4, ensure_ascii=False))
