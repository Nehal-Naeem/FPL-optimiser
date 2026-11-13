-- Scaffold includes nonappearances and blanks in denominators, but never fills missing collection with zero.
WITH completed AS (
    SELECT id AS gameweek FROM {{ ref('stg_gameweeks') }} WHERE finished AND data_checked
), history AS (
    SELECT h.season, h.player_id, f.event AS gameweek,
        COUNT(*) AS fixture_count, COUNTIF(h.minutes > 0) AS appearances,
        SUM(h.total_points) AS points, SUM(h.minutes) AS minutes, SUM(h.starts) AS starts,
        IF(COUNTIF(h.expected_goals IS NULL) = 0, SUM(h.expected_goals), NULL) AS xg,
        IF(COUNTIF(h.expected_assists IS NULL) = 0, SUM(h.expected_assists), NULL) AS xa,
        COUNT(DISTINCT IF(h.was_home, f.team_h, f.team_a)) AS clubs,
        ANY_VALUE(IF(h.was_home, f.team_h, f.team_a)) AS historical_team_id
    FROM {{ ref('stg_player_fixture_history') }} h
    JOIN {{ ref('stg_fixtures') }} f ON h.fixture_id = f.id
    WHERE f.finished
    GROUP BY 1, 2, 3
), scaffold AS (
    SELECT {{ tojson(var('fpl_season', env_var('FPL_SEASON', '2026-27'))) }} AS season,
        p.id AS player_id, p.team AS current_team_id, g.gameweek, c.checked_at,
        -- Conservative freshness bound for players without a fixture row in this GW.
        NOT EXISTS (
            SELECT 1 FROM {{ ref('stg_fixtures') }} f
            WHERE f.event = g.gameweek AND f.finished AND (f.team_h=p.team OR f.team_a=p.team)
              AND (f.kickoff_time IS NULL OR c.checked_at < TIMESTAMP_ADD(f.kickoff_time, INTERVAL 120 MINUTE))
        ) AND c.checked_at IS NOT NULL AS covered
    FROM {{ ref('stg_players') }} p CROSS JOIN completed g
    LEFT JOIN {{ source('fpl_raw', 'player_history_checks') }} c
      ON c.player_id=p.id AND c.season={{ tojson(var('fpl_season', env_var('FPL_SEASON', '2026-27'))) }}
)
SELECT s.*, COALESCE(h.fixture_count, 0) AS fixture_count,
    COALESCE(h.appearances, 0) AS appearances,
    IF(s.covered, COALESCE(h.points, 0), NULL) AS points,
    IF(s.covered, COALESCE(h.minutes, 0), NULL) AS minutes,
    IF(s.covered, COALESCE(h.starts, 0), NULL) AS starts,
    IF(s.covered, IF(h.fixture_count IS NULL, 0, h.xg), NULL) AS xg,
    IF(s.covered, IF(h.fixture_count IS NULL, 0, h.xa), NULL) AS xa,
    h.historical_team_id,
    CASE WHEN NOT s.covered THEN 'incomplete'
         WHEN h.fixture_count > 1 THEN 'multiple_fixtures'
         WHEN h.appearances > 0 THEN 'appeared'
         WHEN h.fixture_count > 0 THEN 'missed_appearance'
         ELSE 'no_record_membership_unknown' END AS gameweek_context
FROM scaffold s
LEFT JOIN history h USING (season, player_id, gameweek)
