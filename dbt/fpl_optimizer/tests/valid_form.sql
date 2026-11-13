SELECT id FROM {{ ref('stg_players') }} WHERE form IS NULL OR IS_NAN(form) OR IS_INF(form)
