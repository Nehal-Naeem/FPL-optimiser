{{ config(severity='warn') }}
SELECT p.id FROM {{ ref('stg_players') }} p
LEFT JOIN (SELECT player_id,SUM(minutes) AS history_minutes,SUM(total_points) AS history_points
           FROM {{ ref('stg_player_fixture_history') }} GROUP BY player_id) h ON p.id=h.player_id
WHERE ABS(p.minutes-COALESCE(h.history_minutes,0))>0 OR ABS(p.total_points-COALESCE(h.history_points,0))>0
   OR p.now_cost NOT BETWEEN 10 AND 200
