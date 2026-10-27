"""Run with: .venv/bin/python -m streamlit run app.py"""

import duckdb
import pandas as pd
import streamlit as st

from database import load_players
from fpl_api import FPLError, fetch_squad
from recommendations import best_transfers, match_squad, replacement_candidates


METRICS = [
    "viability_score", "viability_per_cost", "form_percentile",
    "points_per_gw_percentile", "normalized_n5fs",
]
CANDIDATE_COLUMNS = [
    "player_name", "club", "cost", "viability_score", "viability_per_cost",
    "viability_gain", "price_difference", "form_percentile",
    "points_per_gw_percentile", "normalized_n5fs",
]


def show_table(frame, columns):
    config = {
        "viability_score": st.column_config.NumberColumn("Viability", format="%.3f", help="Saved player score. Higher is better."),
        "viability_per_cost": st.column_config.NumberColumn("Value / £m", format="%.4f", help="Saved viability_by_cost metric, unchanged."),
        "viability_gain": st.column_config.NumberColumn("Score gain", format="%+.3f", help="Replacement viability minus your player's viability."),
        "outgoing_score": st.column_config.NumberColumn("Current score", format="%.3f"),
    }
    for name, label, help_text in [
        ("form_percentile", "Form rank", "Form percentile among players in the same position."),
        ("points_per_gw_percentile", "Points rank", "Points-per-gameweek percentile among players in the same position."),
        ("normalized_n5fs", "Fixture ease", "Saved normalized rating for the next five fixtures. Higher means easier."),
        ("start_ratio", "Start rate", "Saved starts-to-completed-gameweeks ratio."),
    ]:
        config[name] = st.column_config.NumberColumn(label, format="percent", step=0.001, help=help_text)
    config["cost"] = st.column_config.NumberColumn("Cost (£m)", format="%.1f")
    config["price_difference"] = st.column_config.NumberColumn(
        "Price change (£m)", format="%+.1f", help="Replacement price minus current price. Negative means cheaper.",
    )
    config["player_name"] = st.column_config.TextColumn("Player", pinned=True)
    config["outgoing_player"] = "Transfer out"
    config.update(position="Pos", club="Club", role="Lineup", status="Evaluation")
    st.dataframe(
        frame[columns], hide_index=True, width="stretch",
        height=min(420, 36 * (len(frame) + 1) + 4), column_config=config,
    )


def selected_summary(player):
    def formatted(value, spec):
        return "—" if pd.isna(value) else format(value, spec)

    with st.container(border=True):
        st.markdown(f"**{player.player_name}** · {player.position} · {player.club}")
        for column, label, value in zip(st.columns(4),
            ["Price", "Viability", "Value / £m", "Start rate"],
            [f"£{formatted(player.cost, '.1f')}m",
             formatted(player.viability_score, '.3f'),
             formatted(player.viability_per_cost, '.4f'),
             formatted(player.start_ratio, '.1%')],
        ):
            column.metric(label, value)
        st.caption(
            f"Form rank: {formatted(player.form_percentile, '.1%')} · "
            f"Points rank: {formatted(player.points_per_gw_percentile, '.1%')} · "
            f"Fixture ease: {formatted(player.normalized_n5fs, '.1%')}"
        )


def main():
    st.set_page_config(page_title="FPL Optimiser", page_icon="⚽", layout="wide")
    st.title("FPL Optimiser")
    st.caption("Your squad. Affordable upgrades. A clearer next move.")
    with st.sidebar:
        st.header("Your team")
        with st.form("team_form"):
            team_id = st.text_input("FPL team ID", placeholder="e.g. 7425041", help="The number after /entry/ in your FPL points-page URL.")
            submitted = st.form_submit_button("Load squad", type="primary", width="stretch")
        detailed = st.toggle("Show detailed stats", help="Add form rank, points rank and fixture ease to the tables.")
        with st.expander("How to read the scores"):
            st.markdown(
                "**Viability** is your saved player score. **Value / £m** is the saved "
                "viability_by_cost metric. Higher is better for both.\n\n"
                "**Form rank** and **Points rank** are percentiles within a position. "
                "**Fixture ease** and **Start rate** are shown as percentages. "
                "Hover over a table heading for details.\n\n"
                "Prices and scores come from your saved database. Percentages are display "
                "formatting only; the underlying values are unchanged."
            )
        with st.expander("About the suggestions"):
            st.write(
                "Replacements must play the same position, cost no more, have a higher "
                "viability score, and not already be in your squad. Suggestions are "
                "independent and do not check club limits, selling prices, bank balance or transfer hits."
            )
    if submitted:
        # Clear the prior result so an invalid ID never leaves an old squad on screen.
        st.session_state.pop("squad_result", None)
        st.session_state.pop("selected_player", None)
        try:
            with st.spinner("Fetching your squad…"):
                st.session_state.squad_result = fetch_squad(team_id)
        except FPLError as exc:
            st.error(str(exc))
    if "squad_result" not in st.session_state:
        st.info("Enter the team ID from your FPL team's points-page URL to get started.")
        return

    try:
        players = load_players()
    except (duckdb.Error, OSError) as exc:
        st.error("Could not read data/fpl.duckdb. Check that the database and existing evaluation tables are available and not locked by another process.")
        with st.expander("Database error details"):
            st.code(str(exc))
        return

    result = st.session_state.squad_result
    squad = match_squad(result["players"], players)
    st.subheader(f"{result['team_name']} · Gameweek {result['gameweek']}")
    st.caption("Latest published squad, including the bench. Post-deadline transfers may not appear.")
    missing = squad.loc[squad.status != "Matched", "player_name"].tolist()
    if missing:
        st.warning(
            "Missing evaluations for: " + ", ".join(missing)
            + ". They remain visible, but cannot be compared for replacements."
        )
    st.subheader("Your squad")
    show_table(squad, [
        "player_name", "position", "club", "role", "cost",
        "viability_score", "viability_per_cost", "start_ratio",
        *(METRICS[2:] if detailed else []),
        *(["status"] if missing else []),
    ])

    st.subheader("Find a replacement")
    selection_order = squad.sort_values("viability_score", na_position="last")
    labels = {row.id: f"{row.player_name} · {row.position} · {row.club}"
              for row in squad.itertuples()}
    selected_id = st.selectbox(
        "Choose a player to replace", selection_order.id.tolist(), format_func=labels.get,
        key="selected_player", help="Players are ordered by lowest viability first, to help you find potential upgrades.",
    )
    selected_player = squad.loc[squad.id == selected_id]
    selected = selected_player.iloc[0]
    selected_summary(selected)
    candidate_columns = CANDIDATE_COLUMNS if detailed else CANDIDATE_COLUMNS[:7]
    if selected.status != "Matched":
        st.info("This player has no saved evaluation, so a higher viability_score cannot be established.")
    else:
        replacements = replacement_candidates(selected, players, squad.id)
        st.markdown(f"**{len(replacements)} affordable upgrades**")
        st.caption(f"{selected.position} · £{selected.cost:.1f}m or less · Higher viability first")
        if replacements.empty:
            st.info("No affordable upgrades for this player. Choose another squad member above.")
        else:
            show_table(replacements, candidate_columns)

    with st.expander("Best Transfers · compare upgrades across your squad"):
        st.caption("One best replacement per player. Each suggestion is a separate option.")
        for tab, metric in zip(
            st.tabs(["Best by viability", "Best by value"]),
            ["viability_score", "viability_per_cost"],
        ):
            with tab:
                transfers = best_transfers(squad, players, metric)
                if transfers.empty:
                    st.info("No affordable upgrades with the required metrics were found.")
                else:
                    show_table(transfers, ["outgoing_player", "outgoing_score", "position", *candidate_columns])


if __name__ == "__main__":
    main()
