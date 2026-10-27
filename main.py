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
con.execute("DROP TABLE IF EXISTS fct_rolling_team_fixtures")
con.execute("DROP TABLE IF EXISTS fct_rolling_player_fixtures")
con.execute("DROP TABLE IF EXISTS mart_player_outlook")
con.execute("DROP TABLE IF EXISTS mart_player_evaluation")
con.execute("DROP TABLE IF EXISTS parsed_players_summary")

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

con.execute("""
    CREATE TABLE fct_rolling_team_fixtures AS
    WITH upcoming_fixtures AS (
        SELECT
            *,
            ROW_NUMBER() OVER (
                PARTITION BY team_id
                ORDER BY kickoff_time
            ) AS fixture_number
        FROM fct_team_fixtures
        WHERE finished = false
    )

    SELECT
        *,
        6 - difficulty AS fixture_ease,
        6 - fixture_number AS fixture_weight,
    FROM upcoming_fixtures
    WHERE fixture_number <= 5
    ORDER BY team_id, fixture_number
    """
)

con.execute("""
    CREATE TABLE fct_rolling_player_fixtures AS
    SELECT
        p.*,
        rtf.club,
        rtf.opponent,
        rtf.home_away,
        rtf.difficulty,
        rtf.fixture_number,
        rtf.fixture_ease,
        rtf.fixture_weight,
        
    FROM players p

    LEFT JOIN fct_rolling_team_fixtures rtf
        ON p.team = rtf.team_id

    ORDER BY p.team, p.id, rtf.fixture_number 
    
    """
)

con.execute("""
    CREATE TABLE mart_player_outlook AS
    WITH season_progress AS (
        SELECT
            COUNT(*) AS elapsed_gws
        FROM gameweeks
        WHERE finished = True
    )

    SELECT
        id,
        web_name,
        element_type,
        team,
        club,
        now_cost/10 AS cost,
        form,
        total_points,
        minutes,
        starts,
        SUM(fixture_ease * fixture_weight)/ SUM(fixture_weight) AS next_5_fixtures_score,
        total_points / sp.elapsed_gws as points_per_gw,
        minutes / sp.elapsed_gws as minutes_per_gw,
        starts /  sp.elapsed_gws as start_ratio

    FROM fct_rolling_player_fixtures rpf

    CROSS JOIN season_progress sp

    WHERE minutes > 60

    GROUP BY id, web_name, element_type, team, club, cost, form, total_points, minutes, starts, sp.elapsed_gws
    ORDER BY total_points  DESC
    
    """
)

con.execute("""
    CREATE TABLE mart_player_evaluation AS
    SELECT 
        *,
        CUME_DIST() OVER (
            PARTITION BY element_type
            ORDER BY FORM
        ) AS form_percentile,
        (next_5_fixtures_score - 1) / 4 AS normalized_n5fs,
        CUME_DIST() OVER (
            PARTITION BY element_type
            ORDER BY points_per_gw
        ) AS points_per_gw_percentile,
        0.3*form_percentile + 0.45*normalized_n5fs + 0.25*points_per_gw_percentile AS viability_score,
        viability_score / cost AS viability_by_cost
    
    FROM mart_player_outlook

    ORDER BY viability_score DESC
    """
)

# con.execute("""
#     CREATE TABLE parsed_players_summary AS
#     SELECT
#         p.id,
#         p.web_name,
#         t.name as club,
#         pos.singular_name as position,
#         p.now_cost / 10.0 AS price

#     FROM players p

#     LEFT JOIN teams t
#         ON p.team = t.id
    
#     LEFT JOIN positions pos
#         ON p.element_type = pos.id;
# """)