SELECT
    id,
    plural_name,
    singular_name,
    singular_name_short
FROM {{ source('fpl_raw','positions')}}