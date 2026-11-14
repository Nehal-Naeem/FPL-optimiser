{{ config(materialized='table') }}
WITH projections AS (
    SELECT player_id,ARRAY_AGG(STRUCT(gameweek,deadline_time,as_of,fixture_count,expected_points,
        expected_minutes,play_probability,sixty_probability,appearance_points,goal_points,assist_points,
        clean_sheet_points,save_points,penalty_save_points,defensive_points,bonus_points,deduction_points,
        fixtures,availability_note,history_fixtures,history_minutes,data_support,projection_method,unassigned_fixtures)
        ORDER BY gameweek) AS weeks
    FROM {{ ref('mart_player_gameweek_projection') }} GROUP BY player_id
), recent AS (
    SELECT * FROM {{ ref('int_player_recent_form') }}
    QUALIFY cutoff_gameweek=MAX(cutoff_gameweek) OVER ()
), manifest AS (
    SELECT * FROM {{ source('fpl_raw','pipeline_runs') }}
    WHERE run_id={{ tojson(env_var('FPL_RUN_ID','local-validation')) }} AND ingestion_complete
), upcoming AS (
    SELECT f.team_id,
        ARRAY_AGG(STRUCT(f.id, f.opponent_id,
            COALESCE(f.opponent,CAST(f.opponent_id AS STRING)) AS opponent,
            COALESCE(t.short_name,CAST(f.opponent_id AS STRING)) AS opponent_short,
            f.home_away, f.event AS gameweek, f.kickoff_time, f.difficulty)
            ORDER BY f.kickoff_time IS NULL,f.kickoff_time,f.id) AS fixtures
    FROM {{ ref('int_upcoming_team_fixtures') }} f
    LEFT JOIN {{ ref('stg_teams') }} t ON t.id=f.opponent_id
    GROUP BY f.team_id
)
SELECT p.id, p.web_name AS name, p.team AS team_id, COALESCE(t.short_name,CAST(p.team AS STRING)) AS club,
    p.element_type AS position, p.now_cost AS price,
    p.total_points AS season_points, p.minutes AS season_minutes, p.starts AS season_starts,
    COALESCE(p.status,'u') AS status, COALESCE(p.news,'') AS news, p.chance_of_playing_next_round AS chance_of_playing,
    COALESCE(pr.weeks,[]) AS projections,
    COALESCE(u.fixtures,[]) AS upcoming_fixtures,
    IF(r.player_id IS NULL,NULL,STRUCT(r.cutoff_gameweek, r.window_start_gameweek, r.window_gameweeks,
        r.covered_gameweeks, r.complete, r.history_checked_at, r.points, r.minutes, r.starts,
        r.points_per_gw, r.minutes_per_gw, r.points_per_90, r.xg_per_90, r.xa_per_90,
        r.short_window_gameweeks, r.short_points_per_gw, r.short_minutes_per_gw)) AS recent,
    2 AS contract_version, m.run_id AS publication_id, m.season,
    CURRENT_TIMESTAMP() AS projections_updated_at, m.checked_at AS catalog_updated_at,
    m.checked_at AS fixtures_updated_at, m.checked_at AS last_checked_at
FROM {{ ref('stg_players') }} p
JOIN {{ ref('stg_teams') }} t ON t.id=p.team
LEFT JOIN recent r ON r.player_id=p.id
LEFT JOIN projections pr ON pr.player_id=p.id
LEFT JOIN upcoming u ON u.team_id=p.team
CROSS JOIN manifest m
