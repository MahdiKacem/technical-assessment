from pipeline.database import initialize_database, persist_rosters
from pipeline.ingestion.roster import parse_roster_csv


MATCH_ID = "El classico 2017"
DB_PATH = "data/artifacts/El classico 2017/match.db"
ROSTER_PATHS = [
    "data/input/El_Clasico_2017_Lineups.xlsx - Barcelona.csv",
    "data/input/El_Clasico_2017_Lineups.xlsx - Real Madrid.csv",
]

rosters = [parse_roster_csv(path) for path in ROSTER_PATHS]

initialize_database(DB_PATH)
persist_rosters(DB_PATH, MATCH_ID, rosters)

for roster in rosters:
    print(
        f"{roster['team_name']}: "
        f"{len(roster['players'])} players"
    )
