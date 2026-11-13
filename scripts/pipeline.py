"""BigQuery run manifests, typed history merges and fail-closed ownership checks."""
import hashlib
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from google.cloud import bigquery
try:
    from .history_ingestion import COUNTS, DECIMALS
except ImportError:
    from history_ingestion import COUNTS, DECIMALS


def identifier(value):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("Invalid configuration identifier")
    return value


def content_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


HISTORY_SCHEMA = [bigquery.SchemaField(n, t) for n, t in (
    [("season", "STRING"), ("player_id", "INT64"), ("fixture_id", "INT64"), ("gameweek", "INT64"),
     ("opponent_team", "INT64"), ("was_home", "BOOL"), ("kickoff_time", "TIMESTAMP"), ("modified", "BOOL")]
    + [(n, "INT64") for n in COUNTS] + [(n, "NUMERIC") for n in DECIMALS]
    + [("payload_hash", "STRING"), ("ingested_at", "TIMESTAMP"), ("run_id", "STRING")])]


class Pipeline:
    def __init__(self, client):
        self.client = client
        self.project = identifier(os.getenv("GOOGLE_CLOUD_PROJECT", "fpl-optimizer-511321"))
        self.raw = identifier(os.getenv("FPL_RAW_DATASET", os.getenv("BIGQUERY_DATASET", "fpl_raw")))
        self.build = identifier(os.getenv("DBT_DATASET", "fpl_build"))
        self.analytics = identifier(os.getenv("FPL_ANALYTICS_DATASET", "fpl_analytics"))
        self.season = os.getenv("FPL_SEASON", "2026-27")
        self.run_id = os.getenv("FPL_RUN_ID", "")
        self.location = os.getenv("BIGQUERY_LOCATION", "US")
        self._fixtures = []

    def table(self, name):
        return f"{self.project}.{self.raw}.{identifier(name)}"

    @property
    def labels(self):
        return {"fpl_run": re.sub(r"[^a-z0-9_-]", "_", self.run_id.lower())[:63] or "setup"}

    def wait(self, job, action, timeout=None):
        logging.info("BigQuery action=%s run_id=%s job_id=%s", action, self.run_id, job.job_id)
        return job.result(timeout=timeout)

    def query(self, sql, **parameters):
        params = [bigquery.ScalarQueryParameter(k, "BOOL" if isinstance(v, bool) else
                  "TIMESTAMP" if isinstance(v, datetime) else "INT64" if isinstance(v, int) else "STRING", v)
                  for k, v in parameters.items()]
        job = self.client.query(sql, location=self.location, job_config=bigquery.QueryJobConfig(
            query_parameters=params, maximum_bytes_billed=100_000_000, labels=self.labels))
        result = self.wait(job, "query", timeout=180)
        return [dict(row) for row in result]

    def assert_owner(self):
        if not self.run_id:
            raise RuntimeError("FPL_RUN_ID is required; execute through the refresh workflow")
        self.query(f"""ASSERT (SELECT COUNT(*) = 1 AND COUNTIF(owner = @run_id) = 1
            FROM `{self.table('refresh_control')}` WHERE lock_id = 'refresh')
            AS 'Refresh lock is not owned by this execution';""", run_id=self.run_id)

    def claim_stage(self, stage):
        """Fence duplicate job submissions within the same workflow, not just different workflows."""
        self.assert_owner()
        execution = os.getenv("CLOUD_RUN_EXECUTION", "")
        if not execution and os.getenv("FPL_LOCAL_EXECUTION_ID"):
            if not all(dataset.endswith("_localtest") for dataset in (self.raw, self.build, self.analytics)):
                raise RuntimeError("Local stage claims require isolated _localtest datasets")
            execution = os.environ["FPL_LOCAL_EXECUTION_ID"]
        if not execution:
            raise RuntimeError("CLOUD_RUN_EXECUTION is required for a stage claim")
        if stage == "ingestion":
            table, field = self.table("refresh_control"), "ingestion_execution"
            predicate, parameters = "lock_id='refresh' AND owner=@run_id", {}
        elif stage == "build":
            table, field = self.table("pipeline_runs"), "build_execution"
            predicate = "run_id=@run_id AND season=@season AND ingestion_complete"
            parameters = {"season": self.season}
        else:
            raise ValueError("Unknown pipeline stage")
        self.query(f"""BEGIN TRANSACTION;
            ASSERT (SELECT COUNT(*)=1 FROM `{table}` WHERE {predicate}) AS 'Missing/duplicated stage owner';
            UPDATE `{table}` SET {field}=@execution WHERE {predicate} AND {field} IS NULL;
            ASSERT @@row_count=1 AS 'Stage already claimed by another job execution';
            COMMIT TRANSACTION;""", run_id=self.run_id, execution=execution, **parameters)

    def player_checks(self):
        rows = self.query(f"""SELECT c.*, ARRAY(
            SELECT DISTINCT IF(h.was_home, f.team_h, f.team_a)
            FROM `{self.table('player_fixture_history')}` h
            JOIN `{self.table('fixtures')}` f ON h.fixture_id = f.id
            WHERE h.season = c.season AND h.player_id = c.player_id
        ) AS historical_team_ids
        FROM `{self.table('player_history_checks')}` c WHERE season = @season""", season=self.season)
        return {r["player_id"]: r for r in rows}

    def latest_success(self):
        rows = self.query(f"SELECT * FROM `{self.table('pipeline_runs')}` WHERE season = @season "
                          "AND ingestion_complete ORDER BY checked_at DESC LIMIT 1", season=self.season)
        return rows[0] if rows else None

    def previous_fixtures(self):
        row = self.latest_success()
        return {f["id"]: f for f in json.loads(row["fixtures_json"])} if row else {}

    def history_changed_since(self, checked_at):
        # A failed run may have merged corrections before it could write its manifest.
        rows = self.query(f"SELECT COUNTIF(ingested_at>@checked_at)>0 AS dirty "
                          f"FROM `{self.table('player_fixture_history')}` WHERE season=@season",
                          checked_at=checked_at, season=self.season)
        return rows[0]["dirty"]

    def merge_history(self, rows):
        if not rows:
            return 0
        self.assert_owner()
        stage = self.table("history_stage_" + uuid4().hex)
        table = bigquery.Table(stage, schema=HISTORY_SCHEMA)
        table.expires = datetime.now(timezone.utc) + timedelta(days=1)
        self.client.create_table(table)
        self.wait(self.client.load_table_from_json(rows, stage, job_config=bigquery.LoadJobConfig(
            schema=HISTORY_SCHEMA, write_disposition="WRITE_TRUNCATE", labels=self.labels), location=self.location), "history_load")
        fields = [f.name for f in HISTORY_SCHEMA]
        update = ", ".join(f"{f}=s.{f}" for f in fields if f not in ("season", "player_id", "fixture_id"))
        result = self.query(f"""MERGE `{self.table('player_fixture_history')}` t USING `{stage}` s
            ON t.season=s.season AND t.player_id=s.player_id AND t.fixture_id=s.fixture_id
            WHEN MATCHED AND t.payload_hash != s.payload_hash THEN UPDATE SET {update}
            WHEN NOT MATCHED THEN INSERT ({', '.join(fields)}) VALUES ({', '.join('s.' + f for f in fields)});
            SELECT @@row_count AS changed;""")
        return result[0]["changed"]

    def load_catalog(self, table, rows):
        self.assert_owner()
        if table == "fixtures":
            self._fixtures = [{k: v for k, v in r.items() if k not in ("ingested_at", "run_id")} for r in rows]
        # Existing API table schemas are retained; append only our STRING run identifier.
        target = self.table(table)
        existing = self.client.get_table(target)
        schema = list(existing.schema)
        if "run_id" not in {f.name for f in schema}:
            schema.append(bigquery.SchemaField("run_id", "STRING"))
        self.wait(self.client.load_table_from_json(rows, target, job_config=bigquery.LoadJobConfig(
            schema=schema, write_disposition="WRITE_TRUNCATE", labels=self.labels), location=self.location), "catalog_load")
        self.query(f"ASSERT (SELECT COUNT(*) = @count AND COUNTIF(run_id = @run_id) = @count "
                   f"FROM `{target}`) AS 'Raw load count/run mismatch';", count=len(rows), run_id=self.run_id)

    def record_checks(self, selected, players, full, daily, now):
        self.assert_owner()
        selected = set(selected)
        # Once-per-day cadence is global, while checked_at records actual successful requests only.
        if daily:
            self.query(f"UPDATE `{self.table('player_history_checks')}` SET daily_checked_at=@now "
                       "WHERE season=@season", now=now, season=self.season)
        if not selected:
            return
        rows = [{"season": self.season, "player_id": p["id"], "team_id": p["team"],
                 "checked_at": now.isoformat(), "full_checked_at": now.isoformat() if full else None,
                 "daily_checked_at": now.isoformat() if daily else None, "run_id": self.run_id}
                for p in players if p["id"] in selected]
        stage = self.table("checks_stage_" + uuid4().hex)
        schema = self.client.get_table(self.table("player_history_checks")).schema
        table = bigquery.Table(stage, schema=schema)
        table.expires = now + timedelta(days=1)
        self.client.create_table(table)
        self.wait(self.client.load_table_from_json(rows, stage, job_config=bigquery.LoadJobConfig(
            schema=schema, labels=self.labels), location=self.location), "checks_load")
        self.query(f"""MERGE `{self.table('player_history_checks')}` t USING `{stage}` s
            ON t.season=s.season AND t.player_id=s.player_id
            WHEN MATCHED THEN UPDATE SET team_id=s.team_id, checked_at=s.checked_at, run_id=s.run_id,
                full_checked_at=COALESCE(s.full_checked_at,t.full_checked_at),
                daily_checked_at=COALESCE(s.daily_checked_at,t.daily_checked_at)
            WHEN NOT MATCHED THEN INSERT
                (season,player_id,team_id,checked_at,full_checked_at,daily_checked_at,run_id)
            VALUES(s.season,s.player_id,s.team_id,s.checked_at,
                COALESCE(s.full_checked_at,s.checked_at),COALESCE(s.daily_checked_at,s.checked_at),s.run_id)""")

    def complete_ingestion(self, digest, selected, rows, changed, needs_build, now):
        self.query(f"""INSERT INTO `{self.table('pipeline_runs')}`
            (run_id, season, checked_at, content_hash, selected_players, history_rows, changed_history,
             needs_build, ingestion_complete, fixtures_json)
            VALUES (@run_id,@season,@now,@digest,@selected,@rows,@changed,@needs_build,TRUE,@fixtures)""",
            run_id=self.run_id, season=self.season, now=now, digest=digest, selected=selected,
            rows=rows, changed=changed, needs_build=needs_build, fixtures=json.dumps(self._fixtures))

    def current_run(self):
        rows = self.query(f"SELECT * FROM `{self.table('pipeline_runs')}` WHERE run_id=@run_id "
                          "AND season=@season AND ingestion_complete", run_id=self.run_id, season=self.season)
        if len(rows) != 1:
            raise RuntimeError("Exactly one complete ingestion manifest is required")
        for name in ("players", "teams", "positions", "fixtures", "gameweeks"):
            self.query(f"ASSERT (SELECT COUNT(*) > 0 AND COUNTIF(run_id=@run_id)=COUNT(*) "
                       f"FROM `{self.table(name)}`) AS 'Mixed raw snapshot';", run_id=self.run_id)
        return rows[0]

    def provision(self):
        """Operator-only setup, never called by scheduled ingestion."""
        schemas = {
            "player_fixture_history": HISTORY_SCHEMA,
            "player_history_checks": [bigquery.SchemaField(n, t) for n, t in (
                ("season", "STRING"), ("player_id", "INT64"), ("team_id", "INT64"),
                ("checked_at", "TIMESTAMP"), ("full_checked_at", "TIMESTAMP"),
                ("daily_checked_at", "TIMESTAMP"), ("run_id", "STRING"))],
            "pipeline_runs": [bigquery.SchemaField(n, t) for n, t in (
                ("run_id", "STRING"), ("season", "STRING"), ("checked_at", "TIMESTAMP"),
                ("content_hash", "STRING"), ("selected_players", "INT64"), ("history_rows", "INT64"),
                ("changed_history", "INT64"), ("needs_build", "BOOL"), ("ingestion_complete", "BOOL"),
                ("fixtures_json", "STRING"), ("published_at", "TIMESTAMP"), ("build_execution", "STRING"))],
            "refresh_control": [bigquery.SchemaField(n, t) for n, t in (
                ("lock_id", "STRING"), ("owner", "STRING"), ("acquired_at", "TIMESTAMP"),
                ("ingestion_execution", "STRING"))],
        }
        for name, schema in schemas.items():
            table = self.client.create_table(bigquery.Table(self.table(name), schema=schema), exists_ok=True)
            table.expires = None
            self.client.update_table(table, ["expires"])
        self.query(f"""MERGE `{self.table('refresh_control')}` t USING (SELECT 'refresh' AS lock_id) s
            ON t.lock_id=s.lock_id WHEN NOT MATCHED THEN INSERT (lock_id) VALUES(s.lock_id)""")
