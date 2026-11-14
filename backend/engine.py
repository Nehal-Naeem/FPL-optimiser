"""Shared squad constraints and the points-only optimisation entrypoint."""
from collections import Counter
from .models import DomainError, QUOTAS, Pick, Player


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



def optimize(request, players, time_limit=10.0):
    from .points_engine import optimize_points
    return optimize_points(request, players, time_limit)


def replacements(request, players):
    from .replacement_engine import replacements_points
    return replacements_points(request, players)
