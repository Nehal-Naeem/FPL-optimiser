# FPL Optimiser

A small local Streamlit app for viewing a public FPL squad against the existing
DuckDB player evaluations and finding affordable replacements.

## Run

From the project directory (Python 3.9+):

```sh
python3 -m venv .venv  # Only needed if the environment does not exist.
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py --server.address 127.0.0.1
```

Open http://localhost:8501, enter an FPL team ID, and click **Load squad**.
Find the ID in your FPL points-page URL: `/entry/<team_id>/event/<gameweek>`.
Submitting again fetches fresh public picks; changing the selected player does
not refetch the API.

The app opens `data/fpl.duckdb` **read-only** and never runs the existing pipeline.
`players`, `positions`, `teams`, and `mart_player_evaluation` must already exist.
Database paths are resolved relative to `database.py`, not the working directory.
If another process holds a conflicting DuckDB connection, close it and rerun the app.

## Behavior

- Fetches the entry's latest published gameweek picks, including all substitutes.
  The public API does not expose a manager's unpublished post-deadline squad.
- Matches players by FPL element ID. The database must be from the same season;
  player IDs can be reused between seasons. API labels preserve unmatched rows.
- Reads all evaluation metrics directly from `mart_player_evaluation`.
  **`viability_per_cost` is only a SQL alias for existing `viability_by_cost`.**
  Neither metric is recalculated, normalized, or substituted in application code.
- Displays missing metrics as blanks and excludes unevaluated players from
  recommendations requiring a comparison. Matched costs come from the database;
  API prices are used only as a display fallback for unmatched squad players.
- Lists the lowest-scoring squad players, then shows the best replacement for
  each outgoing player in two views, ranked by stored viability or stored value.
- Allows selection of any squad member; defaults to the lowest evaluated score.
  The detailed table lists all eligible replacements by descending viability.
- The sidebar holds the team input and a **Show detailed stats** toggle. The main
  view focuses on the roster, selected-player summary, and replacements; the
  broader **Best Transfers** comparison is collapsed below them.
- Form and points percentiles, normalized fixture ease, and start ratio display
  as percentages. Viability and value remain scores. Formatting does not change
  the stored values or recommendation order.
- Replacements must share the position, cost no more, have strictly higher
  viability, and not already be in the squad. Gain is the difference between
  stored viability scores; price difference is candidate minus outgoing cost.
- Suggestions are independent, not a multi-transfer plan. V1 does not enforce
  club limits or account for bank balance, selling prices, or transfer hits.

## Files

- `app.py`: Streamlit UI.
- `database.py`: reusable read-only DuckDB access.
- `fpl_api.py`: public API requests and squad labels.
- `recommendations.py`: squad matching, eligibility filtering and ranking.
- `main.py`: production data refresh and evaluation pipeline.
- `fixtures.py`: existing pipeline dependency, imported by `main.py`.
- `notebooks/history.ipynb`: historical CSV analysis. Data paths work when the
  notebook kernel starts in the project root or in `notebooks/`.
- `scripts/experimental/squad_fetch_demo.py`: original squad-fetching prototype
  with a hardcoded team ID and gameweek.
- `scripts/experimental/player_ranking_query.py`: exploratory ranking query with
  weights of 0.35 form, 0.40 fixture ease, and 0.25 points. Production weights in
  `main.py` remain 0.30, 0.45, and 0.25 respectively.
- `data/fpl.duckdb`: existing database snapshot, read-only in the app.
- `data/history/{fixtures,gws,teams}/`: preserved historical seasonal CSVs;
  the notebook reads fixtures and gameweeks. The app does not use these CSVs.
- `tests/test_app.py`: API, database, recommendation, and Streamlit checks.
- `.venv/`: local Python environment, kept in place and excluded by `.gitignore`.

Run pipeline and experimental scripts from the project directory so their
existing relative database paths resolve correctly:

```sh
.venv/bin/python main.py
.venv/bin/python scripts/experimental/squad_fetch_demo.py
.venv/bin/python scripts/experimental/player_ranking_query.py
```

`main.py` refreshes and rebuilds database tables. Its import of `fixtures.py`
also fetches fixtures and opens a database connection. Use the Streamlit command
in **Run** to view the saved snapshot without refreshing it.

## Checks

```sh
.venv/bin/python -m unittest discover -s tests -v
```

Tests use controlled API responses and a temporary database; they do not refresh
or write to `data/fpl.duckdb`.
