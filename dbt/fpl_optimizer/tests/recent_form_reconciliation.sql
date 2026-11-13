WITH expected AS (
 SELECT r.season,r.player_id,r.cutoff_gameweek,COUNT(*) AS n,LOGICAL_AND(g.covered) AS complete,
        SUM(g.points) AS points,SUM(g.minutes) AS minutes,SUM(g.starts) AS starts
 FROM {{ ref('int_player_recent_form') }} r
 JOIN {{ ref('int_player_gameweek_history') }} g USING(season,player_id)
 WHERE g.gameweek BETWEEN r.window_start_gameweek AND r.cutoff_gameweek GROUP BY 1,2,3
)
SELECT r.player_id FROM {{ ref('int_player_recent_form') }} r JOIN expected e USING(season,player_id,cutoff_gameweek)
WHERE r.window_gameweeks!=e.n OR r.complete!=e.complete
 OR (r.complete AND (r.points!=e.points OR r.minutes!=e.minutes OR r.starts!=e.starts))
 OR (NOT r.complete AND (r.points IS NOT NULL OR r.minutes IS NOT NULL))
 OR r.window_start_gameweek>r.cutoff_gameweek
 OR (r.minutes=0 AND (r.points_per_90 IS NOT NULL OR r.xg_per_90 IS NOT NULL OR r.xa_per_90 IS NOT NULL))
