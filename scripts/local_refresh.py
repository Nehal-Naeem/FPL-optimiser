"""Run real ingestion/dbt/publication in isolated BigQuery datasets for local testing.

Uses current ADC, never changes Scheduler/Cloud Run/IAM, and retains the lock on failure.
Run from the project root in the prepared Python 3.12 dbt environment.
"""
import json
import argparse
import logging
import os
from pathlib import Path
import subprocess
import sys
from uuid import UUID, uuid4

from google.cloud import bigquery

try:
    from .bigquery_ingestion import ingest
    from .dbt_publish import publish
    from .pipeline import Pipeline
except ImportError:
    from bigquery_ingestion import ingest
    from dbt_publish import publish
    from pipeline import Pipeline

ROOT = Path(__file__).resolve().parents[1]


def configure(resume=None):
    defaults = {"FPL_RAW_DATASET": "fpl_raw_localtest", "DBT_DATASET": "fpl_build_localtest",
                "FPL_ANALYTICS_DATASET": "fpl_analytics_localtest", "FPL_SEASON": "2026-27",
                "BIGQUERY_LOCATION": "US", "GOOGLE_CLOUD_PROJECT": "fpl-optimizer-511321",
                "DBT_SEND_ANONYMOUS_USAGE_STATS": "false"}
    for name, value in defaults.items():
        os.environ.setdefault(name, value)
    datasets = [os.environ[name] for name in ("FPL_RAW_DATASET", "DBT_DATASET", "FPL_ANALYTICS_DATASET")]
    if len(set(datasets)) != 3 or not all(name.endswith("_localtest") for name in datasets):
        raise ValueError("Local refresh requires three distinct _localtest datasets")
    run_id = str(UUID(resume)) if resume else str(uuid4())
    os.environ["FPL_RUN_ID"] = run_id
    os.environ["FPL_LOCAL_EXECUTION_ID"] = "local-" + run_id
    output = ROOT / "logs" / "local-refresh" / run_id
    output.mkdir(parents=True, exist_ok=True)
    os.environ["DBT_TARGET_PATH"] = str(output / "target")
    os.environ["DBT_LOG_PATH"] = str(output / "dbt")
    return output


def prepare(pipeline):
    for name in (pipeline.raw, pipeline.build, pipeline.analytics):
        dataset = bigquery.Dataset(f"{pipeline.project}.{name}")
        dataset.location = pipeline.location
        dataset.default_table_expiration_ms = 7 * 24 * 60 * 60 * 1000
        existing = pipeline.client.create_dataset(dataset, exists_ok=True)
        if existing.location.upper() != pipeline.location.upper():
            raise ValueError("Test dataset location mismatch")
    # Copy only existing API schemas. This does not read or overwrite production data.
    for name in ("players", "teams", "positions", "gameweeks", "fixtures"):
        schema = pipeline.client.get_table(f"{pipeline.project}.fpl_raw.{name}").schema
        pipeline.client.create_table(bigquery.Table(pipeline.table(name), schema=schema), exists_ok=True)
    pipeline.provision()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", help="Resume publication for a failed local run after all its jobs are terminal")
    args = parser.parse_args()
    output = configure(args.resume)
    logging.basicConfig(level=logging.INFO, handlers=[logging.StreamHandler(), logging.FileHandler(output / "refresh.log")])
    pipeline = Pipeline(bigquery.Client(project=os.environ["GOOGLE_CLOUD_PROJECT"]))
    logging.info("Local refresh run_id=%s artifacts=%s", pipeline.run_id, output)
    if args.resume:
        pipeline.assert_owner()
        active = [job.job_id for job in pipeline.client.list_jobs(
            all_users=True, state_filter=["pending", "running"])
            if (job.labels or {}).get("fpl_run") == pipeline.run_id]
        if active:
            raise RuntimeError(f"Local run still has active BigQuery jobs: {active}")
        pipeline.current_run()
        pipeline.query(f"UPDATE `{pipeline.table('pipeline_runs')}` SET build_execution=NULL "
                       "WHERE run_id=@run_id AND published_at IS NULL; ASSERT @@row_count=1;", run_id=pipeline.run_id)
    else:
        prepare(pipeline)
        pipeline.query(f"""BEGIN TRANSACTION;
        ASSERT (SELECT COUNT(*)=1 FROM `{pipeline.table('refresh_control')}` WHERE lock_id='refresh') AS 'Invalid lock singleton';
        UPDATE `{pipeline.table('refresh_control')}` SET owner=@run_id,acquired_at=CURRENT_TIMESTAMP(),ingestion_execution=NULL
        WHERE lock_id='refresh' AND owner IS NULL;
        ASSERT @@row_count=1 AS 'Another local refresh owns the lock'; COMMIT TRANSACTION;""", run_id=pipeline.run_id)
    try:
        if not args.resume:
            ingest(pipeline)
        def dbt(args):
            subprocess.run([str(Path(sys.executable).with_name("dbt")), *args,
                            "--project-dir", str(ROOT / "dbt/fpl_optimizer"),
                            "--profiles-dir", str(ROOT / "deploy/dbt-build")], check=True)
        publish(pipeline, run=dbt)
        pipeline.assert_owner()
        pipeline.query(f"UPDATE `{pipeline.table('refresh_control')}` SET owner=NULL,acquired_at=NULL "
                       "WHERE lock_id='refresh' AND owner=@run_id; ASSERT @@row_count=1;", run_id=pipeline.run_id)
        (output / "success.json").write_text(json.dumps({"run_id": pipeline.run_id,
            "raw": pipeline.raw, "build": pipeline.build, "analytics": pipeline.analytics}, indent=2))
        logging.info("Local refresh succeeded run_id=%s", pipeline.run_id)
    except Exception:
        logging.exception("Local refresh failed run_id=%s; lock retained for diagnosis", pipeline.run_id)
        raise


if __name__ == "__main__":
    main()
