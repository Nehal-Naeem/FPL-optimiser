-- Versioned empirical Bayes-style smoothing, no fitted ML. Recent five completed GWs have weight 2, older GWs 1.
WITH completed AS (
    SELECT id, ROW_NUMBER() OVER(ORDER BY id DESC) AS recency
    FROM {{ ref('stg_gameweeks') }} WHERE finished AND data_checked
), observations AS (
    SELECT h.*,p.element_type,p.minutes AS season_minutes,IF(g.recency<=5,2.0,1.0) AS w,
        IF(p.element_type=2,IF(h.defensive_contribution>=10,2.0,0.0),
           IF(p.element_type IN (3,4),IF(h.defensive_contribution>=12,2.0,0.0),0.0)) AS defensive_points,
        FLOOR(h.saves/3.0) AS save_points,
        h.yellow_cards+3*h.red_cards+2*h.own_goals+2*h.penalties_missed AS deduction_points
    FROM {{ ref('stg_player_fixture_history') }} h
    JOIN {{ ref('stg_players') }} p ON p.id=h.player_id
    JOIN {{ ref('stg_fixtures') }} f ON f.id=h.fixture_id
    JOIN completed g ON g.id=f.event WHERE f.finished
), priors AS (
    SELECT element_type,
        SAFE_DIVIDE(SUM(IF(minutes>0,w,0)),SUM(w)) AS play_prior,
        SAFE_DIVIDE(SUM(IF(minutes>=60,w,0)),SUM(w)) AS sixty_prior,
        SAFE_DIVIDE(SUM(expected_goals*w),SUM(IF(expected_goals IS NOT NULL,minutes*w,0))) AS xg_prior,
        SAFE_DIVIDE(SUM(expected_assists*w),SUM(IF(expected_assists IS NOT NULL,minutes*w,0))) AS xa_prior,
        SAFE_DIVIDE(SUM(save_points*w),SUM(IF(save_points IS NOT NULL,minutes*w,0))) AS saves_prior,
        SAFE_DIVIDE(SUM(defensive_points*w),SUM(IF(defensive_contribution IS NOT NULL,minutes*w,0))) AS defensive_prior,
        SAFE_DIVIDE(SUM(bonus*w),SUM(IF(bonus IS NOT NULL,minutes*w,0))) AS bonus_prior,
        SAFE_DIVIDE(SUM(deduction_points*w),SUM(IF(deduction_points IS NOT NULL,minutes*w,0))) AS deductions_prior,
        SAFE_DIVIDE(SUM(5*penalties_saved*w),SUM(IF(penalties_saved IS NOT NULL,minutes*w,0))) AS penalties_prior
    FROM observations WHERE season_minutes>60 GROUP BY element_type
), totals AS (
    SELECT player_id, COUNT(*) AS history_fixtures, SUM(minutes) AS history_minutes,
        SUM(w) AS exposure, SUM(IF(minutes>0,w,0)) AS played, SUM(IF(minutes>=60,w,0)) AS sixty,
        SAFE_DIVIDE(SUM(IF(minutes>=60,minutes*w,0)),SUM(IF(minutes>=60,w,0))) AS long_minutes,
        SAFE_DIVIDE(SUM(IF(minutes BETWEEN 1 AND 59,minutes*w,0)),SUM(IF(minutes BETWEEN 1 AND 59,w,0))) AS short_minutes,
        SUM(expected_goals*w) AS xg, SUM(IF(expected_goals IS NOT NULL,minutes*w,0)) AS xg_minutes,
        SUM(expected_assists*w) AS xa, SUM(IF(expected_assists IS NOT NULL,minutes*w,0)) AS xa_minutes,
        SUM(save_points*w) AS saves, SUM(IF(save_points IS NOT NULL,minutes*w,0)) AS saves_minutes,
        SUM(defensive_points*w) AS defensive, SUM(IF(defensive_contribution IS NOT NULL,minutes*w,0)) AS defensive_minutes,
        SUM(bonus*w) AS bonus, SUM(IF(bonus IS NOT NULL,minutes*w,0)) AS bonus_minutes,
        SUM(deduction_points*w) AS deductions, SUM(IF(deduction_points IS NOT NULL,minutes*w,0)) AS deductions_minutes,
        SUM(5*penalties_saved*w) AS penalties, SUM(IF(penalties_saved IS NOT NULL,minutes*w,0)) AS penalties_minutes
    FROM observations GROUP BY player_id
)
SELECT p.id AS player_id,COALESCE(t.history_fixtures,0) AS history_fixtures,
    COALESCE(t.history_minutes,0) AS history_minutes,
    IF(t.history_fixtures IS NULL,0.0,SAFE_DIVIDE(t.played+2*COALESCE(pr.play_prior,0),t.exposure+2)) AS p_play,
    IF(t.history_fixtures IS NULL,0.0,SAFE_DIVIDE(t.sixty+2*COALESCE(pr.sixty_prior,0),t.exposure+2)) AS p_60,
    COALESCE(t.long_minutes,90.0) AS long_minutes,COALESCE(t.short_minutes,20.0) AS short_minutes,
    SAFE_DIVIDE(COALESCE(t.xg,0)+360*COALESCE(pr.xg_prior,0),COALESCE(t.xg_minutes,0)+360) AS xg_per_minute,
    SAFE_DIVIDE(COALESCE(t.xa,0)+360*COALESCE(pr.xa_prior,0),COALESCE(t.xa_minutes,0)+360) AS xa_per_minute,
    SAFE_DIVIDE(COALESCE(t.saves,0)+360*COALESCE(pr.saves_prior,0),COALESCE(t.saves_minutes,0)+360) AS saves_per_minute,
    SAFE_DIVIDE(COALESCE(t.defensive,0)+360*COALESCE(pr.defensive_prior,0),COALESCE(t.defensive_minutes,0)+360) AS defensive_per_minute,
    SAFE_DIVIDE(COALESCE(t.bonus,0)+360*COALESCE(pr.bonus_prior,0),COALESCE(t.bonus_minutes,0)+360) AS bonus_per_minute,
    SAFE_DIVIDE(COALESCE(t.deductions,0)+360*COALESCE(pr.deductions_prior,0),COALESCE(t.deductions_minutes,0)+360) AS deductions_per_minute,
    SAFE_DIVIDE(COALESCE(t.penalties,0)+360*COALESCE(pr.penalties_prior,0),COALESCE(t.penalties_minutes,0)+360) AS penalties_per_minute,
    CASE WHEN COALESCE(t.history_minutes,0)=0 THEN 'no_playing_minutes'
         WHEN t.history_minutes<360 THEN 'limited_minutes'
         WHEN COALESCE(t.xg_minutes,0)=0 OR COALESCE(t.xa_minutes,0)=0 THEN 'missing_attacking_data'
         ELSE 'observed_history' END AS data_support
FROM {{ ref('stg_players') }} p LEFT JOIN totals t ON t.player_id=p.id
LEFT JOIN priors pr ON pr.element_type=p.element_type
