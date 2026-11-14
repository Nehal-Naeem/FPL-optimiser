from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
import requests
from fastapi.testclient import TestClient

from backend.app import app, fpl, get_dataset
from backend.data import BigQueryRepository, FPLClient
from backend.models import DomainError


@pytest.fixture
def client(dataset):
    app.dependency_overrides[get_dataset] = lambda: dataset
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def body(squad):
    return {"contract_version":2,"dataset_version": "test-v1", "squad": [p.model_dump() for p in squad], "bank": 0}


def test_players_and_version_pinning(client, squad):
    response = client.get("/api/players")
    assert response.status_code == 200
    assert len(response.json()["players"]) == 15
    assert not response.json()["stale"]
    payload = body(squad)
    assert client.post("/api/replacements", json=payload).status_code == 200
    payload["dataset_version"] = "expired"
    assert client.post("/api/replacements", json=payload).status_code == 409
    assert client.post("/api/optimize", json={**payload, "mode": "transfers"}).status_code == 409


def test_api_validation(client, squad):
    assert client.get("/api/teams/0").status_code == 422
    assert client.get("/api/not-a-route").status_code == 404
    payload = {**body(squad), "mode": "transfers", "max_transfers": -1}
    assert client.post("/api/optimize", json=payload).status_code == 422
    assert client.post("/api/optimize", json={**payload, "max_transfers": 1, "bank": 0.5}).status_code == 422
    result = client.post("/api/optimize", json={**payload, "max_transfers": 0})
    assert result.status_code == 200
    assert result.json()["transfers"] == 0


def test_import_uses_latest_entry_event_not_hardcoded_gw(client, monkeypatch):
    fetch = Mock(side_effect=[{"name": "Test team", "current_event": 2},
                              {"picks": [{"element": i} for i in range(1, 16)], "entry_history": {"bank": 7}}])
    monkeypatch.setattr(fpl, "fetch", fetch)
    result = client.get("/api/teams/123").json()
    assert result["source_gameweek"] == 2
    assert result["bank"] == 7
    assert all(p["estimated"] for p in result["squad"])
    fetch.assert_called_with("entry/123/event/2/picks")


def test_import_before_first_deadline(client, monkeypatch):
    monkeypatch.setattr(fpl, "fetch", lambda _: {"current_event": None})
    assert client.get("/api/teams/123").status_code == 404


def test_stale_metadata(dataset):
    old = dataset.model_copy(update={"projections_updated_at": datetime.now(timezone.utc) - timedelta(hours=13)})
    assert old.metadata()["stale"]


def test_cache_pins_snapshot_and_surfaces_refresh_failure(dataset, monkeypatch):
    repo = BigQueryRepository()
    load = Mock(return_value=dataset)
    monkeypatch.setattr(repo, "_load", load)
    assert repo.get() is repo.get()
    load.assert_called_once()
    repo._expires = 0
    load.side_effect = RuntimeError("Unavailable")
    with pytest.raises(DomainError, match="Player data is unavailable"):
        repo.get()


@pytest.mark.parametrize("failure", ["404", "429", "timeout", "bad_json"])
def test_fpl_upstream_errors(monkeypatch, failure):
    response = Mock(status_code=404 if failure == "404" else 200)
    if failure == "429":
        response.raise_for_status.side_effect = requests.HTTPError("429")
    if failure == "bad_json":
        response.json.side_effect = ValueError("Bad JSON")
    get = Mock(return_value=response)
    if failure == "timeout":
        get.side_effect = requests.Timeout()
    monkeypatch.setattr("backend.data.requests.get", get)
    with pytest.raises(DomainError) as error:
        FPLClient().fetch("entry/123")
    assert error.value.status_code == (404 if failure == "404" else 502)


def test_incomplete_picks(dataset, monkeypatch):
    fpl = FPLClient()
    monkeypatch.setattr(fpl, "fetch", Mock(side_effect=[{"current_event": 2}, {"picks": []}]))
    with pytest.raises(DomainError, match="incomplete squad"):
        fpl.import_team(123, dataset)
