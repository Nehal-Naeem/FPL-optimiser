SELECT
    id,
    code,
    event,
    finished,
    finished_provisional,
    minutes,
    kickoff_time,
    provisional_start_time,
    started,
    team_a,
    team_a_score,
    team_h,
    team_h_score,
    team_h_difficulty,
    team_a_difficulty
FROM {{ source('fpl_raw','fixtures')}}