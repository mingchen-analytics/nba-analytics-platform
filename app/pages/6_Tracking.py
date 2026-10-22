"""Tracking and hustle (layer 1): NBA.com season tracking numbers per player.

Opens the DuckDB database **read-only** and reads only `marts.player_tracking_season`.
Every number here is NBA.com's (official), not computed from our events.
"""

from __future__ import annotations

import duckdb
import pandas as pd
import streamlit as st

from nba_platform.db import DB_PATH
from nba_platform.marts.tracking import GROUPS
from nba_platform.seasons import season_label

st.set_page_config(page_title="Tracking", layout="wide")

LABELS = {"count": "", "rate": ""}
PCT_SUFFIX = ("_pct",)
NOTES = {
    "Hustle": "Hustle numbers exist from 2015-16.",
    "Movement": "Tracking numbers exist from 2013-14.",
}


@st.cache_resource
def connection() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DB_PATH), read_only=True)


@st.cache_data(ttl=300)
def query(sql: str, params: tuple = ()) -> pd.DataFrame:
    return connection().execute(sql, list(params)).df()


def games_column(group: str) -> str:
    return "hustle_gp" if group == "Hustle" else "gp"


def columns_of(group: str) -> list[tuple[str, str]]:
    """(mart column, kind) in display order."""
    return [(c.lower(), k) for _, c, k in GROUPS[group]]


def select_expressions(group: str, mode: str) -> str:
    gp = games_column(group)
    out = []
    for col, kind in columns_of(group):
        if kind == "rate" or mode == "Totals":
            out.append(col)
        elif mode == "Per game":
            out.append(f"{col} / nullif({gp}, 0) AS {col}")
        else:
            out.append(f"36 * {col} / nullif(min, 0) AS {col}")
    return ", ".join(out)


def column_config(group: str, mode: str) -> dict:
    cfg = {}
    for col, kind in columns_of(group):
        name = col.upper()
        if kind == "rate" and col.endswith(PCT_SUFFIX):
            cfg[col] = st.column_config.NumberColumn(name, format="percent")
        elif kind == "rate" or mode != "Totals":
            cfg[col] = st.column_config.NumberColumn(name, format="%.2f")
        else:
            cfg[col] = st.column_config.NumberColumn(name, format="%.0f" if "dist" not in col and "time" not in col else "%.1f")
    return cfg


def main() -> None:
    st.title("Tracking")
    if not DB_PATH.exists():
        st.error("Database not found. Build it with `python -m nba_platform.pipeline --all`.")
        return
    if not query("""SELECT count(*) AS n FROM information_schema.tables
                    WHERE table_schema = 'marts' AND table_name = 'player_tracking_season'""")["n"].iloc[0]:
        st.warning("`marts.player_tracking_season` has not been built yet. Close Streamlit and run "
                   "`python -m nba_platform.marts.tracking`.")
        return
    st.caption("NBA.com season tracking and hustle numbers (**official**, `marts.player_tracking_season`). In the regular season "
               "NBA.com lists a traded player once, under his last team, with full-season totals. Its tracking data misses some "
               "games, so tracking totals can be lower than the box score (`docs/validation/tracking_vs_box.md`).")

    c1, c2, c3, c4 = st.columns([1, 1, 1.4, 1.2])
    season_type = c1.radio("Season type", ["regular", "playoffs"], horizontal=True)
    group = c3.selectbox("Category", list(GROUPS))
    mode = c4.radio("Scale", ["Totals", "Per game", "Per 36"], horizontal=True)
    gp = games_column(group)
    years = query(f"SELECT DISTINCT season_end_year FROM marts.player_tracking_season WHERE season_type = ? AND {gp} IS NOT NULL ORDER BY 1 DESC",
                  (season_type,))["season_end_year"].tolist()
    if not years:
        st.info("No data for this selection.")
        return
    year = c2.selectbox("Season", years, format_func=season_label)
    if group in NOTES:
        st.caption(NOTES[group])

    max_games = int(query(f"SELECT max({gp}) AS g FROM marts.player_tracking_season WHERE season_end_year = ? AND season_type = ?",
                          (year, season_type))["g"].iloc[0])
    min_games = st.slider("Minimum games", 1, max(max_games, 1), min(max(1, max_games // 4), max_games))
    sort_options = [c for c, _ in columns_of(group)]
    sort_by = st.selectbox("Sort by", sort_options, format_func=str.upper)

    # NBA.com's movement numbers of some player-seasons are physically impossible (2025-26: average speeds up
    # to 22 mph); such rows are flagged in the mart (docs/validation/tracking_quality.md), kept, hidden by default
    has_flag = bool(query("""SELECT count(*) AS n FROM information_schema.columns WHERE table_schema = 'marts'
                             AND table_name = 'player_tracking_season' AND column_name = 'movement_suspect'""")["n"].iloc[0])
    hide_flagged = False
    if has_flag and group == "Movement":
        n_flag = int(query("""SELECT count(*) AS n FROM marts.player_tracking_season WHERE movement_suspect
                              AND season_end_year = ? AND season_type = ?""", (year, season_type))["n"].iloc[0])
        if n_flag:
            st.warning(f"{n_flag} player-seasons in {season_label(year)} ({season_type}) have implausible movement values from NBA.com "
                       "(average speed above the plausible maximum). Other players on the same teams may be affected too. "
                       "See `docs/validation/tracking_quality.md`.")
            hide_flagged = st.checkbox("Hide the flagged player-seasons", value=True)
    flag_col = "s.movement_suspect AS suspect, " if has_flag and group == "Movement" else ""
    flag_filter = " AND NOT coalesce(s.movement_suspect, FALSE)" if hide_flagged else ""

    board = query(f"""
        SELECT s.player_id, p.name AS player, t.abbreviation AS team, s.{gp} AS games, s.min, {flag_col}{select_expressions(group, mode)}
        FROM marts.player_tracking_season s JOIN core.players p USING (player_id) JOIN core.teams t USING (team_id)
        WHERE s.season_end_year = ? AND s.season_type = ? AND s.{gp} >= ?{flag_filter} ORDER BY {sort_by} DESC NULLS LAST LIMIT 300""",
                  (year, season_type, min_games))
    cfg = column_config(group, mode)
    cfg.update({"games": st.column_config.NumberColumn("GP", format="%d"), "min": st.column_config.NumberColumn("MIN", format="%d"),
                "suspect": st.column_config.CheckboxColumn("suspect", help="implausible value from NBA.com")})
    st.dataframe(board.drop(columns="player_id"), hide_index=True, width="stretch", column_config=cfg)
    if board.empty:
        return

    st.header("Player across seasons")
    names = board.set_index("player_id")["player"].to_dict()
    player_id = st.selectbox("Player (from the table above)", list(names), format_func=names.get)
    history = query(f"""
        SELECT s.season_end_year, s.season_type, t.abbreviation AS team, s.{gp} AS games, s.min, {flag_col}{select_expressions(group, mode)}
        FROM marts.player_tracking_season s JOIN core.teams t USING (team_id)
        WHERE s.player_id = ? AND s.{gp} IS NOT NULL ORDER BY s.season_end_year, s.season_type DESC""", (int(player_id),))
    history.insert(0, "season", history.pop("season_end_year").map(season_label))
    cfg["games"] = st.column_config.NumberColumn("GP", format="%d")
    st.dataframe(history, hide_index=True, width="stretch", column_config=cfg)


main()
