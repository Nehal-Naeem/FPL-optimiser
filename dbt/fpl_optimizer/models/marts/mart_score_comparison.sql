{{ config(materialized='table') }}
WITH latest AS (
    SELECT * FROM {{ ref('int_player_recent_form') }}
    QUALIFY cutoff_gameweek = MAX(cutoff_gameweek) OVER ()
), aligned_ordered AS (
    SELECT *, ROW_NUMBER() OVER(PARTITION BY team_id ORDER BY kickoff_time IS NULL,kickoff_time,id) AS n
    FROM {{ ref('int_upcoming_team_fixtures') }}
), aligned AS (
    SELECT team_id, (SAFE_DIVIDE(SUM((6-difficulty)*(6-n)),SUM(6-n))-1)/4 AS aligned_fixture_ease
    FROM aligned_ordered GROUP BY team_id
), ranked AS (
    SELECT e.*, r.window_gameweeks, r.cutoff_gameweek, a.aligned_fixture_ease,
        CUME_DIST() OVER (PARTITION BY e.element_type ORDER BY r.points_per_gw) AS recent_percentile
    FROM {{ ref('mart_player_eval') }} e JOIN latest r ON e.id=r.player_id
    LEFT JOIN aligned a ON e.team=a.team_id
    WHERE r.complete
), shadow AS (
    SELECT *, 0.30*recent_percentile+0.45*normalized_n5fs+0.25*points_per_gw_percentile AS shadow_recent_score
    FROM ranked
)
SELECT *, shadow_recent_score*LEAST(1,SAFE_DIVIDE(recent_minutes,60*window_gameweeks)) AS shadow_minutes_score,
    0.30*form_percentile+0.45*aligned_fixture_ease+0.25*points_per_gw_percentile AS shadow_aligned_fixture_score,
    'retrospective_corrected_history' AS evaluation_basis
FROM shadow
