# Points-only migration — November 14, 2026

Public app: https://fpl-web-381011398272.us-central1.run.app

## Change and evidence

Feature commit: `646108d`; optional-analysis deployment safeguard: `5b31455`.
The feature branch is `feat/points-only-recommendations`.

The app removes the retired ranking objective, eligibility/percentile displays and
all score tie-breaks. Replacements, transfers and ideal squads use the shared
five-week XI/captain objective. Cheaper and bank-funded upgrades are considered;
savings swaps must preserve every weekly primary total and reliable single/double
coverage count. Owned unavailable players use labelled zero-minute assumptions
unless explicitly overridden. Forecast method `experimental-points-v1` and its
stored component coefficients are unchanged.

Validation before production migration:

- 47 backend tests plus 42 ingestion/SQL/evaluation tests pass.
- 29 desktop/mobile browser tests pass; one mouse-hover test skipped on mobile.
- TypeScript/Vite build, shell syntax and diff/link checks pass.
- Isolated native dbt run `6365f4a3-ca10-491c-a8f1-946663258a85`: 16 models and 111
  test resources, **PASS=127 WARN=0 ERROR=0 SKIP=0**, plus source freshness.
- Candidate Cloud Run API smoke tests passed against the original production
  snapshot before changing its schema, including imported unavailable players,
  zero-transfer baselines, budgets, legal XIs, captaincy and obsolete-contract 409s.
- Replacement analysis on the 1-CPU service took about 5.35 seconds for the real
  imported squad. No candidate shortlist is applied before evaluating eligibility
  and projected squad impact; each response group is limited to five results.
- Tagged candidate desktop/mobile UI passed with no retired metric in page text,
  no overflow and no JavaScript errors.

Web image `fpl-web:points-v2-646108d`; build
`63c0558a-5446-4df2-9861-5affca604bbf`; revision `fpl-web-00002-dam`.
The candidate was deployed without main traffic and tested before traffic promotion.
The preview tag inherits service-level public IAM; no temporary private service
or other infrastructure was created.

dbt image `fpl-dbt-build:20261114010227`; build
`b6777777-4ce0-40f6-a4ed-36546ffa2337`. Scheduling was paused before updating it.
The contract marker forces a rebuild when migrating an old publication, even if
API payloads have not changed. Active publication now archives only fixture/GW
projection marts and the serving snapshot; it does not update the compatibility
ranking mart. Existing legacy warehouse objects and historical archives remain.

## Contract and recovery

The API requires `contract_version: 2` on POST requests and prefixes dataset tokens
with `points-v2:`. Obsolete/missing contracts receive HTTP 409 instructing a page
reload. New snapshots use `projections_updated_at` and contain no retired score
fields. The new reader temporarily accepts `scores_updated_at` from older serving
snapshots, but exposes only the new API fields. This allowed API/UI promotion
before the data schema migration without taking the public app offline.

Recovery references are in the git-ignored directory
`logs/local-refresh/points-only-20261114T004942Z/`. It records the original web/job/
workflow/scheduler configuration and the confirmed existing immutable rollback
archive `mart_recommendation_snapshot_716617bf_2370_41a6_8c43_6b400c0afda4`.

To roll back, pause scheduling and verify idle jobs; restore that old-contract
archive to the serving table before routing back to `fpl-web-00001-mgd`. Restore
the prior dbt job image/configuration as a pair. Do not route the old API to a
points-only snapshot lacking its expected fields. No historical data was deleted.

## Production migration checks

Workflow `29e63137-672e-496e-8409-78c137d95fa6` succeeded. Cloud Run dbt execution
`fpl-dbt-build-xqkpx` reported **PASS=127 WARN=0 ERROR=0 SKIP=0** (16 models,
109 data tests and two unit tests). Publication checks confirmed 672 unique players,
all with contract 2 and complete recent history, and five projection gameweeks
(11–15). The serving schema has the new projection timestamp and no retired score
columns. The singleton refresh lock was released.

Public API checks passed after schema migration: real public-team import,
replacements, ideal squad, zero-transfer replay, owned-unavailable retention,
club/position/budget constraints, weekly XIs/captains and old-contract/version 409s.
Replacement analysis took about 4.21 seconds. The sampled time-limited ideal result
was `FEASIBLE`, correctly labelled without a claim of proven optimality.

Visual review identified an existing mobile grid intrinsic-size issue that could
clip the planner while the page-width check still passed. Commit `aa1f097` sets
panel minimum widths to zero and adds panel-boundary assertions to the existing
planner test. Both desktop/mobile regressions and the production build passed.
The wider rotation table remains deliberately horizontally scrollable.

A Scheduler-triggered check does not claim observation of a later cron tick.


## Final deployment and scheduling

Final web image `fpl-web:points-v2-aa1f097`; build
`ebb33a77-6805-4bbb-bf8e-4e3ebbaefa5c`; revision `fpl-web-00004-wej`.
The runtime build context was from commit `aa1f097`; the only untracked file was
this deployment record, which the allowlisted build context excludes. Desktop and
mobile checks passed against the actual tagged revision without injected styles,
including planner panel boundaries, 11 starters, 15 rotation rows, popover data,
no retired metric text, no page overflow and no JavaScript errors.

Scheduler `FPL-bigquery-ingestion` is enabled with unchanged cron `0 */6 * * *`
and timezone `America/Vancouver`. Its controlled validation execution
`16cf7c2b-5bfe-48bd-8dff-4e338d7f985f` succeeded from 01:14:29 to 01:20:35 UTC.
Ingestion `fpl-bigquery-ingestion-b4zp5` preceded dbt `fpl-dbt-build-kx8bz`, which
also reported **PASS=127 WARN=0 ERROR=0 SKIP=0**. The refresh lock was released.
This verifies Scheduler authentication and the full dependency chain; the next
natural cron tick has not yet been observed.


After promotion, all public traffic routes to `fpl-web-00004-wej`. The complete
public API smoke passed again against publication
`points-v2:16cf7c2b-5bfe-48bd-8dff-4e338d7f985f`: 672 players and gameweeks 11–15,
with replacement analysis about 6.75 seconds (under the 10-second acceptance target).
The ideal result remained correctly labelled `FEASIBLE`. No local preview or API
servers remained listening on ports 8000, 8002 or 5174 after validation.
