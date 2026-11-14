# Five-gameweek points planner

`experimental-points-v1` is the explainable projection layer used by all recommendation features.
The backend reads a validated serving snapshot exclusively. API contract 2 is
separate from the forecasting method version; the forecast coefficients are unchanged.

## Models and assumptions

- `int_projection_horizon`: next five deadlines strictly after the ingestion
  manifest's `checked_at`, fewer near season end. A passed first deadline blocks
  planning until refresh. Publication rebuilds on horizon expiry even if payloads
  have not changed.
- `int_player_projection_rates`: finished, data-checked fixture history. Last five
  completed GWs receive weight 2, older GWs weight 1. Recorded zero-minute fixtures
  count as non-appearances. Two equivalent positional-prior matches smooth
  appearance/60-minute likelihoods; 360 positional-prior minutes smooth component
  rates. Priors use players with season minutes >60. Long/short conditional minutes
  use observed means, falling back to 90/20. No-history appearance likelihood is zero;
  new purchases without observed minutes need explicit minutes assumptions.
- `int_team_projection_strength`: five-match shrinkage of each team's scoring and
  conceding towards league averages. Venue league averages adjust attacking rates
  and opponent-goal intensity. Attacking factor is bounded 0.5–1.5. No ordinal FDR
  values are converted into probabilities.
- `mart_player_fixture_projection`: expected minutes from appearance and 60-minute
  likelihoods; appearance points `P(play)+P(60)`. Goals and assists use smoothed
  xG/xA rates, minutes and opponent/venue adjustment. Goal values are 10/6/5/4 for
  GK/DEF/MID/FWD. Clean sheets use a Poisson no-goal estimate over conditional long
  minutes. Save-point, penalty-save-point, bonus and deduction rates are empirical.
  Defensive contribution uses observed award thresholds (10 actions DEF, 12 MID/FWD)
  to derive a smoothed awarded-points rate, capped at 2 × appearance likelihood.
  Bonus is capped at 3 × appearance likelihood. GK/DEF goals-conceded deductions use
  the Poisson expectation of `floor(goals / 2)`. This is a simple approximation,
  especially for correlated bonus, red cards and clean sheets.
- `mart_player_gameweek_projection`: player × deadline scaffold. Double fixtures
  sum, assigned blanks are zero, unassigned fixtures are flagged and excluded.
  Across a double GW the greatest fixture appearance likelihood is used for cover
  (a conservative dependence assumption). It is not an independence calculation.

Next-round FPL availability percentages apply only to the first actionable GW.
Later-week fitness is unconfirmed. Players currently marked injured, suspended,
unavailable or 0% are excluded from selection unless users explicitly assume
minutes for every assigned week. Owned unavailable players may remain, with zero assumed minutes in weeks without
explicit overrides. The conservative assumption is labelled and used in both baseline
and candidate plans; no forced sale is required. No recovery dates are invented.
Doubtful players retain flags and the first-week adjustment.

Manual minutes assumptions are deterministic 0–90 **per fixture**, not confidence
levels. 59/60 changes appearance and clean-sheet eligibility. Components recalculate
from the published rate inputs; a blank stays zero and a double applies minutes to
each fixture. Overrides affect the request only; cached/published data stay unchanged.

## Optimisation and cover

The objective is the sum of five weekly legal starting XIs plus one captain bonus
per week. Bench projections and vice-captain fallback do not inflate the headline.
Legal formation has 1 GK, at least 3 DEF, 2 MID, 1 FWD. Squad quotas, budget and club
limits are the existing rules. Future transfers and chips are not planned.

Sequential objectives preserve the best primary integer objective (points rounded
to 0.001), then maximise a formation-aware reserve appearance proxy, then fewer immediate moves/lower expenditure. There is one total 10-second solver
budget. Secondary objectives run only after primary optimality is proved; incomplete
tie-breaks are disclosed. A feasible result does not claim proven optimality.

Weekly bench order uses single-absence projected cover loss, then projected points.
The planner enumerates formation-legal substitutions in bench priority, including
separate GK replacement, without reusing reserves. It reports all 11 single and 55
double absence scenarios. Only reserves with estimated appearance likelihood >=80%
qualify as reliable in these stress tests. The threshold is a heuristic, not calibrated
confidence. The displayed vice-captain is the next strongest starting option; fallback
points are excluded. Cover is secondary to XI points; there is no hard bench spend cap.
Weekly bench expenditure and players with no planned starts remain visible for review.

Current-squad gain and single-swap comparisons use the same projections, overrides,
legal-XI and captain method, including conservative zero-minute assumptions for owned
unavailable players. Savings swaps must preserve every weekly XI/captain total and
single/double cover count; points upgrades may have weekly losses, which are disclosed.

## Validation and forward evaluation

Native dbt generic/singular checks cover player/fixture and player/GW uniqueness,
probability ordering, finite component totals, minutes bounds, blanks/doubles,
scaffold coverage and nested snapshot consistency. Python checks enumerate small
squad/XI problems and test minutes thresholds, rotations, sale prices, transfer caps
and substitution formation. Browser checks cover desktop/mobile planning and replacements.

Each successful publication archives both projection marts and the serving snapshot
with the immutable run UUID. The snapshot's `as_of`, method and component inputs
retain what was known at publication. Do not backdate current forecasts and call
that backtesting: historical injury/fixture feeds were not archived then.

Once future gameweeks settle, run the read-only evaluator:

```sh
python scripts/evaluate_projections.py --run-id UUID \
  --raw-dataset fpl_raw_localtest --analytics-dataset fpl_analytics_localtest
```

Add `--dry-run` to validate SQL and estimate bytes. It uses actual `published_at`
before each deadline, only settled/data-checked GWs, matching fixture assignment and
complete fixture outcomes. It reports points MAE/RMSE, minutes MAE, appearance Brier
and a paired recent-points/GW baseline by position. Blanks, unsettled and incomplete
rows are counted separately. Outcomes are latest **corrected** observations, not a
historically frozen outcome feed. No prospective accuracy claim is available until
these weeks finish. Review positional/minutes errors before changing priors or claiming calibrated predictive accuracy. New coefficients/scoring rules require a new projection method ID.

Rules references: [points](https://www.premierleague.com/en/news/2174909),
[captain/substitution rules](https://www.premierleague.com/en/news/2174899),
[defensive contributions](https://www.premierleague.com/en/news/4361991/).

The UI flags captains with estimated 60-minute likelihood below 70% and weekly
benches above 30% of squad market value as review prompts. These thresholds are
heuristics and do not alter the objective. The existing five-minute repository
cache and one-snapshot query are reused. API gzip compresses the larger catalog;
no per-player cloud queries or new runtime dependencies were introduced.
