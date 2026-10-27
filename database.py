"""Read the existing FPL snapshot without changing its schema or scores."""

from pathlib import Path

import duckdb


DATABASE_PATH = Path(__file__).resolve().parent / "data" / "fpl.duckdb"


def load_players(database_path=DATABASE_PATH):
    """Include unevaluated players; expose the stored value metric by an alias."""
    with duckdb.connect(str(database_path), read_only=True) as con:
        return con.execute("""
            SELECT
                p.id,
                COALESCE(e.web_name, p.web_name) AS player_name,
                COALESCE(e.element_type, p.element_type) AS element_type,
                pos.singular_name_short AS position,
                COALESCE(e.club, t.name) AS club,
                COALESCE(e.cost, p.now_cost / 10.0) AS cost,
                e.viability_score,
                e.viability_by_cost AS viability_per_cost,
                e.form_percentile,
                e.points_per_gw_percentile,
                e.normalized_n5fs,
                e.start_ratio
            FROM players p
            LEFT JOIN mart_player_evaluation e ON e.id = p.id
            LEFT JOIN positions pos
                ON pos.id = COALESCE(e.element_type, p.element_type)
            LEFT JOIN teams t ON t.id = p.team
        """).fetchdf()
