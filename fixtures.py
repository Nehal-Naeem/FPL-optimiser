import requests
import pandas as pd
import duckdb 

fixtures_url = "https://fantasy.premierleague.com/api/fixtures"
con = duckdb.connect("data/fpl.duckdb")

fixtures = requests.get(fixtures_url).json()

fixtures_df = pd.DataFrame(fixtures)[[
    "id",
    "code",
    "event",
    "finished",
    "finished_provisional",
    "minutes",
    "provisional_start_time",
    "started",
    "team_a",
    "team_a_score",
    "team_h",
    "team_h_score",
    "team_h_difficulty",
    "team_a_difficulty"
]]
