# FPL Optimiser

FPL data ingestion and player evaluation pipelines for BigQuery and local DuckDB.
The previous frontend has been removed so a new frontend can be built from scratch.

## Architecture and technologies

- The public Fantasy Premier League API supplies player, team, gameweek,
  position, and fixture data. HTTP requests use `requests`.
- Python, pandas, and DuckDB power the local refresh and evaluation pipeline.
- A Python 3.12 Docker container runs raw ingestion as a Google Cloud Run job.
  Cloud Build builds the image, Artifact Registry stores it, and the
  `google-cloud-bigquery` client loads data into BigQuery.
- dbt and `dbt_utils` define BigQuery staging views, intermediate views, and a
  player evaluation mart.

The local DuckDB and BigQuery pipelines are separate. Refreshing BigQuery or
running dbt does not update `data/fpl.duckdb`.

## Local DuckDB pipeline

From the project directory (Python 3.9+):

```sh
python3 -m venv .venv  # Only needed if the environment does not exist.
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python main.py
```

`main.py` fetches current FPL data and rebuilds the raw tables, fixture tables,
player outlook, and `mart_player_evaluation` in `data/fpl.duckdb`. Run it from the
project directory so its relative database path resolves correctly.

## Files

- `main.py`: local DuckDB refresh and evaluation pipeline.
- `fixtures.py`: standalone local fixture-fetching script.
- `data/fpl.duckdb`: existing local database snapshot.
- `data/history/{fixtures,gws,teams}/`: historical seasonal CSVs.
- `notebooks/history.ipynb`: historical CSV analysis. Data paths work when the
  notebook kernel starts in the project root or in `notebooks/`.
- `scripts/bigquery_ingestion.py`: BigQuery raw ingestion script.
- `deploy/bigquery-ingestion/`: Cloud Run deployment configuration and instructions.
- `dbt/fpl_optimizer/`: BigQuery transformation models and dbt configuration.
- `scripts/experimental/squad_fetch_demo.py`: squad-fetching prototype with a
  hardcoded team ID and gameweek.
- `scripts/experimental/player_ranking_query.py`: exploratory DuckDB ranking query
  with weights of 0.35 form, 0.40 fixture ease, and 0.25 points. Production weights
  in `main.py` remain 0.30, 0.45, and 0.25 respectively.
- `.venv/`: local Python environment, kept in place and excluded by `.gitignore`.

Run experimental scripts from the project directory:

```sh
.venv/bin/python scripts/experimental/squad_fetch_demo.py
.venv/bin/python scripts/experimental/player_ranking_query.py
```

## BigQuery ingestion job

Cloud Run job `fpl-bigquery-ingestion` runs `scripts/bigquery_ingestion.py` in
project `fpl-optimizer-511321`, region `us-central1`. It replaces the `players`,
`gameweeks`, `positions`, `teams`, and `fixtures` tables in `fpl_raw`.

The runtime service account is
`fpl-ingestion@fpl-optimizer-511321.iam.gserviceaccount.com`, with
`roles/bigquery.jobUser` and `roles/bigquery.dataEditor` granted at project level.
Ingestion is run manually. Run the deployed job with:

```sh
gcloud run jobs execute fpl-bigquery-ingestion \
  --project=fpl-optimizer-511321 --region=us-central1 --wait
```

Run dbt separately after ingestion to refresh the BigQuery transformation models.

To deploy `scripts/bigquery_ingestion.py` as a Google Cloud Run job, follow the
[setup and deployment instructions](deploy/bigquery-ingestion/README.md).
For the BigQuery transformation models, see the [dbt README](dbt/fpl_optimizer/README.md).
