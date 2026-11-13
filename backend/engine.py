"""Pure squad validation, independent replacements, and constrained optimization."""

from collections import Counter
from decimal import Decimal, ROUND_HALF_UP
from time import monotonic

from ortools.sat.python import cp_model

from .models import DomainError, OptimizeRequest, Pick, Player, QUOTAS


def score_units(player: Player) -> int:
    return int((Decimal(str(player.score or 0)) * 1000000).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def validate_squad(squad: list[Pick], players: dict[int, Player]) -> None:
    if len(squad) != 15 or len({p.player_id for p in squad}) != 15:
        raise DomainError("A squad must contain exactly 15 different players.")
    if any(p.player_id not in players for p in squad):
        raise DomainError("A squad player is missing from the current catalog. Please edit your squad.")
    if Counter(players[p.player_id].position for p in squad) != Counter(QUOTAS):
        raise DomainError("Select 2 goalkeepers, 5 defenders, 5 midfielders, and 3 forwards.")
    if max(Counter(players[p.player_id].team_id for p in squad).values()) > 3:
        raise DomainError("A squad cannot include more than 3 players from one club.")
    if any(p.selling_price > players[p.player_id].price for p in squad):
        raise DomainError("A selling price cannot exceed the player's current market price.")


def replacements(squad: list[Pick], players: dict[int, Player]):
    validate_squad(squad, players)
    owned = {p.player_id for p in squad}
    clubs = Counter(players[p.player_id].team_id for p in squad)
    rows = []
    for pick in squad:
        current = players[pick.player_id]
        candidates = []
        if current.score is not None:
            for candidate in players.values():
                if (candidate.id in owned or candidate.position != current.position
                        or candidate.score is None or candidate.score <= current.score
                        or candidate.price >= pick.selling_price):
                    continue
                club_count = clubs[candidate.team_id] - int(current.team_id == candidate.team_id)
                if club_count >= 3:
                    continue
                candidates.append({
                    "player": candidate,
                    "viability_gain": candidate.score - current.score,
                    "savings": pick.selling_price - candidate.price,
                })
        candidates.sort(key=lambda c: (-c["viability_gain"], -c["savings"], c["player"].id))
        rows.append({"player_id": current.id, "unscored": current.score is None, "candidates": candidates})
    return rows


def optimize(request: OptimizeRequest, players: dict[int, Player], time_limit: float = 10.0):
    if request.mode == "transfers":
        validate_squad(request.squad, players)
    elif request.squad:
        validate_squad(request.squad, players)
    owned = {p.player_id: p for p in request.squad}
    transfer_mode = request.mode == "transfers"
    pool = sorted((p for p in players.values() if p.score is not None or (transfer_mode and p.id in owned)), key=lambda p: p.id)
    model = cp_model.CpModel()
    selected = {p.id: model.new_bool_var(f"player_{p.id}") for p in pool}
    for position, count in QUOTAS.items():
        model.add(sum(selected[p.id] for p in pool if p.position == position) == count)
    for team in {p.team_id for p in pool}:
        model.add(sum(selected[p.id] for p in pool if p.team_id == team) <= 3)

    available = request.bank + sum(p.selling_price for p in owned.values()) if transfer_mode else request.budget
    effective_prices = {p.id: owned[p.id].selling_price if transfer_mode and p.id in owned else p.price for p in pool}
    spend = sum(effective_prices[p.id] * selected[p.id] for p in pool)
    model.add(spend <= available)
    transfers = sum(selected[p.id] for p in pool if p.id not in owned) if transfer_mode else 0
    if transfer_mode:
        model.add(transfers <= request.max_transfers)
        for p in pool:
            if p.score is None:
                model.add(selected[p.id] == 1)

    # Exact lexicographic objective: score, fewer transfers, then money remaining.
    # Spend is bounded by available, so a higher-priority unit always dominates.
    money_weight = available + 1
    score_weight = 16 * money_weight
    total_score = sum(score_units(p) * selected[p.id] for p in pool)
    model.maximize(total_score * score_weight - transfers * money_weight - spend)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = 1
    started = monotonic()
    status = solver.solve(model)
    status_name = solver.status_name(status)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"status": status_name, "players": [], "message": (
            "No squad satisfies this budget and these constraints." if status == cp_model.INFEASIBLE
            else "The solver could not find a squad within the time limit. Try again."
        ), "elapsed_seconds": monotonic() - started}

    result = [p for p in pool if solver.value(selected[p.id])]
    result_ids = {p.id for p in result}
    incoming = [p for p in result if p.id not in owned]
    outgoing = [players[p] for p in owned if p not in result_ids]
    purchases = sum(p.price for p in incoming) if transfer_mode else sum(p.price for p in result)
    sale_proceeds = sum(owned[p.id].selling_price for p in outgoing) if transfer_mode else 0
    baseline = sum(players[p].score or 0 for p in owned)
    result_score = sum(p.score or 0 for p in result)
    return {
        "status": status_name,
        "players": sorted(result, key=lambda p: (p.position, -float(p.score or 0), p.id)),
        "incoming": incoming, "outgoing": outgoing,
        "transfers": len(incoming) if transfer_mode else None,
        "purchase_cost": purchases, "sale_proceeds": sale_proceeds,
        "remaining_budget": request.bank + sale_proceeds - purchases if transfer_mode else request.budget - purchases,
        "market_value": sum(p.price for p in result),
        "viability": result_score,
        "baseline_viability": baseline if owned else None,
        "viability_gain": result_score - baseline if owned else None,
        "fixed_unscored": [p.id for p in result if p.score is None],
        "estimated_selling_prices": transfer_mode and any(p.estimated for p in owned.values()),
        "elapsed_seconds": monotonic() - started,
    }
