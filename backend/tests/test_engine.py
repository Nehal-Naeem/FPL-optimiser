from collections import Counter
from itertools import combinations

import pytest

from backend.engine import optimize, replacements, score_units, validate_squad
from backend.models import DomainError, OptimizeRequest, Pick, Player, QUOTAS


def extra(id=16, position=2, price=49, score=0.6, team_id=6, status="a"):
    return Player(id=id, name=f"Alternative {id}", team_id=team_id, club=f"Club {team_id}",
                  position=position, price=price, score=score, status=status)


def request(squad, **kwargs):
    return OptimizeRequest(mode="transfers", squad=squad, dataset_version="test", **kwargs)


def test_coupled_transfers_beat_independent_swaps(players, squad):
    # No cheaper-and-better individual move exists; a downgrade funds a big upgrade.
    players[16] = extra(price=30, score=0.4)
    players[17] = extra(id=17, position=3, price=70, score=0.9, team_id=7)
    assert not any(row["candidates"] for row in replacements(squad, players))
    result = optimize(request(squad, max_transfers=2), players)
    assert result["status"] == "OPTIMAL"
    assert {p.id for p in result["incoming"]} == {16, 17}
    assert result["remaining_budget"] == 0
    assert result["viability_gain"] == pytest.approx(0.3)


@pytest.mark.parametrize("mode", ["ideal", "transfers"])
def test_matches_exhaustive_search(players, squad, mode):
    players.update({16: extra(price=30, score=0.4),
                    17: extra(id=17, position=3, price=70, score=0.9, team_id=7),
                    18: extra(id=18, position=4, price=48, score=0.6, team_id=8)})
    req = OptimizeRequest(mode=mode, squad=squad, dataset_version="test", budget=750, max_transfers=2)
    owned = {p.player_id for p in squad}
    def objective(chosen):
        new = len({p.id for p in chosen} - owned) if mode == "transfers" else 0
        return sum(score_units(p) for p in chosen), -new, -sum(p.price for p in chosen)
    valid = []
    for chosen in combinations(players.values(), 15):
        if Counter(p.position for p in chosen) != Counter(QUOTAS):
            continue
        if max(Counter(p.team_id for p in chosen).values()) > 3 or sum(p.price for p in chosen) > 750:
            continue
        if mode == "transfers" and len({p.id for p in chosen} - owned) > 2:
            continue
        valid.append(chosen)
    result = optimize(req, players)
    assert objective(result["players"]) == max(map(objective, valid))


def test_sale_price_and_exact_bank_boundary(players, squad):
    squad[2] = Pick(player_id=3, selling_price=45)
    players[16] = extra(price=50, score=0.9)
    # Fix every other defender's score higher, so selling Player 3 is the only gain.
    for i in range(4, 8):
        players[i] = players[i].model_copy(update={"score": 1.0})
    assert optimize(request(squad, bank=4), players)["transfers"] == 0
    result = optimize(request(squad, bank=5), players)
    assert result["transfers"] == 1
    assert result["sale_proceeds"] == 45
    assert result["remaining_budget"] == 0


def test_zero_transfers_and_tie_prefer_fewer_moves(players, squad):
    players[16] = extra(score=0.5, price=30)
    assert optimize(request(squad, max_transfers=15), players)["transfers"] == 0
    players[16] = extra(score=1.0)
    assert optimize(request(squad, max_transfers=0), players)["incoming"] == []


def test_full_squad_tie_prefers_money(players):
    players[16] = extra(score=0.5, price=30)
    result = optimize(OptimizeRequest(mode="ideal", budget=750, dataset_version="test"), players)
    assert 16 in {p.id for p in result["players"]}
    assert result["remaining_budget"] == 20


def test_infeasible_budget_and_timeout(players):
    req = OptimizeRequest(mode="ideal", budget=1, dataset_version="test")
    assert optimize(req, players)["status"] == "INFEASIBLE"
    assert optimize(req, players, time_limit=0)["status"] == "UNKNOWN"


def test_replacements_strict_sale_price_club_and_owned_rules(players, squad):
    players[16] = extra(price=49, score=0.6, status="i")
    players[17] = extra(id=17, price=50, score=0.9)
    players[18] = extra(id=18, price=40, score=0.5)
    players[19] = extra(id=19, price=40, score=0.9, team_id=1)
    players[4] = players[4].model_copy(update={"price": 40, "score": 0.9})
    squad[3] = Pick(player_id=4, selling_price=40)
    row = next(r for r in replacements(squad, players) if r["player_id"] == 5)
    assert [c["player"].id for c in row["candidates"]] == [16]
    # A player from the outgoing player's club is allowed if the final count stays 3.
    row = next(r for r in replacements(squad, players) if r["player_id"] == 3)
    assert {c["player"].id for c in row["candidates"]} == {16, 19}
    squad[4] = Pick(player_id=5, selling_price=49)
    assert not next(r for r in replacements(squad, players) if r["player_id"] == 5)["candidates"]


def test_unscored_retained_and_unavailable_allowed(players, squad):
    players[3] = players[3].model_copy(update={"score": None})
    players[16] = extra(score=0.99, status="i")
    rows = replacements(squad, players)
    assert rows[2]["unscored"] and not rows[2]["candidates"]
    result = optimize(request(squad), players)
    assert result["fixed_unscored"] == [3]
    assert 16 in {p.id for p in result["incoming"]}


@pytest.mark.parametrize("problem", ["duplicate", "club", "position", "unknown", "sale_price"])
def test_invalid_squads(players, squad, problem):
    if problem == "duplicate":
        squad[0] = squad[1]
    elif problem == "club":
        players[15] = players[15].model_copy(update={"team_id": 1})
    elif problem == "position":
        players[15] = players[15].model_copy(update={"position": 2})
    elif problem == "unknown":
        players.pop(15)
    else:
        squad[0] = Pick(player_id=1, selling_price=51)
    with pytest.raises(DomainError):
        validate_squad(squad, players)
