{{ config(materialized='table') }}
WITH totals AS (
    SELECT player_id,gameweek,COUNT(*) AS fixture_count,SUM(expected_points) AS expected_points,
        SUM(expected_minutes) AS expected_minutes,
        SUM(appearance_points) AS appearance_points,SUM(goal_points) AS goal_points,SUM(assist_points) AS assist_points,
        SUM(clean_sheet_points) AS clean_sheet_points,SUM(save_points) AS save_points,
        SUM(penalty_save_points) AS penalty_save_points,SUM(defensive_points) AS defensive_points,
        SUM(bonus_points) AS bonus_points,SUM(deduction_points) AS deduction_points,
        -- Conservative across-fixture dependence assumption: use the best fixture's appearance likelihood.
        MAX(play_probability) AS play_probability,MAX(sixty_probability) AS sixty_probability,
        ARRAY_AGG(STRUCT(fixture_id,opponent_id,opponent,home_away,kickoff_time,difficulty,
            expected_points,expected_minutes,play_probability,sixty_probability,
            appearance_points,goal_points,assist_points,clean_sheet_points,save_points,penalty_save_points,
            defensive_points,bonus_points,deduction_points,attacking_factor,opponent_goals,
            xg_per_minute,xa_per_minute,saves_per_minute,penalties_per_minute,defensive_per_minute,
            bonus_per_minute,deductions_per_minute)
            ORDER BY kickoff_time IS NULL,kickoff_time,fixture_id) AS fixtures,
        ANY_VALUE(availability_note) AS availability_note
    FROM {{ ref('mart_player_fixture_projection') }} GROUP BY player_id,gameweek
)
SELECT p.id AS player_id,h.gameweek,h.deadline_time,h.as_of,COALESCE(t.fixture_count,0) AS fixture_count,
    COALESCE(t.expected_points,0) AS expected_points,COALESCE(t.expected_minutes,0) AS expected_minutes,
    COALESCE(t.play_probability,0) AS play_probability,COALESCE(t.sixty_probability,0) AS sixty_probability,
    COALESCE(t.appearance_points,0) AS appearance_points,COALESCE(t.goal_points,0) AS goal_points,
    COALESCE(t.assist_points,0) AS assist_points,COALESCE(t.clean_sheet_points,0) AS clean_sheet_points,
    COALESCE(t.save_points,0) AS save_points,COALESCE(t.penalty_save_points,0) AS penalty_save_points,
    COALESCE(t.defensive_points,0) AS defensive_points,COALESCE(t.bonus_points,0) AS bonus_points,
    COALESCE(t.deduction_points,0) AS deduction_points,COALESCE(t.fixtures,[]) AS fixtures,
    COALESCE(t.availability_note,'No assigned fixtures: confirmed blank in this snapshot') AS availability_note,
    r.history_fixtures,r.history_minutes,r.data_support,'experimental-points-v1' AS projection_method,
    EXISTS(SELECT 1 FROM {{ ref('stg_fixtures') }} uf WHERE uf.event IS NULL
        AND NOT COALESCE(uf.finished,FALSE) AND (uf.team_h=p.team OR uf.team_a=p.team)) AS unassigned_fixtures
FROM {{ ref('stg_players') }} p CROSS JOIN {{ ref('int_projection_horizon') }} h
JOIN {{ ref('int_player_projection_rates') }} r ON r.player_id=p.id
LEFT JOIN totals t ON t.player_id=p.id AND t.gameweek=h.gameweek
