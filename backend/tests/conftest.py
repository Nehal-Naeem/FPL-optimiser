from datetime import datetime, timezone

import pytest

from backend.models import Dataset, Pick, Player


@pytest.fixture
def players():
    positions = [1] * 2 + [2] * 5 + [3] * 5 + [4] * 3
    from backend.models import GameweekProjection,FixtureProjection
    from datetime import timedelta
    weeks=[]
    for g in range(5):
        f=FixtureProjection(fixture_id=100+g,opponent_id=20,opponent='Test',home_away='H',expected_points=4,
            expected_minutes=90,play_probability=1,sixty_probability=1)
        weeks.append(GameweekProjection(gameweek=11+g,deadline_time=datetime(2099,1,1,tzinfo=timezone.utc)+timedelta(days=7*g),
            as_of=datetime.now(timezone.utc),fixture_count=1,expected_points=4,expected_minutes=90,
            play_probability=1,sixty_probability=1,fixtures=(f,),history_minutes=900,data_support='observed_history'))
    return {i: Player(id=i,name=f'Player {i}',team_id=(i-1)//3+1,club=f'Club {(i-1)//3+1}',position=pos,
                      price=50,projections=tuple(weeks)) for i,pos in enumerate(positions,1)}


@pytest.fixture
def squad():
    return [Pick(player_id=i, selling_price=50, estimated=False) for i in range(1, 16)]


@pytest.fixture
def dataset(players):
    return Dataset(version="test-v1", players=tuple(players.values()), gameweeks=({"id": 2, "is_current": True},),
                   projections_updated_at=datetime.now(timezone.utc), catalog_updated_at=datetime.now(timezone.utc))
