# FPL BigQuery models

The active graph produces fixture/gameweek points projections and a versioned,
all-player serving snapshot. Retired ranking/comparison models are no longer built,
tested, archived or published. Existing historical warehouse objects remain for
rollback and are not queried by the application.

## History and grains

- `stg_player_fixture_history`: current-season `(season,player_id,fixture_id)`, explicit
  safe casts and deterministic latest-observation deduplication. Raw uniqueness is
  tested separately so deduplication cannot hide ingestion defects.
- `int_player_gameweek_history`: `(season,player_id,gameweek)` scaffold for all current
  catalog players and gameweeks both finished and data-checked. Fixture rows join
  the captured fixture catalog's event/finished state; this handles rescheduling.
  Multiple fixtures are aggregated before windowing. Blanks and nonappearances
  contribute zero only with a successful sufficiently recent player-history check.
- `int_player_recent_form`: `(season,player_id,cutoff_gameweek)`, last five and three
  completed GWs. Early-season denominators use the actual available GW count;
  missing appearances never shorten that denominator. Features include total/rate
  points/minutes/starts, points/90 and xG/xA per 90, with null rates at zero minutes.

Absent records cannot prove a historical club assignment. `gameweek_context`
separates appeared, missed-appearance, multiple-fixture, incomplete, and
`no_record_membership_unknown`. A no-record gameweek may be a blank, an absence, or
pre-registration; **do not label it a confirmed club blank using today's team**.
This deliberately preserves uncertainty instead of inventing membership. All
these gameweeks still count in the completed-GW denominator. Optional unknown
xG/xA stay null, including when just one constituent fixture is missing them.

Coverage requires a successful check and a conservative two-hour post-kickoff
bound for completed fixtures involving the current club. The API supplies no
historic registration calendar or finalisation timestamp per player fixture;
coverage is an explainable collection indicator, not certainty that FPL will
never issue corrections. Daily checks and weekly full sweeps reconcile those.

Past cutoffs are **retrospective with latest corrections**. They do not reconstruct
historic API form/availability or the information visible at old deadlines.
Versioned candidate archives support forward evaluation only after joining their
`publication_id` to a successful `pipeline_runs.run_id` and its non-null
`published_at`. Archives written before a failed publication must be excluded.
Use that publication completion timestamp as the information-availability bound;
`ingested_at` and `projections_updated_at` are collection/calculation times, not proof
that a recommendation was available to users. Evaluate outcomes after selection.

## Serving contract 2

`int_upcoming_team_fixtures` excludes started/finished fixtures and selects the next
five per team, dated first. This display list is distinct from the five actionable
GW deadlines used for points planning.

`mart_recommendation_snapshot` contains all catalog players, nested projections and
components, recent measurements, prices, availability, `contract_version=2`,
`projections_updated_at` and one publication UUID. It has no legacy score fields.
The publisher archives the two projection marts and the serving snapshot, preserves
`_previous`, then atomically replaces the single serving boundary.

## Quality policy and local validation

Errors block publication: required IDs, source/composite uniqueness, current
references, raw-run coherence, required casts/ranges, scaffold grain, rolling
reconciliation, mapping, projection components/probabilities and serving
coverage. Negative FPL points and double-GW minutes above 90 are valid.

Warnings allow publication: optional attacking data, historical players absent
from today's catalog, season-history discrepancies during settling/corrections,
old checks, incomplete recent context, and plausible statistical/price outliers.
Fewer than five actionable GWs is valid; assigned blanks have zero projected points.
Raw source freshness warns at 8 hours and errors at 24; history age uses successful
checks rather than the time a canonical metric last changed.

```sh
# Use a Python 3.12 environment and deploy/dbt-build/requirements.txt.
DBT_SEND_ANONYMOUS_USAGE_STATS=false dbt parse --project-dir dbt/fpl_optimizer \
  --profiles-dir deploy/dbt-build --no-partial-parse
# Offline regression tools only; not production dependencies:
python -m pip install -r tests/dbt/requirements.txt
python -m pytest tests/dbt -q
```

The offline tests execute the actual model SQL, translated to DuckDB. They cover
full candidate joins and nested fixture lists as well as edge cases. dbt-native
unit tests also run in the Cloud Run dbt build. BigQuery adapter execution and failure
injection in isolated datasets remain required before activating production.
See [rollout](../../deploy/fpl-refresh/README.md) for exact sequencing and IAM.

For native validation after a successful **isolated** ingestion, select its real
manifest ID (not the `local-validation` parse default):

```sh
export GOOGLE_CLOUD_PROJECT=fpl-optimizer-511321
export FPL_RAW_DATASET=fpl_raw_validation
export DBT_DATASET=fpl_build_validation
export FPL_RUN_ID=REPLACE_WITH_COMPLETE_VALIDATION_RUN_UUID
export FPL_SEASON=2026-27
export BIGQUERY_LOCATION=US
dbt source freshness --project-dir dbt/fpl_optimizer --profiles-dir deploy/dbt-build
dbt build --project-dir dbt/fpl_optimizer --profiles-dir deploy/dbt-build \
  --exclude resource_type:seed
```

This builds isolated candidates; it does not publish. Production builds and
publication must use the workflow so they share its lock and stage claims.


## Points projection layer

`int_projection_horizon`, `int_player_projection_rates` and
`int_team_projection_strength` feed `mart_player_fixture_projection`, which is
summed/scaffolded into `mart_player_gameweek_projection`. Both projection marts are
archived for prospective evaluation. See the versioned
[methodology and evaluation guide](../../docs/POINTS_PLANNER.md).
