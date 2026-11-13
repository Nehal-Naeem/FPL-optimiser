# FPL Optimiser

FPL data ingestion and player evaluation pipelines for BigQuery and local DuckDB.
The React frontend imports public FPL squads, finds cheaper players with higher
viability, and optimizes full squads or a limited number of transfers.

## Frontend and API

Use Node 22+ and Python 3.12 for new environments. The web dependencies are
separate from the ingestion and DuckDB environments:

```sh
python3.12 -m venv .venv-web
.venv-web/bin/python -m pip install -r backend/requirements-dev.txt
gcloud auth application-default login
.venv-web/bin/python -m uvicorn backend.app:app --reload --port 8000
```

In a second terminal:

```sh
cd frontend
npm ci
npm run dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/api` to FastAPI. Application Default
Credentials need BigQuery Job User and read access to `fpl_raw` and
`fpl_analytics`. Credentials stay on the server. See
[deployment instructions](deploy/frontend/README.md) for a single-origin Cloud Run
image and a dedicated runtime identity. Deployment is a separate manual step.

The interface supports editing the imported deadline snapshot, bank, and selling
prices. Selling prices initially use marked market-price estimates: the public
team API does not expose purchase history or exact selling prices. Changes are
local to the current browser session and never execute FPL transfers. Reloading
the page resets squad edits.

Player cards, replacement comparisons, and optimizer results show the next five
unstarted fixtures per club, including separate matches in double gameweeks.
Badges show opponent abbreviations and H/A with difficulty colours. Focus or
select a badge for the full opponent, gameweek, local kickoff time, and
difficulty; Escape or selecting outside dismisses details. Undated matches appear
after dated matches with a TBC label. Fewer than five remaining matches are shown
without invented fixtures. Fixture updates participate in dataset versioning.

Clicking an open fixture badge again collapses its details; clicking another
switches the displayed match. Keyboard focus still opens details, while Enter
and Space toggle them.

Hover over a player name for a compact statistics preview after 200ms. Click
once to keep it open, and click again to close it. Touch users tap to toggle;
keyboard users activate a focused name with Enter/Space. Only one player
popover is shown at a time. Escape, the close button, or an outside click closes
it. Previews remain open while moving between the name and popover; pinned
popovers stay open when the pointer leaves. Scrolling outside a popover dismisses
it, and resizing repositions it within the viewport. Popovers do not resize
cards and are rendered outside scrolling lists to avoid clipping.

The popover shows form and points-per-gameweek percentiles from the existing
BigQuery model, as percentages to one decimal place. Missing values display
"Unavailable". Comparisons are within position among scored players. Squad-card
popovers include a collapsed weighted-score breakdown and availability news.
Percentile values remain hidden until requested; no double-click is required.

Replacement suggestions must be same-position, strictly cheaper than the
outgoing selling price, and strictly higher in viability, while preserving club
limits and avoiding already-owned players. Each is an independent swap. Applying
one updates the local bank and recalculates suggestions for the edited squad.

The optimizer maximizes total squad viability, including bench players, using
OR-Tools CP-SAT with a ten-second limit. It enforces 2 GK / 5 DEF / 5 MID / 3 FWD,
at most three per club, unique players, and the chosen budget. Ideal mode defaults
to £100m. Transfer mode defaults to one transfer, funded by bank and actual sale
proceeds; ties favor fewer transfers, then more money remaining. Injured or
flagged scored players stay eligible, with warnings. Unscored imported players
stay fixed in transfer mode and are excluded from comparisons and ideal squads.
Viability is a ranking metric, not predicted FPL points; points hits, captaincy,
starting XI selection, and multiweek planning are not modeled.

### Validation

```sh
.venv-web/bin/python -m pytest backend/tests -q
cd frontend
npm run build
npx playwright install chromium  # Once, if no local browser is configured.
npm test
```

Browser tests launch a deterministic test-only API (`backend.tests.preview`) and
exercise the real optimizer on desktop and mobile. They make no production API
or BigQuery requests. On macOS, an installed Chrome can be used without a browser
download:

```sh
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' npm test
```

Browser tests use ports 8002 and 5174, independently of the local app on 8000 and 5173. API documentation is at
`http://127.0.0.1:8000/docs`. `/api/health` is a process check;
`/api/players` also verifies cloud data access. Requests carry a dataset version
and return HTTP 409 if the cached data has refreshed. Reloading player data in the
interface preserves squad edits and clears stale calculations.

## Architecture and technologies

- The public Fantasy Premier League API supplies player, team, gameweek,
  position, and fixture data. HTTP requests use `requests`.
- Python, pandas, and DuckDB power the local refresh and evaluation pipeline.
- Separate Python 3.12 Docker containers run ingestion and dbt as Cloud Run jobs.
  Cloud Build builds the image, Artifact Registry stores it, and the
  `google-cloud-bigquery` client loads data into BigQuery. Cloud Scheduler triggers
  a Google Cloud Workflow every six hours to run ingestion before the dbt build.
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
Ingestion runs as part of the scheduled refresh workflow. To run ingestion alone:

```sh
gcloud run jobs execute fpl-bigquery-ingestion \
  --project=fpl-optimizer-511321 --region=us-central1 --wait
```

The separate `fpl-dbt-build` Cloud Run job refreshes transformations in
`fpl_analytics`. The `fpl-refresh` workflow runs ingestion and then dbt, waiting
for each job to succeed. Scheduler `FPL-bigquery-ingestion` triggers the workflow
at 00:00, 06:00, 12:00, and 18:00 `America/Vancouver`; manual workflow runs remain
available. Deployment scripts do not execute the jobs; a separate `schedule.sh`
configures the existing scheduler. See the [dbt job instructions](deploy/dbt-build/README.md)
and [refresh workflow instructions](deploy/fpl-refresh/README.md).

To deploy `scripts/bigquery_ingestion.py` as a Google Cloud Run job, follow the
[setup and deployment instructions](deploy/bigquery-ingestion/README.md).
For the BigQuery transformation models, see the [dbt README](dbt/fpl_optimizer/README.md).
