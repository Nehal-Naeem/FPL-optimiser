"""Lazy cloud access, five-minute snapshot cache, and public FPL imports."""

import logging
import math
import os
import re
from datetime import datetime, timezone
from threading import Lock
from time import monotonic

import requests
from google.cloud import bigquery

from .models import Dataset, DomainError, Pick, Player, UpcomingFixture

logger = logging.getLogger(__name__)


def identifier(name: str) -> str:
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", name):
        raise ValueError("Invalid BigQuery project or dataset identifier")
    return name


def optional_number(value):
    return float(value) if value is not None and math.isfinite(float(value)) else None


def upcoming_by_team(rows):
    """Next five matches per club, with undated matches after scheduled matches."""
    grouped = {}
    seen = set()
    for row in rows:
        if row["started"] or row["finished"]:
            continue
        key = (row["team_id"], row["id"])
        if key in seen:
            continue
        seen.add(key)
        fixture = UpcomingFixture(
            id=row["id"], opponent_id=row["opponent_id"],
            opponent=row["opponent"] or str(row["opponent_id"]),
            opponent_short=row["opponent_short"] or str(row["opponent_id"]),
            home_away=row["home_away"], gameweek=row["event"],
            kickoff_time=row["kickoff_time"], difficulty=row["difficulty"],
        )
        grouped.setdefault(row["team_id"], []).append(fixture)
    last = datetime.max.replace(tzinfo=timezone.utc)
    return {team: tuple(sorted(fixtures, key=lambda f: (f.kickoff_time is None, f.kickoff_time or last, f.id))[:5])
            for team, fixtures in grouped.items()}


class BigQueryRepository:
    def __init__(self):
        self.project = identifier(os.getenv("GOOGLE_CLOUD_PROJECT", "fpl-optimizer-511321"))
        self.raw = identifier(os.getenv("FPL_RAW_DATASET", "fpl_raw"))
        self.analytics = identifier(os.getenv("FPL_ANALYTICS_DATASET", "fpl_analytics"))
        self.client = None
        self._snapshot = None
        self._expires = 0.0
        self._lock = Lock()

    def get(self) -> Dataset:
        with self._lock:
            if self._snapshot is not None and monotonic() < self._expires:
                return self._snapshot
            try:
                snapshot = self._load()
            except Exception as exc:
                logger.exception("Failed to load BigQuery player dataset")
                raise DomainError("Player data is unavailable. Check BigQuery access and try again.", 503) from exc
            self._snapshot = snapshot
            self._expires = monotonic() + 300
            return snapshot

    def _query(self, sql):
        return self.client.query(sql, location=os.getenv("BIGQUERY_LOCATION", "US"),
                                 job_config=bigquery.QueryJobConfig(maximum_bytes_billed=100_000_000),
                                 timeout=15).result(timeout=30)

    def _load(self) -> Dataset:
        if self.client is None:
            self.client = bigquery.Client(project=self.project)
        return self._load_published()

    def _load_published(self) -> Dataset:
        rows = [dict(r) for r in self._query(
            f"SELECT * FROM `{self.project}.{self.analytics}.mart_recommendation_snapshot`")]
        if not rows or len({r["id"] for r in rows}) != len(rows):
            raise ValueError("Empty or duplicated published catalog")
        time_field = "projections_updated_at" if "projections_updated_at" in rows[0] else "scores_updated_at"
        metadata = ("publication_id", time_field, "catalog_updated_at", "fixtures_updated_at",
                    "last_checked_at", "season")
        if any(any(row[k] != rows[0][k] for k in metadata) for row in rows):
            raise ValueError("Inconsistent publication metadata")
        players = tuple(Player.model_validate({k: v for k, v in r.items() if k in Player.model_fields}) for r in rows)
        first = rows[0]
        return Dataset(version="points-v2:"+first["publication_id"], players=players, published=True,
                       projections_updated_at=first[time_field], catalog_updated_at=first["catalog_updated_at"],
                       fixtures_updated_at=first["fixtures_updated_at"], last_checked_at=first["last_checked_at"],
                       season=first["season"])


class FPLClient:
    base_url = "https://fantasy.premierleague.com/api"

    def fetch(self, path):
        try:
            response = requests.get(f"{self.base_url}/{path}/", timeout=(5, 15))
            if response.status_code == 404:
                raise DomainError("Team or published gameweek squad not found.", 404)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Unexpected FPL response")
            return data
        except (requests.RequestException, ValueError) as exc:
            raise DomainError("FPL is unavailable or rate limiting requests. Please try again shortly.", 502) from exc

    def import_team(self, team_id: int, dataset: Dataset):
        entry = self.fetch(f"entry/{team_id}")
        # Public picks are deadline snapshots. Never call authenticated my-team endpoints.
        gameweek = entry.get("current_event")
        if not gameweek:
            raise DomainError("This team has no published gameweek squad yet.", 404)
        payload = self.fetch(f"entry/{team_id}/event/{int(gameweek)}/picks")
        catalog = {p.id: p for p in dataset.players}
        try:
            picks = payload["picks"]
            if len(picks) != 15 or len({p["element"] for p in picks}) != 15:
                raise ValueError("Incomplete squad")
            squad = [Pick(player_id=p["element"], selling_price=catalog[p["element"]].price) for p in picks]
            bank = int(payload["entry_history"]["bank"])
            if bank < 0:
                raise ValueError("Invalid bank")
        except KeyError as exc:
            raise DomainError("This published squad is incomplete or contains a player missing from the catalog.", 502) from exc
        except (TypeError, ValueError) as exc:
            raise DomainError("FPL returned an incomplete squad. Please try again.", 502) from exc
        return {"team_id": team_id, "name": entry.get("name", "Your squad"),
                "source_gameweek": int(gameweek), "bank": bank, "squad": squad,
                "imported_at": datetime.now(timezone.utc),
                "notice": "Published deadline snapshot. Correct recent transfers, bank, and estimated selling prices before optimizing."}
