"""Lineups (layer 2): five-man lineups and two-man pairs of a team, per 100 of our possessions.

Opens the DuckDB database **read-only** and reads only marts (marts.lineup_stats, marts.pair_stats).
"""

from __future__ import annotations

import duckdb
import pandas as pd
import streamlit as st

from nba_platform.db import DB_PATH
from nba_platform.seasons import season_label

st.set_page_config(page_title="Lineups", layout="wide")


@st.cache_resource
def connection() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DB_PATH), read_only=True)


@st.cache_data(ttl=300)
def query(sql: str, params: tuple = ()) -> pd.DataFrame:
    return connection().execute(sql, list(params)).df()


def has_table(name: str) -> bool:
    schema, table = name.split(".")
    return bool(query("SELECT count(*) AS n FROM information_schema.tables WHERE table_schema = ? AND table_name = ?",
                      (schema, table))["n"].iloc[0])


def rate(pts: str, poss: str) -> str:
    return f"CASE WHEN {poss} > 0 THEN 100.0 * {pts} / {poss} END"


def ratings(hide_heaves: bool) -> str:
    o = "x.o_poss" + (" - x.o_heave_poss" if hide_heaves else "")
    d = "x.d_poss" + (" - x.d_heave_poss" if hide_heaves else "")
    return (f"x.games AS GP, x.secs / 60 AS minutes, {o} AS o_poss, {rate('x.o_pts', o)} AS ortg, {d} AS d_poss, "
            f"{rate('x.d_pts', d)} AS drtg, {rate('x.o_pts', o)} - {rate('x.d_pts', d)} AS net")


CFG = {"minutes": st.column_config.NumberColumn("MIN", format="%d"), "o_poss": st.column_config.NumberColumn("O POSS", format="%d"),
       "ortg": st.column_config.NumberColumn("ORTG", format="%.1f"), "d_poss": st.column_config.NumberColumn("D POSS", format="%d"),
       "drtg": st.column_config.NumberColumn("DRTG", format="%.1f"), "net": st.column_config.NumberColumn("NET", format="%+.1f")}


def main() -> None:
    st.title("Lineups")
    if not DB_PATH.exists() or not has_table("marts.lineup_stats") or not has_table("marts.pair_stats"):
        st.error("marts.lineup_stats / marts.pair_stats not found. Build them with `python -m nba_platform.marts.onoff`.")
        return
    st.caption("Five-man lineups and two-man pairs, **counted from our play-by-play** (same crediting as the On/off page). "
               "Small samples are noisy: the possession counts are shown next to every rate.")

    c1, c2, c3 = st.columns(3)
    season_type = c1.radio("Season type", ["regular", "playoffs"], horizontal=True)
    years = query("SELECT DISTINCT season_end_year FROM marts.lineup_stats WHERE season_type = ? ORDER BY 1 DESC",
                  (season_type,))["season_end_year"].tolist()
    year = c2.selectbox("Season", years, format_func=season_label)
    teams = query("""SELECT DISTINCT l.team_id, t.abbreviation FROM marts.lineup_stats l JOIN core.teams t USING (team_id)
                     WHERE l.season_end_year = ? AND l.season_type = ? ORDER BY 2""", (year, season_type))
    names = dict(zip(teams["team_id"], teams["abbreviation"]))
    team = c3.selectbox("Team", list(names), format_func=names.get)
    hide = st.toggle("Exclude end-of-period heaves", value=True,
                     help="0-point possessions starting with 2 s or less left in the period (pbpstats excludes them from efficiency).")

    five, two = st.tabs(["Five-man lineups", "Two-man pairs"])
    with five:
        min_poss = st.slider("Minimum offensive possessions", 0, 1500, 100 if season_type == "regular" else 25, step=25, key="five")
        lineups = query(f"""
            SELECT concat_ws(' · ', n1.name, n2.name, n3.name, n4.name, n5.name) AS lineup, {ratings(hide)}
            FROM marts.lineup_stats x
            JOIN core.players n1 ON n1.player_id = x.p1 JOIN core.players n2 ON n2.player_id = x.p2
            JOIN core.players n3 ON n3.player_id = x.p3 JOIN core.players n4 ON n4.player_id = x.p4
            JOIN core.players n5 ON n5.player_id = x.p5
            WHERE x.season_end_year = ? AND x.season_type = ? AND x.team_id = ? AND x.o_poss >= ?
            ORDER BY x.o_poss DESC""", (year, season_type, int(team), min_poss))
        st.dataframe(lineups, hide_index=True, width="stretch", column_config=CFG)
    with two:
        min_poss = st.slider("Minimum offensive possessions", 0, 4000, 300 if season_type == "regular" else 50, step=50, key="two")
        pairs = query(f"""
            SELECT a.name AS player_a, b.name AS player_b, {ratings(hide)}
            FROM marts.pair_stats x JOIN core.players a ON a.player_id = x.player_a JOIN core.players b ON b.player_id = x.player_b
            WHERE x.season_end_year = ? AND x.season_type = ? AND x.team_id = ? AND x.o_poss >= ?
            ORDER BY x.o_poss DESC""", (year, season_type, int(team), min_poss))
        st.dataframe(pairs, hide_index=True, width="stretch", column_config=CFG)


main()
