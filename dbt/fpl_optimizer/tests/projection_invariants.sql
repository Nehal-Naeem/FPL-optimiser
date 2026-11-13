WITH components AS (
    SELECT *,appearance_points+goal_points+assist_points+clean_sheet_points+save_points+
        penalty_save_points+defensive_points+bonus_points+deduction_points AS component_total
    FROM {{ ref('mart_player_fixture_projection') }}
), gw AS (
    SELECT player_id,gameweek,COUNT(*) AS n,SUM(expected_points) AS points,SUM(expected_minutes) AS minutes
    FROM components GROUP BY player_id,gameweek
)
SELECT 'fixture_component_or_probability' AS problem FROM components
WHERE expected_points IS NULL OR IS_NAN(expected_points) OR IS_INF(expected_points)
    OR ABS(expected_points-component_total)>1e-8 OR play_probability NOT BETWEEN 0 AND 1
    OR sixty_probability NOT BETWEEN 0 AND play_probability OR expected_minutes NOT BETWEEN 0 AND 90
    OR (position=1 AND defensive_points!=0) OR (position!=1 AND save_points!=0)
    OR defensive_points>2*play_probability+1e-8 OR bonus_points>3*play_probability+1e-8
UNION ALL
SELECT 'gameweek_reconciliation' FROM {{ ref('mart_player_gameweek_projection') }} p LEFT JOIN gw USING(player_id,gameweek)
WHERE p.fixture_count!=COALESCE(gw.n,0) OR ABS(p.expected_points-COALESCE(gw.points,0))>1e-8
 OR ABS(p.expected_minutes-COALESCE(gw.minutes,0))>1e-8
 OR (p.fixture_count=0 AND (p.expected_points!=0 OR p.play_probability!=0))
UNION ALL
SELECT 'scaffold_count' FROM (SELECT 1 AS anchor) WHERE
 (SELECT COUNT(*) FROM {{ ref('mart_player_gameweek_projection') }}) !=
 (SELECT COUNT(*) FROM {{ ref('stg_players') }})*(SELECT COUNT(*) FROM {{ ref('int_projection_horizon') }})
UNION ALL
SELECT 'past_deadline' FROM {{ ref('int_projection_horizon') }} WHERE deadline_time<=as_of
UNION ALL
SELECT 'snapshot_projection_count' FROM {{ ref('mart_recommendation_snapshot') }} p
WHERE ARRAY_LENGTH(p.projections)!=(SELECT COUNT(*) FROM {{ ref('int_projection_horizon') }})
