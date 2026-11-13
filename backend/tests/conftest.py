from datetime import datetime, timezone

import pytest

from backend.models import Dataset, Pick, Player


@pytest.fixture
def players():
    positions = [1] * 2 + [2] * 5 + [3] * 5 + [4] * 3
    return {i: Player(id=i, name=f"Player {i}", team_id=(i - 1) // 3 + 1,
                      club=f"Club {(i - 1) // 3 + 1}", position=pos, price=50, score=0.5,
                      form=3.0, form_percentile=0.5, normalized_fixture_ease=0.5,
                      points_percentile=0.5)
            for i, pos in enumerate(positions, 1)}


@pytest.fixture
def squad():
    return [Pick(player_id=i, selling_price=50, estimated=False) for i in range(1, 16)]


@pytest.fixture
def dataset(players):
    return Dataset(version="test-v1", players=tuple(players.values()), gameweeks=({"id": 2, "is_current": True},),
                   scores_updated_at=datetime.now(timezone.utc), catalog_updated_at=datetime.now(timezone.utc))
