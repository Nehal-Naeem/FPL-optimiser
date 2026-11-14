"""Shared API contracts. All monetary amounts are integer tenths of a million."""

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

QUOTAS = {1: 2, 2: 5, 3: 5, 4: 3}


class UpcomingFixture(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    opponent_id: int
    opponent: str
    opponent_short: str
    home_away: Literal["H", "A"]
    gameweek: Optional[int] = None
    kickoff_time: Optional[datetime] = None
    difficulty: Optional[int] = Field(default=None, ge=1, le=5)


class RecentForm(BaseModel):
    cutoff_gameweek: int
    window_start_gameweek: int
    window_gameweeks: int = Field(ge=1, le=5)
    covered_gameweeks: int = Field(ge=0, le=5)
    complete: bool
    history_checked_at: Optional[datetime] = None
    points: Optional[int] = None
    minutes: Optional[int] = None
    starts: Optional[int] = None
    points_per_gw: Optional[float] = None
    minutes_per_gw: Optional[float] = None
    points_per_90: Optional[float] = None
    xg_per_90: Optional[float] = None
    xa_per_90: Optional[float] = None
    short_window_gameweeks: int
    short_points_per_gw: Optional[float] = None
    short_minutes_per_gw: Optional[float] = None


class PointComponents(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    appearance_points: float = 0
    goal_points: float = 0
    assist_points: float = 0
    clean_sheet_points: float = 0
    save_points: float = 0
    penalty_save_points: float = 0
    defensive_points: float = 0
    bonus_points: float = 0
    deduction_points: float = 0


class FixtureProjection(PointComponents):
    fixture_id: int
    opponent_id: int
    opponent: str
    home_away: Literal["H", "A"]
    kickoff_time: Optional[datetime] = None
    difficulty: Optional[int] = None
    expected_points: float
    expected_minutes: float = Field(ge=0, le=90)
    play_probability: float = Field(ge=0, le=1)
    sixty_probability: float = Field(ge=0, le=1)
    attacking_factor: float = 1
    opponent_goals: float = 1.35
    xg_per_minute: float = 0
    xa_per_minute: float = 0
    saves_per_minute: float = 0
    penalties_per_minute: float = 0
    defensive_per_minute: float = 0
    bonus_per_minute: float = 0
    deductions_per_minute: float = 0


class GameweekProjection(PointComponents):
    gameweek: int = Field(ge=1, le=38)
    deadline_time: datetime
    as_of: datetime
    fixture_count: int = Field(ge=0)
    expected_points: float
    expected_minutes: float = Field(ge=0)
    play_probability: float = Field(ge=0, le=1)
    sixty_probability: float = Field(ge=0, le=1)
    fixtures: tuple[FixtureProjection, ...] = ()
    availability_note: str = "Historical role assumed"
    history_fixtures: int = 0
    history_minutes: int = 0
    data_support: str = "limited_minutes"
    projection_method: str = "experimental-points-v1"
    unassigned_fixtures: bool = False
    minutes_overridden: bool = False


class Player(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    team_id: int
    club: str
    position: int = Field(ge=1, le=4)
    price: int = Field(gt=0)
    status: str = "a"
    news: str = ""
    chance_of_playing: Optional[int] = None
    upcoming_fixtures: tuple[UpcomingFixture, ...] = ()
    recent: Optional[RecentForm] = None
    projections: tuple[GameweekProjection, ...] = ()


class Dataset(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: str
    players: tuple[Player, ...]
    gameweeks: tuple[dict, ...] = Field(default=(), exclude=True)
    projections_updated_at: datetime
    catalog_updated_at: datetime
    fixtures_updated_at: Optional[datetime] = None
    last_checked_at: Optional[datetime] = None
    season: Optional[str] = None
    published: bool = False

    def metadata(self):
        horizon = next((p.projections for p in self.players if p.projections), ())
        return {
            "dataset_version": self.version,
            "contract_version": 2,
            "projections_updated_at": self.projections_updated_at,
            "catalog_updated_at": self.catalog_updated_at,
            "fixtures_updated_at": self.fixtures_updated_at,
            "last_checked_at": self.last_checked_at,
            "season": self.season,
            "published": self.published,
            "projection_gameweeks": [p.gameweek for p in horizon],
            "projection_method": horizon[0].projection_method if horizon else None,
            "projection_stale": bool(horizon and horizon[0].deadline_time <= datetime.now(timezone.utc)),
            "stale": (datetime.now(timezone.utc) - (self.last_checked_at or self.projections_updated_at)).total_seconds() > 43200,
        }


class Pick(BaseModel):
    player_id: int = Field(gt=0)
    selling_price: int = Field(ge=0, le=10000)
    estimated: bool = True


class MinutesOverride(BaseModel):
    player_id: int = Field(gt=0)
    gameweek: int = Field(ge=1, le=38)
    minutes_per_fixture: int = Field(ge=0, le=90)


class SquadRequest(BaseModel):
    contract_version: Literal[2]
    squad: list[Pick] = Field(min_length=15, max_length=15)
    bank: int = Field(default=0, ge=0, le=10000)
    dataset_version: str
    source_gameweek: Optional[int] = Field(default=None, ge=1, le=38)
    minutes_overrides: list[MinutesOverride] = Field(default_factory=list, max_length=200)


class OptimizeRequest(BaseModel):
    contract_version: Literal[2]
    mode: Literal["ideal", "transfers"]
    squad: list[Pick] = Field(default_factory=list, max_length=15)
    bank: int = Field(default=0, ge=0, le=10000)
    budget: int = Field(default=1000, gt=0, le=10000)
    max_transfers: int = Field(default=1, ge=0, le=15)
    dataset_version: str
    source_gameweek: Optional[int] = Field(default=None, ge=1, le=38)
    objective: Literal["five_gw_points"] = "five_gw_points"
    minutes_overrides: list[MinutesOverride] = Field(default_factory=list, max_length=200)


class DomainError(Exception):
    def __init__(self, message: str, status_code: int = 422):
        self.message = message
        self.status_code = status_code
        super().__init__(message)
