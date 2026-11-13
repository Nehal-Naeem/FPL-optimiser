{{ config(materialized='table') }}
WITH inputs AS (
    SELECT p.id AS player_id,p.element_type AS position,h.gameweek,h.horizon_index,h.as_of,
        f.id AS fixture_id,f.opponent_id,f.opponent,f.home_away,f.kickoff_time,f.difficulty,
        r.* EXCEPT(player_id),
        IF(h.horizon_index=1,
            IF(p.chance_of_playing_next_round IS NOT NULL,LEAST(1,GREATEST(0,p.chance_of_playing_next_round/100.0)),
               IF(p.status IN ('i','s','u'),0.0,1.0)),1.0) AS availability_factor,
        LEAST(1.5,GREATEST(0.5,SAFE_DIVIDE(o.defence,t.mean_goals)*
            SAFE_DIVIDE(IF(f.home_away='H',t.home_goals,t.away_goals),t.mean_goals))) AS attacking_factor,
        GREATEST(0.05,SAFE_DIVIDE(o.attack*t.defence,t.mean_goals*t.mean_goals)*
            IF(f.home_away='H',t.away_goals,t.home_goals)) AS opponent_goals,
        IF(p.status!='a' AND h.horizon_index>1,'Future availability unconfirmed; historical role assumed',
           IF(h.horizon_index=1 AND p.status!='a','Next-GW FPL availability adjustment','Historical role assumed')) AS availability_note
    FROM {{ ref('stg_players') }} p
    JOIN {{ ref('int_team_fixtures') }} f ON f.team_id=p.team
    JOIN {{ ref('int_projection_horizon') }} h ON h.gameweek=f.event
    JOIN {{ ref('int_player_projection_rates') }} r ON r.player_id=p.id
    JOIN {{ ref('int_team_projection_strength') }} t ON t.team_id=p.team
    JOIN {{ ref('int_team_projection_strength') }} o ON o.team_id=f.opponent_id
    WHERE NOT COALESCE(f.started,FALSE) AND NOT COALESCE(f.finished,FALSE)
), minutes AS (
    SELECT *,p_play*availability_factor AS play_probability,p_60*availability_factor AS sixty_probability,
        availability_factor*(p_60*long_minutes+(p_play-p_60)*short_minutes) AS expected_minutes
    FROM inputs
), components AS (
    SELECT *, play_probability+sixty_probability AS appearance_points,
        expected_minutes*xg_per_minute*attacking_factor*CASE position WHEN 1 THEN 10 WHEN 2 THEN 6 WHEN 3 THEN 5 ELSE 4 END AS goal_points,
        expected_minutes*xa_per_minute*attacking_factor*3 AS assist_points,
        sixty_probability*EXP(-opponent_goals*long_minutes/90)*CASE WHEN position IN (1,2) THEN 4 WHEN position=3 THEN 1 ELSE 0 END AS clean_sheet_points,
        IF(position=1,expected_minutes*saves_per_minute,0) AS save_points,
        IF(position=1,expected_minutes*penalties_per_minute,0) AS penalty_save_points,
        IF(position=1,0,LEAST(2*play_probability,expected_minutes*defensive_per_minute)) AS defensive_points,
        LEAST(3*play_probability,expected_minutes*bonus_per_minute) AS bonus_points,
        -expected_minutes*deductions_per_minute-IF(position IN (1,2),
          sixty_probability*(opponent_goals*long_minutes/180-(1-EXP(-2*opponent_goals*long_minutes/90))/4)+
          (play_probability-sixty_probability)*(opponent_goals*short_minutes/180-(1-EXP(-2*opponent_goals*short_minutes/90))/4),0) AS deduction_points
    FROM minutes
)
SELECT *,appearance_points+goal_points+assist_points+clean_sheet_points+save_points+penalty_save_points+
    defensive_points+bonus_points+deduction_points AS expected_points,
    'experimental-points-v1' AS projection_method
FROM components
