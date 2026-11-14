"""Deterministic browser-test server. Never used by the production entrypoint."""

from datetime import datetime, timedelta, timezone

from backend.app import app, fpl, get_dataset
from backend.models import Dataset, DomainError, Pick, Player, RecentForm, UpcomingFixture, FixtureProjection, GameweekProjection


def fixture_dataset():
    positions = [1] * 2 + [2] * 5 + [3] * 5 + [4] * 3
    players = [Player(id=i, name=f"Player {i}", team_id=(i - 1) // 3 + 1,
                      club=f"C{(i - 1) // 3 + 1}", position=pos, price=50,
)
               for i, pos in enumerate(positions, 1)]
    players.extend([
        Player(id=16, name="Value Defender", team_id=6, club="C6", position=2, price=45),
        Player(id=17, name="Premium Midfielder", team_id=7, club="C7", position=3, price=70, status="i", news="Test injury flag"),
        Player(id=18, name="Budget Midfielder", team_id=8, club="C8", position=3, price=30),
    ])
    fixtures = tuple(UpcomingFixture(id=i, opponent_id=i + 10, opponent=f"Opponent {i}",
                     opponent_short=f"O{i}", home_away="H" if i % 2 else "A", gameweek=13 + i // 2,
                     kickoff_time=datetime(2026, 11, 14 + i, 15, tzinfo=timezone.utc) if i < 5 else None,
                     difficulty=i) for i in range(1, 6))
    players = [p.model_copy(update={"upcoming_fixtures": fixtures if p.id != 15 else ()}) for p in players]
    recent = RecentForm(cutoff_gameweek=10, window_start_gameweek=6, window_gameweeks=5,
        covered_gameweeks=5, complete=True, history_checked_at=datetime.now(timezone.utc),
        points=14, minutes=240, starts=3, points_per_gw=2.8, minutes_per_gw=48,
        points_per_90=5.25, xg_per_90=0.15, xa_per_90=None, short_window_gameweeks=3,
        short_points_per_gw=3, short_minutes_per_gw=60)
    players = [p.model_copy(update={"recent": recent}) if p.id==1 else
               p.model_copy(update={"recent": recent.model_copy(update={"minutes": 0, "starts": 0,
                   "points": 0, "points_per_90": None, "xg_per_90": None, "xa_per_90": None, "minutes_per_gw": 0})}) if p.id==2 else
               p.model_copy(update={"recent": recent.model_copy(update={"complete": False, "covered_gameweeks": 4,
                   "points": None, "minutes": None, "starts": None})}) if p.id==3 else p for p in players]
    projected = []
    for p in players:
        weeks = []
        for i in range(5):
            xp = 8 if p.id==16 else 3 + (p.id % 5) / 2 + (1 if i % 2 == p.id % 2 else 0)
            fixture = FixtureProjection(fixture_id=100+i, opponent_id=20, opponent='Opponent', home_away='H',
                expected_points=xp, expected_minutes=90, play_probability=1, sixty_probability=1,
                appearance_points=2, goal_points=xp-2, xg_per_minute=0.005)
            weeks.append(GameweekProjection(gameweek=11+i, deadline_time=datetime(2099,1,1,tzinfo=timezone.utc)+timedelta(days=i*7),
                as_of=datetime.now(timezone.utc),fixture_count=1,expected_points=xp,expected_minutes=90,
                play_probability=1,sixty_probability=1,appearance_points=2,goal_points=xp-2,
                fixtures=(fixture,),history_fixtures=10,history_minutes=900,data_support='observed_history'))
        projected.append(p.model_copy(update={'projections':tuple(weeks)}))
    players = projected
    return Dataset(version="browser-test-v1", players=tuple(players), gameweeks=(),
                   projections_updated_at=datetime.now(timezone.utc), catalog_updated_at=datetime.now(timezone.utc),
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
