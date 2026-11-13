SELECT
    id,
    name,
    finished,
    data_checked,
    deadline_time,
    is_previous,
    is_current,
    is_next,
    ingested_at
FROM {{ source('fpl_raw','gameweeks')}}