"""Join squad IDs and filter/rank stored evaluation outputs. No score formulas."""

import pandas as pd


def match_squad(api_players, database_players):
    squad = api_players.merge(
        database_players, on="id", how="left", suffixes=("_api", ""),
        indicator=True, validate="one_to_one",
    )
    # API labels keep unmatched players visible, without inventing evaluations.
    for column in ["player_name", "element_type", "position", "club", "cost"]:
        squad[column] = squad[column].combine_first(squad.pop(f"{column}_api"))
    squad["status"] = "Matched"
    squad.loc[squad.viability_score.isna(), "status"] = "No evaluation"
    squad.loc[squad["_merge"] == "left_only", "status"] = "Not in database"
    return squad.drop(columns="_merge").sort_values("squad_order")


def replacement_candidates(selected, players, owned_ids):
    candidates = players.loc[
        (players.element_type == selected.element_type)
        & (players.cost <= selected.cost)
        & (players.viability_score > selected.viability_score)
        & (players.id != selected.id)
        & ~players.id.isin(owned_ids)
    ].copy()
    candidates["viability_gain"] = candidates.viability_score - selected.viability_score
    candidates["price_difference"] = candidates.cost - selected.cost
    return candidates.sort_values(
        ["viability_score", "cost", "id"], ascending=[False, True, True],
    )


def best_transfers(squad, players, metric):
    """One best replacement per outgoing player, ordered by the chosen metric."""
    if metric not in ("viability_score", "viability_per_cost"):
        raise ValueError("Unsupported ranking metric")
    options = []
    for _, selected in squad.iterrows():
        candidates = replacement_candidates(selected, players, squad.id)
        candidates = candidates.dropna(subset=[metric]).sort_values(
            [metric, "viability_gain", "cost", "id"],
            ascending=[False, False, True, True],
        )
        if candidates.empty:
            continue
        best = candidates.head(1).copy()
        best["outgoing_player"] = selected.player_name
        best["outgoing_score"] = selected.viability_score
        options.append(best)
    if not options:
        return pd.DataFrame()
    return pd.concat(options, ignore_index=True).sort_values(
        [metric, "viability_gain"], ascending=False,
    )
