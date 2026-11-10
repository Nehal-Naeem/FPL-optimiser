from google.cloud import bigquery
import requests
from datetime import datetime, timezone

PROJECT_ID = 'fpl-optimizer-511321'
DATASET_ID = 'fpl_raw'

client = bigquery.Client(project=PROJECT_ID)
# table_id = "fpl-optimizer-511321.fpl_raw.players"

fixtures_url = "https://fantasy.premierleague.com/api/fixtures"
bootstrap_url = "https://fantasy.premierleague.com/api/bootstrap-static/"

bootstrap = requests.get(bootstrap_url).json()
fixtures = requests.get(fixtures_url).json()

ingested_at = datetime.now(timezone.utc).isoformat()

bootstrap_tables = {
    "elements" : "players",
    "events" : "gameweeks",
    "element_types" : "positions",
    "teams" : "teams"
}

job_config = bigquery.LoadJobConfig(
    write_disposition = "WRITE_TRUNCATE"
)

def replace_empty_dicts(obj):
    if isinstance(obj, dict):
        if not obj:
            return None
        
        return {
            k: replace_empty_dicts(v)
            for k, v in obj.items()
        }

    if isinstance(obj, list):
        return [
            replace_empty_dicts(v)
            for v in obj
        ]

    return obj

bootstrap = replace_empty_dicts(bootstrap)

jobs = []

for source_key, table_name in bootstrap_tables.items():
    
    rows = bootstrap[source_key]

    for row in rows:
        row["ingested_at"] = ingested_at

    table_id = f"{PROJECT_ID}.{DATASET_ID}.{table_name}"

    job = client.load_table_from_json(
        rows,
        table_id,
        job_config=job_config
    )

    jobs.append((table_name, job))

for fixture in fixtures:
    fixture["ingested_at"] = ingested_at

fixtures_job = client.load_table_from_json(
    fixtures,
    f"{PROJECT_ID}.{DATASET_ID}.fixtures",
    job_config=job_config
)

jobs.append(("fixtures", fixtures_job))

for table_name, job in jobs:
    try:
        job.result()
        print(f"Successfully loaded {table_name}")
    except Exception as e:
        print(f"Failed to load {table_name}")
        print(e)









# players = bootstrap["elements"]
# gameweeks = bootstrap["events"]
# positions = bootstrap["element_types"]
# teams = bootstrap["teams"]

# for player in players:
#     player["ingetsed_at"] = datetime.now(timezone.utc)
# for gameweek in gameweeks:
#     gameweek["ingetsed_at"] = datetime.now(timezone.utc)
# for position in positions:
#     position["ingetsed_at"] = datetime.now(timezone.utc)
# for team in teams:
#     team["ingetsed_at"] = datetime.now(timezone.utc)

# players_df = con.execute("""
#     SELECT * FROM players
# """).fetchdf()
 
# players_df["ingested_at"] = datetime.now(timezone.utc)

# job = client.load_table_from_dataframe(
#     players_df,
#     table_id,
#     job_config=job_config
# )

# job.result()

# print(f"players_df shape: {players_df.shape}")
# print(f"first 10 players: {players_df["id", "web_name", "team", "now_cost", "form"].head()}")
