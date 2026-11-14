"""Descriptive squad diagnostics, independent of optimisation and expected points."""
from collections import Counter


def squad_diagnostics(players, remaining_budget):
    allocation = [{"position": position, "players": sum(p.position == position for p in players),
                   "market_value": sum(p.price for p in players if p.position == position)}
                  for position in (1, 2, 3, 4)]
    clubs = Counter(p.team_id for p in players)
    defence = Counter(p.team_id for p in players if p.position in (1, 2))
    warnings = []
    if remaining_budget >= 50:
        warnings.append({"code":"unused_budget","message":"At least £5m remains. Spending more does not necessarily improve the five-GW XI projection."})
    for team, count in sorted(clubs.items()):
        club = next(p.club for p in players if p.team_id == team)
        if count == 3:
            warnings.append({"code": "club_concentration", "team_id": team,
                             "message": f"Three players from {club}. Review shared fixture exposure."})
        if defence[team] >= 2:
            warnings.append({"code": "defensive_concentration", "team_id": team,
                             "message": f"{defence[team]} goalkeepers/defenders from {club}. Clean-sheet outcomes may be shared."})
    low = [p.id for p in players if p.recent and p.recent.complete
           and p.recent.minutes_per_gw is not None and p.recent.minutes_per_gw < 60]
    return {"budget_by_position": allocation, "club_counts": [
        {"team_id": team, "players": count} for team, count in sorted(clubs.items())],
        "low_minutes_player_ids": low, "warnings": warnings,
        "methodology":"Projected weekly XIs and captain bonuses drive selection; formation-aware cover, fewer transfers and lower spending break ties."}
