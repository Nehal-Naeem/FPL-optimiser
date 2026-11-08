WITH season_progress AS (
    SELECT
        COUNT(*) AS elapsed_gws
    FROM {{ ref('stg_gameweeks') }}
    WHERE finished = TRUE
),

players AS (
    SELECT *
    FROM {{ ref('stg_players') }}
),

positions AS (
    SELECT *
    FROM {{ ref('stg_positions') }}
),

rolling_team_fixtures AS (
    SELECT *
    FROM {{ ref('int_rolling_team_fixtures') }}
),

player_fixture_outlook AS (
    SELECT
        p.id,
        p.web_name,
        p.element_type,
        po.singular_name AS position,
        p.team,
        rtf.club,
        p.now_cost,
        p.form,
        p.total_points,
        p.minutes,
        p.starts,

        rtf.fixture_ease,
        rtf.fixture_weight

    FROM players p

    LEFT JOIN rolling_team_fixtures rtf
        ON p.team = rtf.team_id
    LEFT JOIN positions po
        ON p.element_type = po.id
)

SELECT
    pfo.id,
    pfo.web_name,
    pfo.element_type,
    pfo.position,
    pfo.team,
    pfo.club,

    SAFE_DIVIDE(pfo.now_cost, 10.0) AS cost,

    pfo.form,
    pfo.total_points,
    pfo.minutes,
    pfo.starts,

    SAFE_DIVIDE(
        SUM(pfo.fixture_ease * pfo.fixture_weight),
        SUM(pfo.fixture_weight)
    ) AS next_5_fixtures_score,

    SAFE_DIVIDE(
        pfo.total_points,
        sp.elapsed_gws
    ) AS points_per_gw,

    SAFE_DIVIDE(
        pfo.minutes,
        sp.elapsed_gws
    ) AS minutes_per_gw,

    SAFE_DIVIDE(
        pfo.starts,
        sp.elapsed_gws
    ) AS starts_per_gw

FROM player_fixture_outlook pfo

CROSS JOIN season_progress sp

WHERE pfo.minutes > 60

GROUP BY
    pfo.id,
    pfo.web_name,
    pfo.element_type,
    pfo.position,
    pfo.team,
    pfo.club,
    pfo.now_cost,
    pfo.form,
    pfo.total_points,
    pfo.minutes,
    pfo.starts,
    sp.elapsed_gws