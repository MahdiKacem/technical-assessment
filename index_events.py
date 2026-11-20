from pipeline.database import get_connection, initialize_database
from pipeline.search import build_event_search_index


MATCH_ID = "El classico 2017"
DB_PATH = "data/artifacts/El classico 2017/match.db"


initialize_database(DB_PATH)

with get_connection(DB_PATH) as connection:
    count = build_event_search_index(connection, MATCH_ID)

print(f"Indexed {count} events.")
