from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
import pytest
import requests

from scripts.history_ingestion import fetch_json, normalize_history, select_players, validate_season

NOW = datetime(2026, 11, 13, tzinfo=timezone.utc)


def sample(**changes):
    return dict(element=1, fixture=10, round=5, opponent_team=2, was_home=True, minutes=90,
                starts=1, total_points=-1, goals_scored=0, assists=0, expected_goals="0.25",
                expected_assists=None, **changes)


def normal(row):
    return normalize_history(1, {"history": [row]}, "2026-27", "one", NOW)[0]


def test_types_null_metrics_negative_points_and_stable_hash():
    row = normal(sample())
    assert row["total_points"] == -1
    assert row["expected_goals"] == "0.25" and row["expected_assists"] is None
    later = normalize_history(1, {"history": [sample()]}, "2026-27", "two", NOW + timedelta(days=1))[0]
    assert later["payload_hash"] == row["payload_hash"]
    changed = sample()
    changed["total_points"] = 6
    assert normal(changed)["payload_hash"] != row["payload_hash"]


@pytest.mark.parametrize("field,value", [("minutes", 91), ("starts", 2), ("round", 39),
    ("expected_goals", "NaN"), ("expected_assists", "-0.1"), ("minutes", None), ("was_home", "true")])
def test_invalid_history_rejected(field, value):
    row = sample()
    row[field] = value
    with pytest.raises((ValueError, TypeError)):
        normal(row)


def test_empty_success_differs_from_missing_history_and_duplicates():
    assert normalize_history(1, {"history": []}, "2026-27", "one", NOW) == []
    with pytest.raises(ValueError):
        normalize_history(1, {}, "2026-27", "one", NOW)
    with pytest.raises(ValueError):
        normalize_history(1, {"history": [sample(), sample()]}, "2026-27", "one", NOW)


def test_retry_after_and_no_retry_of_permanent_errors():
    limited = Mock(status_code=429, headers={"Retry-After": "3"})
    limited.raise_for_status.side_effect = requests.HTTPError(response=limited)
    success = Mock()
    success.json.return_value = {"history": []}
    session, sleep = Mock(), Mock()
    session.get.side_effect = [limited, success]
    assert fetch_json("https://test", session, sleep) == {"history": []}
    sleep.assert_called_once_with(3)
    missing = Mock(status_code=404)
    missing.raise_for_status.side_effect = requests.HTTPError(response=missing)
    session.get.reset_mock()
    session.get.side_effect = [missing]
    with pytest.raises(requests.HTTPError):
        fetch_json("https://test", session, sleep)
    assert session.get.call_count == 1


def test_timeout_exhaustion():
    session = Mock()
    session.get.side_effect = requests.Timeout()
    with pytest.raises(requests.Timeout):
        fetch_json("https://test", session, Mock(), attempts=2)
    assert session.get.call_count == 2


def test_season_rollover_guard():
    events = [{"deadline_time": "2026-08-20T12:00:00Z"}, {"deadline_time": "2027-05-20T12:00:00Z"}]
    validate_season("2026-27", events)
    with pytest.raises(ValueError):
        validate_season("2025-26", events)


def test_targeted_changes_daily_and_weekly():
    players = [{"id": 1, "team": 1}, {"id": 2, "team": 2}, {"id": 3, "team": 3}]
    checks = {p["id"]: {"team_id": p["team"], "full_checked_at": NOW, "daily_checked_at": NOW,
                          "historical_team_ids": []} for p in players}
    fixture = {"id": 10, "team_h": 1, "team_a": 2, "event": 5, "finished": False}
    assert select_players(players, [fixture], {10: fixture}, checks, [], NOW)[0] == set()
    finished = dict(fixture, finished=True)
    assert select_players(players, [finished], {10: fixture}, checks, [], NOW)[0] == {1, 2}
    # Previously transferred participant is still targeted using history-derived clubs.
    checks[3]["historical_team_ids"] = [1]
    assert select_players(players, [finished], {10: fixture}, checks, [], NOW)[0] == {1, 2, 3}
    assert select_players(players, [fixture], {10: fixture}, checks, [], NOW + timedelta(days=7))[1:]==(True, True)
    assert select_players(players, [fixture], {10: fixture}, checks,
                          [{"id": 5, "finished": True, "data_checked": True}], NOW + timedelta(days=1))[0] == {1, 2, 3}
    # Removed players cannot force a full sweep on every execution.
    checks[99] = {"team_id": 20, "full_checked_at": None, "daily_checked_at": None}
    assert select_players(players, [fixture], {10: fixture}, checks, [], NOW)[0] == set()


def test_parallel_collection_fails_as_a_unit_and_names_the_failed_player():
    from scripts.history_ingestion import fetch_histories
    def fetch(url):
        if '/2/' in url:
            raise requests.Timeout('timed out')
        return {'history':[]}
    with pytest.raises(RuntimeError,match='player_id=2'):
        fetch_histories([1,2,3], '2026-27', 'run', NOW, fetch)
