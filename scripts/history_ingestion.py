"""Deterministic history selection and typed FPL response handling."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import random
import re
import time
from threading import local
import requests

_sessions = local()
COUNTS = ("minutes", "starts", "total_points", "goals_scored", "assists", "clean_sheets",
          "goals_conceded", "own_goals", "penalties_saved", "penalties_missed", "yellow_cards",
          "red_cards", "saves", "bonus", "bps", "clearances_blocks_interceptions",
          "recoveries", "tackles", "defensive_contribution", "value", "selected",
          "transfers_balance", "transfers_in", "transfers_out")
DECIMALS = ("expected_goals", "expected_assists", "expected_goal_involvements",
            "expected_goals_conceded", "influence", "creativity", "threat", "ict_index")
REQUIRED = ("minutes", "starts", "total_points", "goals_scored", "assists")


def fetch_json(url, session=None, sleep=time.sleep, attempts=4):
    if session is None:
        if not hasattr(_sessions, "session"):
            _sessions.session = requests.Session()
        session = _sessions.session
    for attempt in range(attempts):
        response = None
        try:
            response = session.get(url, timeout=(10, 60))
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status is not None and status != 429 and not 500 <= status < 600:
                raise
            if attempt == attempts - 1:
                raise
            retry_after = response.headers.get("Retry-After", "") if response is not None else ""
            if retry_after.isdigit():
                delay = min(120, int(retry_after))
            else:
                try:
                    from email.utils import parsedate_to_datetime
                    delay = min(120, max(0, (parsedate_to_datetime(retry_after) - datetime.now(timezone.utc)).total_seconds()))
                except (TypeError, ValueError):
                    delay = 2 ** attempt + random.random()
            sleep(delay)


def validate_season(season, events):
    if not re.fullmatch(r"20\d{2}-\d{2}", season):
        raise ValueError("FPL_SEASON must have form 2026-27")
    year = int(season[:4])
    if int(season[-2:]) != (year + 1) % 100:
        raise ValueError("Invalid season range")
    deadlines = [datetime.fromisoformat(e["deadline_time"].replace("Z", "+00:00")) for e in events]
    if not deadlines or min(deadlines).year != year or min(deadlines).month < 7 or max(deadlines).year != year + 1:
        raise ValueError("API season does not match FPL_SEASON; refusing rollover")


def normalize_history(player_id, payload, season, run_id, now):
    if not isinstance(payload, dict) or not isinstance(payload.get("history"), list):
        raise ValueError(f"Incomplete history response for {player_id}")
    rows, seen = [], set()
    for item in payload["history"]:
        fixture = int(item["fixture"])
        if fixture <= 0 or fixture in seen or int(item["element"]) != player_id:
            raise ValueError("Duplicate fixture or mismatched player")
        seen.add(fixture)
        row = {"season": season, "player_id": player_id, "fixture_id": fixture,
               "gameweek": int(item["round"]), "opponent_team": int(item["opponent_team"]),
               "was_home": item["was_home"], "kickoff_time": item.get("kickoff_time"),
               "modified": item.get("modified", False)}
        for key in COUNTS:
            value = item.get(key)
            if key in REQUIRED and value is None:
                raise ValueError(f"Missing required history metric {key}")
            if value is not None and Decimal(str(value)) != int(value):
                raise ValueError(f"Non-integral metric {key}")
            row[key] = int(value) if value is not None else None
            if key not in ("total_points", "bps", "transfers_balance") and row[key] is not None and row[key] < 0:
                raise ValueError(f"Negative count {key}")
        for key in DECIMALS:
            value = item.get(key)
            try:
                number = Decimal(str(value)) if value is not None else None
                if number is not None and (not number.is_finite() or (key.startswith("expected_") and number < 0)):
                    raise ValueError(f"Invalid {key}")
                row[key] = str(number) if number is not None else None
            except InvalidOperation as exc:
                raise ValueError(f"Invalid decimal {key}") from exc
        if not 1 <= row["gameweek"] <= 38 or not 0 <= row["minutes"] <= 90 or row["starts"] not in (0, 1):
            raise ValueError("Invalid gameweek/minutes/starts")
        if type(row["was_home"]) is not bool or type(row["modified"]) is not bool:
            raise ValueError("Invalid history boolean")
        row["payload_hash"] = hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()
        row.update(ingested_at=now.isoformat(), run_id=run_id)
        rows.append(row)
    return rows


def fetch_histories(player_ids, season, run_id, now, fetch=fetch_json):
    def one(player_id):
        return normalize_history(player_id, fetch(
            f"https://fantasy.premierleague.com/api/element-summary/{player_id}/"), season, run_id, now)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(one, player): player for player in sorted(player_ids)}
        results = {}
        for future in as_completed(futures):
            player = futures[future]
            try:
                results[player] = future.result()
            except Exception as exc:
                for pending in futures:
                    pending.cancel()
                raise RuntimeError(f"History collection failed for player_id={player}") from exc
        return [row for player in sorted(results) for row in results[player]]


def select_players(players, fixtures, previous, checks, events, now):
    """Weekly sweeps catch older corrections; current and previously observed clubs are targeted."""
    catalog = {p["id"]: p for p in players}
    checks = {p: c for p, c in checks.items() if p in catalog}
    full = not checks or any(c.get("full_checked_at") is None or
                            now - c["full_checked_at"] >= timedelta(days=7) for c in checks.values())
    daily = not checks or any(c.get("daily_checked_at") is None or
                             now - c["daily_checked_at"] >= timedelta(days=1) for c in checks.values())
    selected = {p for p in catalog if p not in checks or checks[p]["team_id"] != catalog[p]["team"]}
    if full:
        return set(catalog), True, True
    recent = sorted(e["id"] for e in events if e["finished"] and e.get("data_checked"))[-2:]
    teams = set()
    for fixture in fixtures:
        old = previous.get(fixture["id"])
        if (fixture.get("finished") and fixture != old) or (daily and fixture.get("event") in recent):
            teams.update((fixture["team_h"], fixture["team_a"]))
    selected.update(p for p, row in catalog.items() if row["team"] in teams)
    selected.update(p for p, c in checks.items() if p in catalog and (c["team_id"] in teams or teams.intersection(c.get("historical_team_ids", []))))
    return selected, False, daily
