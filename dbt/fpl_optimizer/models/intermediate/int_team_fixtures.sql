WITH fixtures AS (

    SELECT *
    FROM {{ ref('stg_fixtures') }}

),

team_fixtures AS (

    SELECT
        id AS fixture_id,
        event AS gameweek_id,
        kickoff_time,
        finished,
        team_h AS team_id,
        team_a AS opponent_id,
        "H" AS home_away,
        team_h_difficulty AS difficulty 
    FROM fixtures

    UNION ALL

    SELECT
        id AS fixture_id,
        event AS gameweek_id,
        kickoff_time,
        finished,
        team_a AS team_id,
        team_h AS opponent_id,
        'A' AS home_away,
        team_a_difficulty AS difficulty
    FROM fixtures
    
)

SELECT *
FROM team_fixtures