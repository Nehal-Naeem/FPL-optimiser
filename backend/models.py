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


class Player(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    team_id: int
    club: str
    position: int = Field(ge=1, le=4)
    price: int = Field(gt=0)
    score: Optional[float] = Field(default=None, ge=0, le=1)
    form: Optional[float] = None
    form_percentile: Optional[float] = None
    fixture_ease: Optional[float] = None
    normalized_fixture_ease: Optional[float] = None
    points_per_gw: Optional[float] = None
    points_percentile: Optional[float] = None
    status: str = "a"
    news: str = ""
    chance_of_playing: Optional[int] = None
    upcoming_fixtures: tuple[UpcomingFixture, ...] = ()


class Dataset(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: str
    players: tuple[Player, ...]
    gameweeks: tuple[dict, ...] = Field(exclude=True)
    scores_updated_at: datetime
    catalog_updated_at: datetime
    fixtures_updated_at: Optional[datetime] = None

    def metadata(self):
        return {
            "dataset_version": self.version,
            "scores_updated_at": self.scores_updated_at,
            "catalog_updated_at": self.catalog_updated_at,
            "fixtures_updated_at": self.fixtures_updated_at,
            "stale": (datetime.now(timezone.utc) - self.scores_updated_at).total_seconds() > 43200,
        }


class Pick(BaseModel):
    player_id: int = Field(gt=0)
    selling_price: int = Field(ge=0, le=10000)
    estimated: bool = True


class SquadRequest(BaseModel):
    squad: list[Pick] = Field(min_length=15, max_length=15)
    bank: int = Field(default=0, ge=0, le=10000)
    dataset_version: str
    source_gameweek: Optional[int] = Field(default=None, ge=1, le=38)


class OptimizeRequest(BaseModel):
    mode: Literal["ideal", "transfers"]
    squad: list[Pick] = Field(default_factory=list, max_length=15)
    bank: int = Field(default=0, ge=0, le=10000)
    budget: int = Field(default=1000, gt=0, le=10000)
    max_transfers: int = Field(default=1, ge=0, le=15)
    dataset_version: str
    source_gameweek: Optional[int] = Field(default=None, ge=1, le=38)


class DomainError(Exception):
    def __init__(self, message: str, status_code: int = 422):
        self.message = message
        self.status_code = status_code
        super().__init__(message)
