-- Shrink team goal rates toward league rates by five matches; simple transparent Poisson baseline.
WITH matches AS (
    SELECT f.* FROM {{ ref('stg_fixtures') }} f JOIN {{ ref('stg_gameweeks') }} g ON g.id=f.event
    WHERE f.finished AND g.finished AND g.data_checked AND f.team_h_score IS NOT NULL AND f.team_a_score IS NOT NULL
), league AS (
    SELECT GREATEST(AVG(team_h_score),0.1) AS home_goals, GREATEST(AVG(team_a_score),0.1) AS away_goals,
        GREATEST(AVG((team_h_score+team_a_score)/2.0),0.1) AS mean_goals FROM matches
), sides AS (
    SELECT team_h AS team_id,team_h_score AS scored,team_a_score AS conceded FROM matches
    UNION ALL SELECT team_a,team_a_score,team_h_score FROM matches
)
SELECT t.id AS team_id,COALESCE(l.home_goals,1.5) AS home_goals,
    COALESCE(l.away_goals,1.2) AS away_goals,COALESCE(l.mean_goals,1.35) AS mean_goals,
    SAFE_DIVIDE(COALESCE(SUM(s.scored),0)+5*COALESCE(l.mean_goals,1.35),COUNT(s.team_id)+5) AS attack,
    SAFE_DIVIDE(COALESCE(SUM(s.conceded),0)+5*COALESCE(l.mean_goals,1.35),COUNT(s.team_id)+5) AS defence
FROM {{ ref('stg_teams') }} t CROSS JOIN league l LEFT JOIN sides s ON s.team_id=t.id
GROUP BY t.id,l.home_goals,l.away_goals,l.mean_goals
