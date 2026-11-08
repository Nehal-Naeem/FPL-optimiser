WITH player_features AS (
    SELECT
        *,
        CUME_DIST() OVER (
            PARTITION BY element_type
            ORDER BY form
        ) AS form_percentile,

        (next_5_fixtures_score - 1) / 4 AS normalized_n5fs,

        CUME_DIST() OVER (
            PARTITION BY element_type
            ORDER BY points_per_gw
        ) AS points_per_gw_percentile

    FROM {{ ref('int_player_outlook')}}
),

viability AS (
    SELECT
        *,
        0.30 * form_percentile
        + 0.45 * normalized_n5fs
        + 0.25 * points_per_gw_percentile AS viability_score

    FROM player_features
)

SELECT
    *,
    SAFE_DIVIDE(viability_score, cost) AS viability_by_cost
FROM viability