import requests
import pandas as pd
import duckdb

# import fixtures

fixtures_url = "https://fantasy.premierleague.com/api/fixtures"
bootstrap_url = "https://fantasy.premierleague.com/api/bootstrap-static/"
con = duckdb.connect("data/fpl.duckdb")

bootstrap = requests.get(bootstrap_url).json()
fixtures = requests.get(fixtures_url).json()

players = bootstrap["elements"]
gameweeks = bootstrap["events"]
positions = bootstrap["element_types"]
teams = bootstrap["teams"]

players_df = pd.DataFrame(players)[[
    "id",
    "web_name",
    "team",
    "element_type",
    "now_cost",
    "total_points",
    "form",
    "minutes",
    "goals_scored",
    "assists",
    "clean_sheets",
    "goals_conceded",
    "saves",
    "bonus",
    "defensive_contribution",
    "starts",
]]
players_df["form"] = pd.to_numeric(players_df["form"], errors="coerce")

gameweeks_df = pd.DataFrame(gameweeks)[[
    "id",
    "name",
    "finished",
    "is_previous",
    "is_current",
    "is_next"
]]

positions_df = pd.DataFrame(positions)[[
    "id",
    "plural_name",
    "singular_name",
    "singular_name_short"
]]

teams_df = pd.DataFrame(teams)[[
    "id",
    "code",
    "name",
    "short_name",
    "win",
    "draw",
    "loss",
    "strength_overall_home",
    "strength_overall_away",
]]

fixtures_df = pd.DataFrame(fixtures)[[
    "id",
    "code",
    "event",
    "finished",
    "finished_provisional",
    "minutes",
    "kickoff_time",
    "provisional_start_time",
    "started",
    "team_a",
    "team_a_score",
    "team_h",
    "team_h_score",
    "team_h_difficulty",
    "team_a_difficulty"
]]
fixtures_df["kickoff_time"] = pd.to_datetime(fixtures_df["kickoff_time"])

con.execute("DROP TABLE IF EXISTS players")
con.execute("DROP TABLE IF EXISTS gameweeks")
con.execute("DROP TABLE IF EXISTS teams")
con.execute("DROP TABLE IF EXISTS positions")
con.execute("DROP TABLE IF EXISTS fixtures")
con.execute("DROP TABLE IF EXISTS fct_team_fixtures")

con.execute("""
    CREATE TABLE players AS
    SELECT * FROM players_df
    """
)

con.execute("""
    CREATE TABLE gameweeks AS
    SELECT * FROM gameweeks_df
    """
)

con.execute("""
    CREATE TABLE teams AS
    SELECT * FROM teams_df
    """
)

con.execute("""
    CREATE TABLE positions AS
    SELECT * FROM positions_df
    """
)

con.execute("""
    CREATE TABLE fixtures AS
    SELECT * FROM fixtures_df
    """
)

con.execute("""
    CREATE TABLE fct_team_fixtures AS
    SELECT 
        f.id,
        f.event,
        f.finished,
        f.kickoff_time,
        f.team_h as team_id,
        f.team_a as opponent_id,
        th.name as club,
        ta.name as opponent,
        'H' as home_away,
        f.team_h_difficulty as difficulty

    FROM fixtures f

    LEFT JOIN teams th
        ON f.team_h = th.id
    
    LEFT JOIN teams ta
        ON f.team_a = ta.id

    UNION ALL

    SELECT 
        f.id,
        f.event,
        f.finished,
        f.kickoff_time,
        f.team_a as team_id,
        f.team_h as opponent_id,
        ta.name as club,
        th.name as opponent,
        'A' as home_away,
        f.team_a_difficulty as difficulty

    FROM fixtures f

    LEFT JOIN teams th
        ON f.team_h = th.id
    
    LEFT JOIN teams ta
        ON f.team_a = ta.id

    ORDER BY id, event
    """
)

# Recommendation planning is served by the cloud points pipeline; this script only refreshes local inputs/fixtures.
