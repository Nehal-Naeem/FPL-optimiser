import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import duckdb
import pandas as pd
import requests
from streamlit.testing.v1 import AppTest

from database import load_players
from fpl_api import FPLError, fetch_squad
from recommendations import best_transfers, match_squad, replacement_candidates


ROOT = Path(__file__).resolve().parents[1]


def sample_players():
    # Deliberately independent stored scores and values detect accidental recomputation.
    rows = [
        (1, 5.0, .3, .999, 3),  # Selected
        (2, 5.0, .8, .07, 3),  # Best viability, equal cost
        (3, 4.0, .7, .98, 3),  # Best stored value
        (4, 5.1, .9, .5, 3),  # Too expensive
        (5, 4.0, .9, .5, 2),  # Wrong position
        (6, 4.0, .3, .5, 3),  # Equal score
        (7, 4.0, .2, .5, 3),  # Lower score
        (8, 4.0, .95, .5, 3), # Already owned
        (9, 4.0, None, None, 3),
    ]
    players = pd.DataFrame(rows, columns=[
        "id", "cost", "viability_score", "viability_per_cost", "element_type",
    ])
    players["player_name"] = players.id.map(lambda i: f"Player {i}")
    players["position"] = players.element_type.map({2: "DEF", 3: "MID"})
    players["club"] = "Club"
    for field in ["form_percentile", "points_per_gw_percentile", "normalized_n5fs", "start_ratio"]:
        players[field] = .6
    return players


def sample_squad():
    ids = [1, 8, 9] + list(range(100, 112))
    return pd.DataFrame([{
        "id": player_id, "squad_order": order,
        "role": "Starting XI" if order <= 11 else "Bench",
        "player_name": f"API {player_id}", "position": "MID",
        "club": "API Club", "element_type": 3, "cost": 9.0,
    } for order, player_id in enumerate(ids, 1)])


class RecommendationTests(unittest.TestCase):
    def setUp(self):
        self.players = sample_players()
        self.squad = match_squad(sample_squad(), self.players)

    def test_preserves_full_squad_and_missing_metrics(self):
        self.assertEqual(len(self.squad), 15)
        self.assertEqual((self.squad.role == "Bench").sum(), 4)
        indexed = self.squad.set_index("id")
        self.assertEqual(indexed.loc[1, "cost"], 5.0)
        self.assertEqual(indexed.loc[1, "viability_per_cost"], .999)
        self.assertEqual(indexed.loc[9, "status"], "No evaluation")
        self.assertEqual(indexed.loc[100, "status"], "Not in database")
        self.assertEqual(indexed.loc[100, "player_name"], "API 100")
        self.assertTrue(pd.isna(indexed.loc[100, "viability_score"]))

    def test_eligibility_order_and_gains(self):
        selected = self.squad.iloc[0]
        candidates = replacement_candidates(selected, self.players, self.squad.id)
        self.assertEqual(candidates.id.tolist(), [2, 3])
        self.assertEqual(candidates.viability_score.tolist(), [.8, .7])
        self.assertEqual(candidates.viability_per_cost.tolist(), [.07, .98])
        self.assertAlmostEqual(candidates.iloc[0].viability_gain, .5)
        self.assertEqual(candidates.price_difference.tolist(), [0., -1.])

    def test_views_rank_by_the_stored_metric(self):
        by_score = best_transfers(self.squad, self.players, "viability_score")
        by_value = best_transfers(self.squad, self.players, "viability_per_cost")
        self.assertEqual(by_score.id.tolist(), [2])
        self.assertEqual(by_value.id.tolist(), [3])

    def test_no_evaluation_or_no_improvement_returns_empty(self):
        for player_id in [8, 9, 100]:
            selected = self.squad.loc[self.squad.id == player_id].iloc[0]
            self.assertTrue(replacement_candidates(selected, self.players, self.squad.id).empty)


class DatabaseTests(unittest.TestCase):
    def test_raw_scores_are_aliased_unchanged_and_database_is_not_written(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.duckdb"
            with duckdb.connect(str(path)) as con:
                con.execute("CREATE TABLE players AS SELECT 1 id, 'Player' web_name, 3 element_type, 1 team, 50 now_cost")
                con.execute("CREATE TABLE teams AS SELECT 1 id, 'Club' AS name")
                con.execute("CREATE TABLE positions AS SELECT 3 id, 'MID' singular_name_short")
                con.execute("""CREATE TABLE mart_player_evaluation AS SELECT
                    1 id, 'Player' web_name, 3 element_type, 'Club' club, 5.0 AS cost,
                    0.8123456789::DOUBLE viability_score,
                    0.987654321::DOUBLE viability_by_cost,
                    0.1 form_percentile, 0.2 points_per_gw_percentile,
                    0.3 normalized_n5fs, 0.4 start_ratio""")
            before = path.read_bytes()
            row = load_players(path).iloc[0]
            self.assertEqual(row.viability_score, .8123456789)
            self.assertEqual(row.viability_per_cost, .987654321)
            self.assertEqual(path.read_bytes(), before)


class ApiTests(unittest.TestCase):
    @patch("fpl_api.requests.get")
    def test_invalid_id_never_calls_network(self, get):
        for team_id in ["", "abc", "-1", "0", "1.2", "https://example.com"]:
            with self.assertRaises(FPLError):
                fetch_squad(team_id)
        get.assert_not_called()

    @patch("fpl_api.requests.get")
    def test_missing_team_and_network_failure(self, get):
        get.return_value = Mock(status_code=404)
        with self.assertRaisesRegex(FPLError, "No FPL team"):
            fetch_squad("123")
        get.side_effect = requests.Timeout()
        with self.assertRaisesRegex(FPLError, "Could not reach"):
            fetch_squad("123")

    @patch("fpl_api._get")
    def test_latest_published_gameweek_and_full_bench(self, get):
        get.side_effect = [
            {"name": "My Team", "current_event": 7},
            {"picks": [{"element": i, "position": i} for i in range(1, 16)]},
            {"elements": [], "teams": [], "element_types": []},
        ]
        result = fetch_squad("123")
        self.assertEqual(result["gameweek"], 7)
        self.assertEqual(len(result["players"]), 15)
        self.assertEqual((result["players"].role == "Bench").sum(), 4)
        self.assertEqual(get.call_args_list[1].args[0], "entry/123/event/7/picks")

    @patch("fpl_api._get", return_value={"current_event": None})
    def test_no_published_picks(self, get):
        with self.assertRaisesRegex(FPLError, "no published"):
            fetch_squad("123")


class StreamlitTests(unittest.TestCase):
    @patch("database.load_players", side_effect=sample_players)
    @patch("fpl_api.fetch_squad")
    def test_load_select_missing_player_and_invalid_reload(self, fetch, load):
        fetch.return_value = {
            "team_id": 123, "team_name": "Test Team", "gameweek": 7,
            "players": sample_squad(),
        }
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=15).run()
        self.assertFalse(app.exception)
        app.text_input[0].set_value("123")
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.dataframe[0].value), 15)
        self.assertEqual(len(app.tabs), 2)
        self.assertEqual(app.selectbox[0].value, 1)
        self.assertEqual(app.dataframe[1].value.player_name.tolist(), ["Player 2", "Player 3"])
        self.assertEqual(app.dataframe[0].value.iloc[0].viability_per_cost, .999)
        self.assertEqual(app.metric[3].value, "60.0%")
        self.assertNotIn("form_percentile", app.dataframe[0].value.columns)
        app.toggle[0].set_value(True).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.dataframe[0].value.iloc[0].form_percentile, .6)
        self.assertEqual(app.dataframe[1].value.iloc[0].viability_per_cost, .07)
        app.selectbox[0].select(100).run()
        self.assertFalse(app.exception)
        self.assertTrue(any("no saved evaluation" in info.value for info in app.info))
        fetch.assert_called_once_with("123")
        fetch.side_effect = FPLError("No FPL team was found for that ID.")
        app.text_input[0].set_value("999")
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.dataframe), 0)
        self.assertEqual(len(app.error), 1)

    @patch("database.load_players", side_effect=duckdb.IOException("Database locked"))
    @patch("fpl_api.fetch_squad")
    def test_database_failure_is_visible(self, fetch, load):
        fetch.return_value = {"players": sample_squad()}
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=15).run()
        app.text_input[0].set_value("123")
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertIn("Could not read", app.error[0].value)


if __name__ == "__main__":
    unittest.main()
