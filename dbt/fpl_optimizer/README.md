# FPL BigQuery models

The production ranking remains `mart_player_eval`: season minutes >60, within-position
`CUME_DIST` for API form and season points/completed-GW, and weighted next-five-match
ease, with weights 0.30/0.45/0.25. New recent features join **after** percentile and
score computation. They do not alter eligibility, ranks or the CP-SAT objective.

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
`ingested_at` and `scores_updated_at` are collection/calculation times, not proof
that a recommendation was available to users. Evaluate outcomes after selection.

## Serving and shadow comparisons

`int_upcoming_team_fixtures` matches the backend display rule: exclude started or
finished, dated first, kickoff then fixture ID, five per team. The legacy scoring
selector remains unchanged. The serving snapshot exposes both fixture sets so a
live/undated discrepancy is explained rather than silently changing rankings.

`mart_score_comparison` includes baseline and separate heuristic experiments:
recent points/GW percentile in place of API form, that score times a capped
recent-minutes factor, and the baseline with aligned upcoming-fixture selection.
These are not calibrated expected points, and none feeds the serving score.
Compare within-position rank deltas/top-K overlap, low-minutes selections, squad
spend and club exposure. The complete-history comparison cohort may differ from
the full baseline cohort; report its coverage. Future observed points must be
joined after the saved selection timestamp, with transfer/availability caveats.

`mart_recommendation_snapshot` contains **all catalog players**, nullable scores,
nested upcoming/scoring fixtures, recent features, season totals, component
contributions, prices, availability and one run/publication ID. The separate job
publishes it only after the entire candidate build and critical checks pass.

## Quality policy and local validation

Errors block publication: required IDs, source/composite uniqueness, current
references, raw-run coherence, required casts/ranges, scaffold grain, rolling
reconciliation, mapping, eligibility, percentiles, score formula and serving
coverage. Negative FPL points and double-GW minutes above 90 are valid.

Warnings allow publication: optional attacking data, historical players absent
from today's catalog, season-history discrepancies during settling/corrections,
old checks, incomplete recent context, and plausible statistical/price outliers.
No-future-fixture scores may be null. Fewer than five remaining matches is valid.
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


## Optional points projection layer

The serving snapshot now nests `mart_player_gameweek_projection` and its fixture
components. `int_projection_horizon`, `int_player_projection_rates`, and
`int_team_projection_strength` feed the separate `mart_player_fixture_projection`.
The viability formula remains unchanged. Both projection marts are archived with
each validated publication for prospective evaluation. See the versioned
[methodology and evaluation guide](../../docs/POINTS_PLANNER.md).
