from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from backend.app import app, get_dataset
from backend.data import upcoming_by_team
from backend.models import UpcomingFixture

START = datetime(2026, 11, 14, 15, tzinfo=timezone.utc)


def row(id, **updates):
    return {"id": id, "team_id": 1, "opponent_id": id + 10, "opponent": f"Opponent {id}",
            "opponent_short": f"O{id}", "home_away": "H", "event": 13,
            "kickoff_time": START + timedelta(days=id), "difficulty": 2,
            "started": False, "finished": False, **updates}


def test_next_five_sorted_deduplicated_and_no_started_matches():
    rows = [row(i) for i in (7, 3, 2, 6, 1, 5, 4)]
    rows += [row(1), row(8, started=True), row(9, finished=True)]
    assert [f.id for f in upcoming_by_team(rows)[1]] == [1, 2, 3, 4, 5]
    assert upcoming_by_team([row(1, started=True), row(2, finished=True)]) == {}


def test_double_gameweek_undated_and_stable_order():
    rows = [row(3, kickoff_time=None, event=None), row(2, kickoff_time=START), row(1, kickoff_time=START)]
    fixtures = upcoming_by_team(rows)[1]
    assert [f.id for f in fixtures] == [1, 2, 3]
    assert [f.gameweek for f in fixtures] == [13, 13, None]
    assert fixtures[2].kickoff_time is None
    assert len(fixtures) == 3


def test_home_away_difficulty_and_fallback_names():
    fixtures = upcoming_by_team([row(1, difficulty=2), row(1, team_id=11, opponent_id=1,
                                      opponent=None, opponent_short=None, home_away="A", difficulty=5)])
    assert fixtures[1][0].home_away == "H" and fixtures[1][0].difficulty == 2
    assert fixtures[11][0].home_away == "A" and fixtures[11][0].difficulty == 5
    assert fixtures[11][0].opponent == "1"



def test_fixtures_survive_all_player_responses(dataset, squad):
    fixture = UpcomingFixture(id=1, opponent_id=2, opponent="Test club", opponent_short="TST",
                              home_away="A", gameweek=13, kickoff_time=START, difficulty=4)
    players = [p.model_copy(update={"upcoming_fixtures": (fixture,)}) for p in dataset.players]
    from backend.tests.test_points_engine import project
    candidate = project(players[2].model_copy(update={"id":16,"team_id":6,"price":40}),(8,)*5)
    updated = dataset.model_copy(update={"players": tuple(players + [candidate]), "fixtures_updated_at": START})
    app.dependency_overrides[get_dataset] = lambda: updated
    try:
        with TestClient(app) as client:
            catalog = client.get('/api/players').json()
            assert catalog['fixtures_updated_at'] is not None
            assert 'score' not in catalog['players'][0]
            assert catalog['players'][0]['upcoming_fixtures'][0]['opponent_short'] == 'TST'
            body = {"contract_version":2,"squad": [p.model_dump() for p in squad], "dataset_version": dataset.version}
            rows = client.post('/api/replacements', json=body).json()['replacements']
            assert rows[2]['upgrades'][0]['player']['upcoming_fixtures'][0]['difficulty'] == 4
            result = client.post('/api/optimize', json={**body, "mode": "transfers"}).json()
            assert len(result['players']) == 15
            assert all(p['upcoming_fixtures'][0]['id'] == 1 for p in result['players'])
    finally:
        app.dependency_overrides.clear()
