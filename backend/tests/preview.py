"""Deterministic browser-test server. Never used by the production entrypoint."""

from datetime import datetime, timezone

from backend.app import app, fpl, get_dataset
from backend.models import Dataset, DomainError, Pick, Player, UpcomingFixture


def fixture_dataset():
    positions = [1] * 2 + [2] * 5 + [3] * 5 + [4] * 3
    players = [Player(id=i, name=f"Player {i}", team_id=(i - 1) // 3 + 1,
                      club=f"C{(i - 1) // 3 + 1}", position=pos, price=50, score=0.5,
                      form=3, form_percentile=0 if i == 1 else 0.5, fixture_ease=3, normalized_fixture_ease=0.5,
                      points_per_gw=4, points_percentile=0.87654 if i == 1 else 0.5)
               for i, pos in enumerate(positions, 1)]
    players.extend([
        Player(id=16, name="Value Defender", team_id=6, club="C6", position=2, price=45, score=0.8),
        Player(id=17, name="Premium Midfielder", team_id=7, club="C7", position=3, price=70, score=0.9, status="i", news="Test injury flag"),
        Player(id=18, name="Budget Midfielder", team_id=8, club="C8", position=3, price=30, score=0.4),
    ])
    fixtures = tuple(UpcomingFixture(id=i, opponent_id=i + 10, opponent=f"Opponent {i}",
                     opponent_short=f"O{i}", home_away="H" if i % 2 else "A", gameweek=13 + i // 2,
                     kickoff_time=datetime(2026, 11, 14 + i, 15, tzinfo=timezone.utc) if i < 5 else None,
                     difficulty=i) for i in range(1, 6))
    players = [p.model_copy(update={"upcoming_fixtures": fixtures if p.id != 15 else ()}) for p in players]
    return Dataset(version="browser-test-v1", players=tuple(players), gameweeks=(),
                   scores_updated_at=datetime.now(timezone.utc), catalog_updated_at=datetime.now(timezone.utc),
                   fixtures_updated_at=datetime.now(timezone.utc))


DATASET = fixture_dataset()
app.dependency_overrides[get_dataset] = lambda: DATASET


def import_fixture(team_id, dataset):
    if team_id == 404:
        raise DomainError("Team or published gameweek squad not found.", 404)
    if team_id == 503:
        raise DomainError("FPL is unavailable or rate limiting requests. Please try again shortly.", 502)
    return {"team_id": team_id, "name": "Test XI", "source_gameweek": 12, "bank": 0,
            "squad": [Pick(player_id=i, selling_price=50) for i in range(1, 16)],
            "notice": "Test data only. Published deadline snapshot; selling prices are estimates."}


fpl.import_team = import_fixture
