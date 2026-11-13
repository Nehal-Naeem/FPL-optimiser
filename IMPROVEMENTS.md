# Suggested tooling and infrastructure improvements

Recorded November 11, 2026. This is a proposed roadmap, not a record of completed
changes. Recommendations are based on repository inspection; live cloud health,
usage, and costs have not been verified.

Keep the existing Cloud Run, BigQuery, and dbt foundation. Prioritize reproducible
environments, data-quality checks, and reliable refreshes before adding services.

## First: reproducible development and automated validation

- [ ] Adopt `uv`, a `pyproject.toml`, and a committed lockfile. Define dependency
  groups for local analysis, ingestion, dbt, and development checks. Use locked
  installs in development, CI, and container builds.
- [ ] Move script execution behind functions and a `main()` entry point so tests
  can import code without making network requests or modifying databases.
- [ ] Add meaningful pytest tests using small, saved FPL API responses. Cover
  payload cleanup, source-to-table mapping, ingestion timestamps, failed requests,
  and failed BigQuery loads without accessing production services.
- [ ] Add GitHub Actions validation on pushes and pull requests:
  - Install dependencies in a clean environment from the lockfile.
  - Run Ruff and the Python tests.
  - Install dbt packages and parse the project to check configuration, model
    references, and Jinja syntax. Parsing alone does not validate BigQuery SQL
    execution or data correctness.
  - Build the ingestion Docker image to catch packaging failures before deployment.
- [ ] Stop tracking generated DuckDB databases and query logs going forward; add
  appropriate ignore rules for logs, dbt artifacts, and generated databases.
  Preserve existing local files and document how to recreate the database. Keep
  small, intentional test fixtures in Git.

GitHub Actions runs the checks; the tests and validation rules still need to be
implemented. Start with validation only and retain manual deployment initially.

## Next: data quality and one reliable refresh workflow

- [ ] Make BigQuery/dbt the primary evaluation pipeline to reduce duplicated
  scoring logic in `main.py` and dbt. Retain DuckDB for offline analysis, with
  exported results or shared fixtures to check consistency where both paths remain.
- [ ] Populate the empty dbt model schema YAML files with tests for unique,
  non-null identifiers, relationships, and score ranges. Test fixture identifiers
  at the correct grain, such as fixture ID plus team ID for team fixtures.
- [ ] Cover scoring edge cases: zero completed gameweeks, missing upcoming
  fixtures, missing player inputs, and zero cost. Define expected behavior before
  asserting results.
- [ ] Configure source freshness using `ingested_at`. Set thresholds to match the
  chosen refresh cadence and run freshness checks explicitly before building;
  `dbt build` does not include source freshness checks.
- [x] Add a separate `fpl-dbt-build` Cloud Run deployment bundle and an
  `fpl-refresh` Workflows definition that waits for ingestion success before
  building `+mart_player_eval`. Write transformed models to `fpl_analytics`.
  See [deployment and execution instructions](deploy/fpl-refresh/README.md).
- [ ] Add source freshness checks to the dbt job after defining thresholds.
- [x] Retarget the existing Cloud Scheduler job to `fpl-refresh`, preserving its
  six-hour cadence and `America/Vancouver` timezone. Use the dedicated
  `fpl-scheduler` identity and retain manual execution.
- [ ] Add protection against overlapping refreshes if concurrent triggers are
  needed. Until then, operators must avoid overlap; one task per execution does
  not prevent separate executions from overlapping.
- [ ] Add bounded retries for transient API failures and validate response
  structure before loading. Do not enable blanket whole-job retries without
  accounting for partial table refreshes.

The current ingestion replaces five tables independently. Sequential orchestration
does not make those replacements atomic. If mixed snapshots become a practical
problem, introduce staging tables and a validated publication step that ensures
downstream consumers read one consistent ingestion run.

## Operational visibility and access

- [ ] Emit structured logs containing a run ID, ingestion timestamp, per-table row
  counts, duration, and failures.
- [ ] Alert on failed executions and on the absence of a successful refresh within
  the expected interval. Track successful mart builds as well as raw ingestion.
- [ ] Narrow ingestion's BigQuery Data Editor grant to `fpl_raw`, retaining Job
  User at project level. Ensure the transformation identity has the required raw
  read access and output-dataset write access.
- [ ] Review actual execution duration, memory use, and BigQuery query usage before
  changing resource sizes or materializations. Retain full refreshes at the
  current data volume unless measurements show a reason to change.

## Later, when needed

- [ ] Add optional BigQuery integration checks using an isolated temporary dataset.
  Build models, run data tests, and clean up the dataset even on failure. Keep
  these checks separate from routine checks that need no cloud credentials.
- [ ] Consider automated deployment after validation is reliable. Use short-lived
  cloud authentication rather than committing service-account keys.
- [ ] Capture stable datasets, IAM, Cloud Run, scheduling, and alerting configuration
  in Terraform. The existing deployment script is adequate during early iteration.

Defer Kubernetes, Airflow/Composer, streaming ingestion, and elaborate incremental
models until workload or operational requirements justify their maintenance cost.

## References

- [uv locking and syncing](https://docs.astral.sh/uv/concepts/projects/sync/)
- [dbt data tests](https://docs.getdbt.com/docs/build/data-tests)
- [dbt source freshness](https://docs.getdbt.com/docs/deploy/source-freshness)
- [Scheduling Cloud Run jobs](https://docs.cloud.google.com/run/docs/execute/jobs-on-schedule)
- [BigQuery IAM roles and permissions](https://docs.cloud.google.com/bigquery/docs/access-control)
