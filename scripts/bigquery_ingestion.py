"""Refresh raw FPL data. Importing this module never accesses the network."""
import json
import logging
import os
from datetime import datetime, timezone
from google.cloud import bigquery
try:
    from .history_ingestion import fetch_json, fetch_histories, select_players, validate_season
    from .pipeline import Pipeline, content_hash
except ImportError:
    from history_ingestion import fetch_json, fetch_histories, select_players, validate_season
    from pipeline import Pipeline, content_hash

BOOTSTRAP_TABLES = {"elements": "players", "events": "gameweeks",
                    "element_types": "positions", "teams": "teams"}
BASE_URL = "https://fantasy.premierleague.com/api"


def replace_empty_dicts(obj):
    if isinstance(obj, dict):
        return {k: replace_empty_dicts(v) for k, v in obj.items()} if obj else None
    if isinstance(obj, list):
        return [replace_empty_dicts(v) for v in obj]
    return obj


def validate_catalog(bootstrap, fixtures):
    """Reject partial inputs before replacing any current raw table."""
    for source in BOOTSTRAP_TABLES:
        rows = bootstrap.get(source)
        if not isinstance(rows, list) or not rows or len({r["id"] for r in rows}) != len(rows):
            raise ValueError(f"Empty or duplicated {source}")
    if not fixtures or len({f["id"] for f in fixtures}) != len(fixtures):
        raise ValueError("Empty or duplicated fixtures")
    teams = {t["id"] for t in bootstrap["teams"]}
    positions = {p["id"] for p in bootstrap["element_types"]}
    if any(p["team"] not in teams or p["element_type"] not in positions
           or p["now_cost"] <= 0 for p in bootstrap["elements"]):
        raise ValueError("Invalid player mapping/price")
    if any(f["team_h"] not in teams or f["team_a"] not in teams for f in fixtures):
        raise ValueError("Invalid fixture team")


def ingest(pipeline, fetch=fetch_json, history_fetch=fetch_histories, now=None):
    now = now or datetime.now(timezone.utc)
    pipeline.claim_stage("ingestion")
    bootstrap = replace_empty_dicts(fetch(f"{BASE_URL}/bootstrap-static/"))
    fixtures = fetch(f"{BASE_URL}/fixtures/")
    validate_catalog(bootstrap, fixtures)
    validate_season(pipeline.season, bootstrap["events"])
    checks = pipeline.player_checks()
    previous = pipeline.previous_fixtures()
    selected, full_sweep, daily = select_players(
        bootstrap["elements"], fixtures, previous, checks, bootstrap["events"], now)
    logging.info("History selection run_id=%s players=%s full_sweep=%s daily=%s",
                 pipeline.run_id, len(selected), full_sweep, daily)
    histories = history_fetch(selected, pipeline.season, pipeline.run_id, now)
    observed_players = {h["player_id"] for h in histories}
    if any(p["id"] in selected and p.get("minutes", 0) > 0 and p["id"] not in observed_players
           for p in bootstrap["elements"]):
        raise ValueError("Empty history for a player with recorded season minutes")
    fixture_ids = {f["id"] for f in fixtures}
    if any(h["fixture_id"] not in fixture_ids for h in histories):
        raise ValueError("History references unknown current-season fixture")
    digest = content_hash({"bootstrap": bootstrap, "fixtures": fixtures})
    previous_run = pipeline.latest_success()
    changed_history = pipeline.merge_history(histories)
    stamp = now.isoformat()
    raw_tables = {table: bootstrap[key] for key, table in BOOTSTRAP_TABLES.items()}
    raw_tables["fixtures"] = fixtures
    # Serving never reads these independently replaced raw tables.
    for table, rows in raw_tables.items():
        pipeline.load_catalog(table, [dict(row, ingested_at=stamp, run_id=pipeline.run_id) for row in rows])
    pipeline.assert_owner()
    pipeline.record_checks(selected, bootstrap["elements"], full_sweep, daily, now)
    needs_build = (not previous_run or not previous_run.get("published_at")
                   or previous_run["content_hash"] != digest or changed_history > 0 or bool(selected)
                   or pipeline.history_changed_since(previous_run["checked_at"]))
    pipeline.complete_ingestion(digest, len(selected), len(histories), changed_history, needs_build, now)
    logging.info(json.dumps({"stage": "ingestion_complete", "run_id": pipeline.run_id,
                            "selected": len(selected), "history_rows": len(histories),
                            "changed_history": changed_history, "needs_build": needs_build}))


def main():
    logging.basicConfig(level=logging.INFO)
    pipeline = Pipeline(bigquery.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT", "fpl-optimizer-511321")))
    try:
        ingest(pipeline)
    except Exception:
        logging.exception("Ingestion failed run_id=%s; publication blocked", pipeline.run_id)
        raise


if __name__ == "__main__":
    main()
