# FPL BigQuery transformations

This dbt project reads the five FPL raw tables in
`fpl-optimizer-511321.fpl_raw`. Sources are declared in
[`models/staging/__sources.yml`](models/staging/__sources.yml).

## Data flow and technologies

The project uses dbt, BigQuery SQL, and the `dbt_utils` package. The upstream
Cloud Run ingestion job refreshes `players`, `gameweeks`, `positions`, `teams`,
and `fixtures` from the public FPL API. See the
[ingestion deployment README](../../deploy/bigquery-ingestion/README.md) for
setup and execution commands.

The Cloud Run job runs only `scripts/bigquery_ingestion.py`. It does not execute
dbt. Run transformations separately after ingestion.
The local DuckDB pipeline is separate; these BigQuery models do not update
`data/fpl.duckdb`.

## Models

- `models/staging/`: views for players, gameweeks, positions, teams, and fixtures.
- `models/intermediate/`: views for team fixtures, rolling team fixtures, and
  player outlook.
- `models/marts/mart_player_eval.sql`: player evaluation mart, materialized as
  a table.

The `seeds/` CSV files and `macros/cents_to_dollars.sql` are retained from the
Jaffle Shop starter template; the FPL staging models read BigQuery sources.

## Run transformations

Configure a BigQuery connection under the `fpl_optimizer` profile in
`~/.dbt/profiles.yml`, including the intended output dataset and credentials.
The dbt identity needs access to read the raw sources, run BigQuery jobs, and
create models in the output dataset. The ingestion service account's grants do
not configure credentials for local dbt.

With dbt and BigQuery support installed, run from this directory:

```sh
dbt deps
dbt build --select '+mart_player_eval'
```

This builds the evaluation mart and its upstream FPL models and runs their
associated tests. The selection excludes unrelated starter seeds. Staging and
intermediate models are materialized as views; the mart is materialized as a
table in the configured output dataset.
