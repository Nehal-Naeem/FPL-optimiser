WITH team_fixtures AS (
    SELECT *
    FROM {{ ref("int_team_fixtures")}}
),
upcoming_fixtures AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY team_id
            ORDER BY kickoff_time
        ) AS fixture_number
    FROM team_fixtures
    WHERE finished = false
)

SELECT
    *,
    6 - difficulty AS fixture_ease,
    6 - fixture_number AS fixture_weight,
FROM upcoming_fixtures
WHERE fixture_number <= 5
ORDER BY team_id, fixture_number