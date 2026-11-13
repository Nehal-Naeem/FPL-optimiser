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
    v.*,
    SAFE_DIVIDE(v.viability_score, v.cost) AS viability_by_cost,
    r.cutoff_gameweek AS recent_cutoff_gameweek,
    r.window_gameweeks AS recent_window_gameweeks,
    r.complete AS recent_complete,
    r.points AS recent_points,
    r.minutes AS recent_minutes,
    r.starts AS recent_starts,
    r.points_per_gw AS recent_points_per_gw,
    r.minutes_per_gw AS recent_minutes_per_gw,
    r.xg_per_90 AS recent_xg_per_90,
    r.xa_per_90 AS recent_xa_per_90
FROM viability v
LEFT JOIN (
    SELECT * FROM {{ ref('int_player_recent_form') }}
    QUALIFY cutoff_gameweek=MAX(cutoff_gameweek) OVER ()
) r ON r.player_id=v.id