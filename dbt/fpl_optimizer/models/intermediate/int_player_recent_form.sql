-- Completed-GW cutoffs only. Latest API corrections make past cutoffs retrospective, not point-in-time.
WITH cutoffs AS (
    SELECT id AS cutoff_gameweek FROM {{ ref('stg_gameweeks') }} WHERE finished AND data_checked
), windows AS (
    SELECT h.*, c.cutoff_gameweek,
        ROW_NUMBER() OVER (PARTITION BY h.season, h.player_id, c.cutoff_gameweek ORDER BY h.gameweek DESC) AS recency
    FROM {{ ref('int_player_gameweek_history') }} h JOIN cutoffs c ON h.gameweek <= c.cutoff_gameweek
), totals AS (
    SELECT season, player_id, cutoff_gameweek,
        COUNT(*) AS window_gameweeks, MIN(gameweek) AS window_start_gameweek,
        COUNTIF(covered) AS covered_gameweeks, LOGICAL_AND(covered) AS complete,
        MIN(checked_at) AS history_checked_at,
        IF(LOGICAL_AND(covered), SUM(points), NULL) AS points,
        IF(LOGICAL_AND(covered), SUM(minutes), NULL) AS minutes,
        IF(LOGICAL_AND(covered), SUM(starts), NULL) AS starts,
        IF(LOGICAL_AND(covered) AND COUNTIF(xg IS NULL)=0, SUM(xg), NULL) AS xg,
        IF(LOGICAL_AND(covered) AND COUNTIF(xa IS NULL)=0, SUM(xa), NULL) AS xa,
        COUNTIF(recency<=3) AS short_window_gameweeks,
        IF(COUNTIF(recency<=3 AND NOT covered)=0, SUM(IF(recency<=3, points, 0)), NULL) AS short_points,
        IF(COUNTIF(recency<=3 AND NOT covered)=0, SUM(IF(recency<=3, minutes, 0)), NULL) AS short_minutes
    FROM windows WHERE recency<=5 GROUP BY 1,2,3
)
SELECT *, SAFE_DIVIDE(points,window_gameweeks) AS points_per_gw,
    SAFE_DIVIDE(minutes,window_gameweeks) AS minutes_per_gw,
    SAFE_DIVIDE(90*points,minutes) AS points_per_90,
    SAFE_DIVIDE(90*xg,minutes) AS xg_per_90,
    SAFE_DIVIDE(90*xa,minutes) AS xa_per_90,
    SAFE_DIVIDE(short_points,short_window_gameweeks) AS short_points_per_gw,
    SAFE_DIVIDE(short_minutes,short_window_gameweeks) AS short_minutes_per_gw
FROM totals
