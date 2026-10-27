SELECT
    id,
    web_name,
    team,
    element_type,
    now_cost,
    total_points,
    SAFE_CAST(form AS FLOAT64) AS form ,
    minutes,
    goals_scored,
    assists,
    clean_sheets,
    goals_conceded,
    saves,
    bonus,
    defensive_contribution,
    starts,
    ingested_at
FROM {{ source('fpl_raw','players')}}
