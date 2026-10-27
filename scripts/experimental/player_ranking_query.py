import duckdb

con = duckdb.connect("data/fpl.duckdb")

# result = con.execute("""
#     SELECT * FROM fct_rolling_team_fixtures
#     WHERE team_id = 7
# """).fetchdf()

result = con.execute("""
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
        0.35*form_percentile + 0.4*normalized_n5fs + 0.25*points_per_gw_percentile AS viability_score,
        viability_score / cost AS viability_by_cost

    
    FROM mart_player_outlook
    WHERE element_type = 3

    ORDER BY viability_by_cost DESC
    LIMIT 10

"""
).fetch_df()

print(result)