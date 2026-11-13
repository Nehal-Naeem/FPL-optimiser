WITH expected AS (
    SELECT team_id,TO_JSON_STRING(ARRAY_AGG(id ORDER BY kickoff_time IS NULL,kickoff_time,id)) AS fixture_ids
    FROM {{ ref('int_upcoming_team_fixtures') }} GROUP BY team_id
)
SELECT 'catalog_count' AS problem FROM (SELECT 1 AS anchor) WHERE
 (SELECT COUNT(*) FROM {{ ref('mart_recommendation_snapshot') }}) != (SELECT COUNT(*) FROM {{ ref('stg_players') }})
UNION ALL
SELECT 'fixture_list' FROM {{ ref('mart_recommendation_snapshot') }} s
LEFT JOIN expected f ON f.team_id=s.team_id
WHERE ARRAY_LENGTH(upcoming_fixtures)>5 OR
 ARRAY_LENGTH(upcoming_fixtures)!=(SELECT COUNT(DISTINCT fixture.id) FROM UNNEST(s.upcoming_fixtures) fixture)
 OR TO_JSON_STRING(ARRAY(SELECT fixture.id FROM UNNEST(s.upcoming_fixtures) fixture)) != COALESCE(f.fixture_ids,'[]')
UNION ALL
SELECT 'null_score_with_coverage' FROM {{ ref('mart_recommendation_snapshot') }} s
LEFT JOIN {{ ref('mart_player_eval') }} e ON e.id=s.id
WHERE s.score IS NULL AND e.viability_score IS NOT NULL
