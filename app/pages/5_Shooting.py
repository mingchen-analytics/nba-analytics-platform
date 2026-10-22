"""Shooting (layer 1): a player's shot frequency and accuracy by zone, with league percentiles,
and a shot chart.

Opens the DuckDB database **read-only**. Zones and percentiles come from `marts.shot_zones_*`
(NBA shot chart data; percentiles among players above the minimums in config/rules.yaml).
The shot chart reads the player's shots from `core.shots`; flagged shots are shown, not hidden.
"""

from __future__ import annotations

import altair as alt
import duckdb
import numpy as np
import pandas as pd
import streamlit as st

from nba_platform.db import DB_PATH
from nba_platform.seasons import season_label

st.set_page_config(page_title="Shooting", layout="wide")

ZONE_ORDER = ["Restricted Area", "In The Paint (Non-RA)", "Mid-Range", "Left Corner 3", "Right Corner 3",
              "Above the Break 3", "Backcourt", "Unknown"]


@st.cache_resource
def connection() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DB_PATH), read_only=True)


@st.cache_data(ttl=300)
def query(sql: str, params: tuple = ()) -> pd.DataFrame:
    return connection().execute(sql, list(params)).df()


def court_lines() -> pd.DataFrame:
    """Hoop, paint and the three-point line in the shot chart's units (tenths of feet from the hoop)."""
    t = np.linspace(0, 2 * np.pi, 60)
    hoop = pd.DataFrame({"x": 7.5 * np.cos(t), "y": 7.5 * np.sin(t), "part": "hoop"})
    paint = pd.DataFrame({"x": [-80, -80, 80, 80], "y": [-47.5, 142.5, 142.5, -47.5], "part": "paint"})
    a = np.linspace(np.arccos(220 / 237.5), np.pi - np.arccos(220 / 237.5), 80)
    arc = pd.DataFrame({"x": 237.5 * np.cos(a), "y": 237.5 * np.sin(a), "part": "three"})
    left = pd.DataFrame({"x": [-220, -220], "y": [-47.5, 237.5 * np.sin(np.arccos(220 / 237.5))], "part": "corner_l"})
    right = pd.DataFrame({"x": [220, 220], "y": [-47.5, 237.5 * np.sin(np.arccos(220 / 237.5))], "part": "corner_r"})
    return pd.concat([hoop, paint, arc, left, right], ignore_index=True)


def main() -> None:
    st.title("Shooting")
    if not DB_PATH.exists():
        st.error("Database not found. Build it with `python -m nba_platform.pipeline --all`.")
        return
    st.caption("NBA shot chart data (`core.shots`), zones as labelled by NBA. Percentiles compare a player with other players "
               "of the same season and type above the minimum attempts (config/rules.yaml `dashboard`); smaller samples have none.")

    c1, c2, c3 = st.columns([1, 1, 2])
    season_type = c1.radio("Season type", ["regular", "playoffs"], horizontal=True)
    years = query("SELECT DISTINCT season_end_year FROM marts.shot_zones_player WHERE season_type = ? ORDER BY 1 DESC",
                  (season_type,))["season_end_year"].tolist()
    year = c2.selectbox("Season", years, format_func=season_label)
    players = query("""
        SELECT z.player_id, p.name, sum(z.fga) AS fga FROM marts.shot_zones_player z JOIN core.players p USING (player_id)
        WHERE z.season_end_year = ? AND z.season_type = ? GROUP BY ALL HAVING sum(z.fga) >= 50 ORDER BY fga DESC""", (year, season_type))
    names = players.set_index("player_id").apply(lambda r: f"{r['name']} ({int(r['fga'])} FGA)", axis=1).to_dict()
    player_id = c3.selectbox("Player (50+ attempts)", list(names), format_func=names.get)
    if player_id is None:
        st.info("No players for this selection.")
        return

    zones = query("""
        SELECT zone, fga, fgm, fg_pct, league_fg_pct, fg_pct_percentile, freq, league_freq, freq_percentile, flagged_share
        FROM marts.shot_zones_player WHERE season_end_year = ? AND season_type = ? AND player_id = ?""",
                  (year, season_type, int(player_id)))
    zones["order"] = zones["zone"].map({z: i for i, z in enumerate(ZONE_ORDER)})
    zones = zones.sort_values("order").drop(columns="order")
    st.subheader("Zones")
    st.dataframe(zones, hide_index=True, width="stretch", column_config={
        "fg_pct": st.column_config.NumberColumn("FG%", format="percent"),
        "league_fg_pct": st.column_config.NumberColumn("league FG%", format="percent"),
        "fg_pct_percentile": st.column_config.ProgressColumn("FG% percentile", min_value=0, max_value=100, format="%d"),
        "freq": st.column_config.NumberColumn("freq", format="percent"),
        "league_freq": st.column_config.NumberColumn("league freq", format="percent"),
        "freq_percentile": st.column_config.ProgressColumn("freq percentile", min_value=0, max_value=100, format="%d"),
        "flagged_share": st.column_config.NumberColumn("flagged shots", format="percent", help="share of shots with a data-quality flag")})

    st.subheader("Shot chart")
    shots = query("""
        SELECT s.loc_x, s.loc_y, s.made, s.shot_zone_basic AS zone
        FROM core.shots s JOIN core.games g USING (game_id)
        WHERE g.season_end_year = ? AND g.season_type = ? AND s.player_id = ? AND s.loc_x IS NOT NULL AND s.loc_y IS NOT NULL""",
                  (year, season_type, int(player_id)))
    if shots.empty:
        st.info("No shot locations for this player and season.")
        return
    shots["result"] = np.where(shots["made"], "made", "missed")
    points = alt.Chart(shots).mark_circle(size=28, opacity=0.6).encode(
        x=alt.X("loc_x:Q", scale=alt.Scale(domain=[-250, 250]), axis=None),
        y=alt.Y("loc_y:Q", scale=alt.Scale(domain=[-50, 420]), axis=None),
        color=alt.Color("result:N", scale=alt.Scale(domain=["made", "missed"], range=["#2e7d32", "#c62828"])),
        tooltip=["zone", "result"])
    lines = alt.Chart(court_lines()).mark_line(color="gray").encode(x="x:Q", y="y:Q", detail="part:N")
    st.altair_chart((lines + points).properties(width=520, height=490), width="content")
    st.caption(f"{len(shots):,} shots with a location; units are tenths of feet from the hoop.")


main()
