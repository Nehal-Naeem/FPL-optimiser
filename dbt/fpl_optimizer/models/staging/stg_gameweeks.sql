SELECT
    id,
    name,
    finished,
    is_previous,
    is_current,
    is_next,
    ingested_at
FROM {{ source('fpl_raw','gameweeks')}}