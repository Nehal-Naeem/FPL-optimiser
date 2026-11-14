from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
import pytest

from backend.data import BigQueryRepository
from backend.diagnostics import squad_diagnostics

NOW = datetime.now(timezone.utc)


def published_row(player):
    return {**player.model_dump(), "publication_id": "publication-1", "projections_updated_at": NOW,
            "catalog_updated_at": NOW, "fixtures_updated_at": NOW, "last_checked_at": NOW,
            "season": "2026-27"}


def test_published_mode_uses_one_query_no_raw_or_metadata_reads(players, monkeypatch):
    repo = BigQueryRepository()
    repo.client = Mock()
    rows = [published_row(p) for p in players.values()]
    query = Mock(return_value=rows)
    monkeypatch.setattr(repo, "_query", query)
    result = repo._load()
    assert result.version == "points-v2:publication-1" and result.published
    assert len(result.players) == 15
    query.assert_called_once()
    assert ".mart_recommendation_snapshot`" in query.call_args.args[0]
    repo.client.get_table.assert_not_called()


@pytest.mark.parametrize("problem", ["duplicate", "mixed_version", "mixed_check"])
def test_invalid_snapshot_refused(players, monkeypatch, problem):
    repo = BigQueryRepository()
    rows = [published_row(p) for p in players.values()]
    if problem == "duplicate": rows.append(rows[0])
    elif problem == "mixed_version": rows[1]["publication_id"] = "new"
    else: rows[1]["last_checked_at"] = NOW - timedelta(hours=1)
    monkeypatch.setattr(repo, "_query", Mock(return_value=rows))
    with pytest.raises(ValueError): repo._load_published()


def test_successful_check_keeps_unchanged_scores_fresh(dataset):
    snapshot = dataset.model_copy(update={"projections_updated_at": NOW-timedelta(days=2), "last_checked_at": NOW})
    assert not snapshot.metadata()["stale"]


def test_diagnostics_are_descriptive_and_do_not_change_projections(players):
    chosen = list(players.values())
    before = [p.projections for p in chosen]
    result = squad_diagnostics(chosen, 50)
    assert sum(r["market_value"] for r in result["budget_by_position"]) == sum(p.price for p in chosen)
    assert "unused_budget" in {w["code"] for w in result["warnings"]}
    assert "defensive_concentration" in {w["code"] for w in result["warnings"]}
    assert [p.projections for p in chosen] == before
    assert not squad_diagnostics(chosen, 49)["low_minutes_player_ids"]
