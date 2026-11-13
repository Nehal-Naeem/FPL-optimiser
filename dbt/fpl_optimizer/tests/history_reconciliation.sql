SELECT 'raw_staging_keys' AS problem
FROM (SELECT 1 AS anchor)
WHERE (SELECT COUNT(*) FROM {{ source('fpl_raw','player_fixture_history') }}
       WHERE season={{ tojson(var('fpl_season',env_var('FPL_SEASON','2026-27'))) }})
    != (SELECT COUNT(*) FROM {{ ref('stg_player_fixture_history') }})
UNION ALL
SELECT 'invalid_opponent' FROM {{ ref('stg_player_fixture_history') }} h
JOIN {{ ref('stg_fixtures') }} f ON f.id=h.fixture_id
WHERE h.opponent_team != IF(h.was_home,f.team_a,f.team_h)
UNION ALL
SELECT 'missing_player_check' FROM {{ ref('stg_players') }} p
LEFT JOIN {{ source('fpl_raw','player_history_checks') }} c ON c.player_id=p.id
AND c.season={{ tojson(var('fpl_season',env_var('FPL_SEASON','2026-27'))) }}
WHERE c.checked_at IS NULL
