WITH fixtures AS (
    SELECT *
    FROM {{ ref('stg_fixtures') }}
),

teams AS (
    SELECT *
    FROM {{ ref('stg_teams') }}
),

home_rows AS (
    SELECT 
        f.id,
        f.event,
        f.finished,
        f.kickoff_time,
        f.team_h AS team_id,
        f.team_a AS opponent_id,
        th.name AS club,
        ta.name AS opponent,
        'H' AS home_away,
        f.team_h_difficulty AS difficulty
    FROM fixtures f
    LEFT JOIN teams th
        ON f.team_h = th.id
    LEFT JOIN teams ta
        ON f.team_a = ta.id
),

away_rows AS (
    SELECT 
        f.id,
        f.event,
        f.finished,
        f.kickoff_time,
        f.team_a AS team_id,
        f.team_h AS opponent_id,
        ta.name AS club,
        th.name AS opponent,
        'A' AS home_away,
        f.team_a_difficulty AS difficulty
    FROM fixtures f
    LEFT JOIN teams th
        ON f.team_h = th.id
    LEFT JOIN teams ta
        ON f.team_a = ta.id
)

SELECT * FROM home_rows
UNION ALL
SELECT * FROM away_rows