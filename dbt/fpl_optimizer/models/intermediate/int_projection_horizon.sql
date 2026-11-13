-- A frozen, actionable five-GAMEWEEK horizon; never infer a postponed fixture's event.
WITH snapshot AS (
    SELECT checked_at AS as_of FROM {{ source('fpl_raw','pipeline_runs') }}
    WHERE run_id={{ tojson(env_var('FPL_RUN_ID','local-validation')) }} AND ingestion_complete
)
SELECT g.id AS gameweek, SAFE_CAST(g.deadline_time AS TIMESTAMP) AS deadline_time, s.as_of,
    ROW_NUMBER() OVER(ORDER BY SAFE_CAST(g.deadline_time AS TIMESTAMP),g.id) AS horizon_index
FROM {{ ref('stg_gameweeks') }} g CROSS JOIN snapshot s
WHERE SAFE_CAST(g.deadline_time AS TIMESTAMP)>s.as_of
QUALIFY horizon_index<=5
