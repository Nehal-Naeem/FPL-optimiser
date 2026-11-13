WITH history AS (
 SELECT h.player_id,f.event AS gameweek,SUM(h.minutes) AS minutes,SUM(h.total_points) AS points,
        SUM(h.starts) AS starts, COUNT(*) AS fixtures
 FROM {{ ref('stg_player_fixture_history') }} h JOIN {{ ref('stg_fixtures') }} f ON f.id=h.fixture_id
 WHERE f.finished GROUP BY 1,2
)
SELECT 'wrong_scaffold_count' AS problem FROM (SELECT 1 AS anchor) WHERE
 (SELECT COUNT(*) FROM {{ ref('int_player_gameweek_history') }}) !=
 (SELECT COUNT(*) FROM {{ ref('stg_players') }}) *
 (SELECT COUNT(*) FROM {{ ref('stg_gameweeks') }} WHERE finished AND data_checked)
UNION ALL
SELECT 'aggregate_mismatch' FROM {{ ref('int_player_gameweek_history') }} g
LEFT JOIN history h USING(player_id,gameweek)
WHERE g.covered AND (g.minutes!=COALESCE(h.minutes,0) OR g.points!=COALESCE(h.points,0)
 OR g.starts!=COALESCE(h.starts,0) OR g.fixture_count!=COALESCE(h.fixtures,0))
