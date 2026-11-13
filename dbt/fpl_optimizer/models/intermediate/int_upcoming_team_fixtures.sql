-- Display rule intentionally differs from the unchanged legacy scoring fixture selector.
SELECT * FROM {{ ref('int_team_fixtures') }}
WHERE NOT COALESCE(started,FALSE) AND NOT COALESCE(finished,FALSE)
QUALIFY ROW_NUMBER() OVER (PARTITION BY team_id ORDER BY kickoff_time IS NULL, kickoff_time, id)<=5
