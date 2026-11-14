"""Build candidates, inspect test results, then atomically publish one serving table."""
import json
import logging
import os
from pathlib import Path
import subprocess
from datetime import datetime, timezone

from google.api_core.exceptions import NotFound
from google.cloud import bigquery
try:
    from .pipeline import Pipeline
except ImportError:
    from pipeline import Pipeline

MODELS = ("mart_player_fixture_projection",
          "mart_player_gameweek_projection", "mart_recommendation_snapshot")


def run_dbt(args, run=subprocess.run):
    run(["dbt", *args], check=True)


def publish(pipeline, run=run_dbt):
    if pipeline.build in (pipeline.analytics, pipeline.raw):
        raise ValueError("DBT_DATASET must be isolated from raw and published datasets")
    pipeline.claim_stage("build")
    manifest = pipeline.current_run()
    snapshot = f"{pipeline.project}.{pipeline.analytics}.mart_recommendation_snapshot"
    try:
        published_table = pipeline.client.get_table(snapshot)
        exists = True
        projection_ready = {"projections","contract_version"}.issubset({field.name for field in published_table.schema})
    except NotFound:
        exists = False
        projection_ready = False
    if not manifest["needs_build"] and exists and projection_ready and os.getenv("FPL_FORCE_BUILD", "false").lower() != "true":
        # Time itself can advance the actionable horizon, even without changed metric payloads.
        expired = pipeline.query(f"SELECT COUNTIF(p.deadline_time<=@checked_at)>0 AS expired "
                                 f"FROM `{snapshot}` s, UNNEST(s.projections) p", checked_at=manifest["checked_at"])
        if expired[0]["expired"]:
            manifest["needs_build"] = True
    if not manifest["needs_build"] and exists and projection_ready and os.getenv("FPL_FORCE_BUILD", "false").lower() != "true":
        # Heartbeat updates metadata atomically without changing publication ID/rankings.
        pipeline.assert_owner()
        pipeline.query(f"UPDATE `{snapshot}` SET last_checked_at=@checked_at",
                       checked_at=manifest["checked_at"])
        mark_published(pipeline)
        logging.info("No input changes; skipped dbt run_id=%s", pipeline.run_id)
        return
    run(["source", "freshness"])
    # All candidate model, source, singular and unit tests run before any publication.
    run(["build", "--exclude", "resource_type:seed"])
    artifacts = Path(os.environ.get("DBT_TARGET_PATH", "target"))
    results = json.loads((artifacts / "run_results.json").read_text())
    bad = [r for r in results["results"] if r["status"] not in ("success", "pass", "warn")]
    built_models = {r["unique_id"] for r in results["results"] if r["status"] == "success"}
    if bad or not {"model.fpl_optimizer." + m for m in MODELS}.issubset(built_models):
        raise RuntimeError("dbt artifacts contain failed/skipped resources; refusing publication")
    pipeline.assert_owner()
    # Keep versioned inputs/results for forward evaluation; do not overwrite previous observations.
    suffix = pipeline.run_id.replace("-", "_")
    if not suffix or not suffix.replace("_", "").isalnum():
        raise ValueError("Invalid run ID for snapshot archive")
    for model in MODELS:
        source = f"{pipeline.project}.{pipeline.build}.{model}"
        archive = f"{pipeline.project}.{pipeline.analytics}.{model}_{suffix}"
        copy(pipeline, source, archive, "WRITE_EMPTY", retain=True)
    # Preserve the previous serving contract before atomic publication.
    if exists:
        copy(pipeline, snapshot, snapshot + "_previous", "WRITE_TRUNCATE", retain=True)
    pipeline.assert_owner()
    copy(pipeline, f"{pipeline.project}.{pipeline.build}.mart_recommendation_snapshot",
         snapshot, "WRITE_TRUNCATE", retain=True)
    mark_published(pipeline)
    logging.info("Published validated snapshot run_id=%s", pipeline.run_id)


def copy(pipeline, source, target, disposition, retain=False):
    pipeline.wait(pipeline.client.copy_table(source, target, location=pipeline.location,
        job_config=bigquery.CopyJobConfig(write_disposition=disposition, labels=pipeline.labels)), "copy")
    if retain:
        table = pipeline.client.get_table(target)
        table.expires = None
        pipeline.client.update_table(table, ["expires"])


def mark_published(pipeline):
    pipeline.query(f"UPDATE `{pipeline.table('pipeline_runs')}` SET published_at=@now "
                   "WHERE run_id=@run_id", now=datetime.now(timezone.utc), run_id=pipeline.run_id)


def main():
    logging.basicConfig(level=logging.INFO)
    pipeline = Pipeline(bigquery.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT", "fpl-optimizer-511321")))
    try:
        publish(pipeline)
    except Exception:
        logging.exception("Build/publication failed run_id=%s; refresh lock retained", pipeline.run_id)
        raise


if __name__ == "__main__":
    main()
