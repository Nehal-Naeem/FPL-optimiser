{{ config(severity='warn') }}
SELECT h.player_id FROM {{ ref('stg_player_fixture_history') }} h
LEFT JOIN {{ ref('stg_players') }} p ON p.id=h.player_id
WHERE p.id IS NULL OR h.expected_goals IS NULL OR h.expected_assists IS NULL OR h.total_points>30
UNION ALL
SELECT player_id FROM {{ source('fpl_raw','player_history_checks') }}
WHERE season={{ tojson(var('fpl_season',env_var('FPL_SEASON','2026-27'))) }}
 AND checked_at<TIMESTAMP_SUB(CURRENT_TIMESTAMP(),INTERVAL 8 DAY)
UNION ALL
SELECT player_id FROM {{ ref('int_player_recent_form') }} WHERE NOT complete
UNION ALL
SELECT h.player_id FROM {{ ref('stg_player_fixture_history') }} h
JOIN {{ ref('stg_fixtures') }} f ON f.id=h.fixture_id
WHERE h.gameweek IS DISTINCT FROM f.event
