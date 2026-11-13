-- Each current catalog must belong to this workflow execution, including nonempty input.
{% for table in ['players','teams','positions','gameweeks','fixtures'] %}
SELECT '{{ table }}' AS failed_table
FROM (
    SELECT COUNT(*) AS total_rows,
        COUNTIF(run_id={{ tojson(env_var('FPL_RUN_ID','local-validation')) }}) AS run_rows
    FROM {{ source('fpl_raw',table) }}
)
WHERE total_rows=0 OR run_rows!=total_rows
{% if not loop.last %} UNION ALL {% endif %}
{% endfor %}
