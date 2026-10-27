"""Public FPL squad fetching, independent of database and recommendations."""

import re

import pandas as pd
import requests


API_URL = "https://fantasy.premierleague.com/api"


class FPLError(Exception):
    """An actionable error suitable for display in the app."""


def _get(path, missing_message):
    try:
        response = requests.get(f"{API_URL}/{path}/", timeout=20)
        if response.status_code == 404:
            raise FPLError(missing_message)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise FPLError("Could not reach the FPL API. Please try again shortly.") from exc
    except ValueError as exc:
        raise FPLError("The FPL API returned an unreadable response. Please try again.") from exc


def fetch_squad(team_id):
    """Return the latest published picks, including the bench, with API labels."""
    team_id = str(team_id).strip()
    if not re.fullmatch(r"[0-9]{1,12}", team_id) or int(team_id) <= 0:
        raise FPLError("Enter a positive numeric FPL team ID, such as 7425041.")
    team_id = int(team_id)
    entry = _get(f"entry/{team_id}", "No FPL team was found for that ID.")
    try:
        gameweek = entry.get("current_event")
        if not gameweek:
            raise FPLError("This team has no published gameweek picks yet.")
        picks = _get(
            f"entry/{team_id}/event/{gameweek}/picks",
            f"Picks for Gameweek {gameweek} are not available yet. Please try again later.",
        )["picks"]
        if not picks:
            raise FPLError("This team has no published squad yet.")
        bootstrap = _get("bootstrap-static", "FPL player information is unavailable.")
        players = {p["id"]: p for p in bootstrap["elements"]}
        teams = {t["id"]: t["name"] for t in bootstrap["teams"]}
        positions = {p["id"]: p["singular_name_short"] for p in bootstrap["element_types"]}
        rows = []
        for pick in picks:
            player_id = pick["element"]
            player = players.get(player_id, {})
            rows.append({
                "id": player_id,
                "squad_order": pick["position"],
                "role": "Starting XI" if pick["position"] <= 11 else "Bench",
                "player_name": player.get("web_name", f"Player #{player_id}"),
                "element_type": player.get("element_type"),
                "position": positions.get(player.get("element_type"), "Unknown"),
                "club": teams.get(player.get("team"), "Unknown"),
                "cost": player["now_cost"] / 10.0 if "now_cost" in player else None,
            })
        return {
            "team_id": team_id,
            "team_name": entry.get("name", f"Team {team_id}"),
            "gameweek": gameweek,
            "players": pd.DataFrame(rows).sort_values("squad_order"),
        }
    except (KeyError, TypeError, AttributeError) as exc:
        raise FPLError("The FPL API returned incomplete squad data. Please try again.") from exc
