from google.cloud import bigquery
import requests
from datetime import datetime, timezone
import os

PROJECT_ID = os.environ.get('GOOGLE_CLOUD_PROJECT', 'fpl-optimizer-511321')
DATASET_ID = os.environ.get('BIGQUERY_DATASET', 'fpl_raw')

client = bigquery.Client(project=PROJECT_ID)
# table_id = "fpl-optimizer-511321.fpl_raw.players"

fixtures_url = "https://fantasy.premierleague.com/api/fixtures"
bootstrap_url = "https://fantasy.premierleague.com/api/bootstrap-static/"

def fetch_json(url):
    response = requests.get(url, timeout=(10, 60))
    response.raise_for_status()
    return response.json()


bootstrap = fetch_json(bootstrap_url)
fixtures = fetch_json(fixtures_url)

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

failed_tables = []
for table_name, job in jobs:
    try:
        job.result()
        print(f"Successfully loaded {table_name}", flush=True)
    except Exception as e:
        print(f"Failed to load {table_name}")
        print(e, flush=True)
        failed_tables.append(table_name)

if failed_tables:
    raise RuntimeError(f"BigQuery loads failed: {', '.join(failed_tables)}")
