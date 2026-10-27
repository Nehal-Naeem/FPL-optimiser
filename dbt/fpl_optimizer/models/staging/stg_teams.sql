SELECT
    id,
    code,
    name,
    short_name,
    win,
    draw,
    loss,
    strength_overall_home,
    strength_overall_away,
FROM {{ source('fpl_raw','teams')}}