"""Lineups (layer 2): two- to five-man groups, per 100 of our own possessions, with the four factors and a noise hint.

Opens the DuckDB database **read-only** and reads only marts (marts.pair_stats, marts.combo_stats, marts.lineup_stats,
marts.possession_noise). Three views: one team, the whole league, and every group a player belongs to.
"""

from __future__ import annotations

import duckdb
import pandas as pd
import streamlit as st

from nba_platform.db import DB_PATH
from nba_platform.seasons import season_label

st.set_page_config(page_title="Lineups", layout="wide")

# size -> (table, key columns, extra filter)
SIZES = {2: ("marts.pair_stats", ["player_a", "player_b"], "TRUE"),
         3: ("marts.combo_stats", ["p1", "p2", "p3"], "x.size = 3"),
         4: ("marts.combo_stats", ["p1", "p2", "p3", "p4"], "x.size = 4"),
         5: ("marts.lineup_stats", ["p1", "p2", "p3", "p4", "p5"], "TRUE")}
SIZE_LABEL = {2: "Two-man pairs", 3: "Three-man", 4: "Four-man", 5: "Five-man lineups"}
SORTS = {"NET (best first)": "net DESC NULLS LAST", "NET (worst first)": "net ASC NULLS LAST", "ORTG": "ortg DESC NULLS LAST",
         "DRTG (best first)": "drtg ASC NULLS LAST", "Possessions": "o_poss DESC", "Minutes": "minutes DESC"}
NEEDED = ("pair_stats", "combo_stats", "lineup_stats", "possession_noise")


@st.cache_resource
def connection() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DB_PATH), read_only=True)


@st.cache_data(ttl=300)
def query(sql: str, params: tuple = ()) -> pd.DataFrame:
    return connection().execute(sql, list(params)).df()


def has_tables() -> bool:
    n = query("SELECT count(*) AS n FROM information_schema.tables WHERE table_schema = 'marts' AND table_name IN ('pair_stats', 'combo_stats', "
              "'lineup_stats', 'possession_noise')")["n"].iloc[0]
    return int(n) == len(NEEDED)


def rate(pts: str, poss: str) -> str:
    return f"CASE WHEN {poss} > 0 THEN 100.0 * {pts} / {poss} END"


def board_sql(size: int, hide_heaves: bool, where: str, order: str, limit: int) -> str:
    """Rows of one group size. Ratings can leave out end-of-period heaves; the four factors always use all possessions."""
    table, keys, extra = SIZES[size]
    names = ", ".join(f"n{i}.name" for i in range(len(keys)))
    joins = " ".join(f"JOIN core.players n{i} ON n{i}.player_id = x.{k}" for i, k in enumerate(keys))
    o = "(x.o_poss - x.o_heave_poss)" if hide_heaves else "x.o_poss"
    d = "(x.d_poss - x.d_heave_poss)" if hide_heaves else "x.d_poss"
    net = f"({rate('x.o_pts', o)} - {rate('x.d_pts', d)})"
    return f"""
        SELECT * FROM (
            SELECT t.abbreviation AS team, x.season_end_year, concat_ws(' · ', {names}) AS group_name, x.games AS gp, x.secs / 60 AS minutes,
                   {o} AS o_poss, {rate('x.o_pts', o)} AS ortg, {d} AS d_poss, {rate('x.d_pts', d)} AS drtg, {net} AS net,
                   CASE WHEN {o} > 0 AND {d} > 0 THEN 196.0 * n.sd_pts * sqrt(1.0 / {o} + 1.0 / {d}) END AS net_margin,
                   x.o_efg, x.o_tov_pct, x.o_orb_pct, x.o_ft_rate, x.d_efg, x.d_tov_pct, x.d_orb_pct, x.d_ft_rate
            FROM {table} x {joins} JOIN core.teams t ON t.team_id = x.team_id
            JOIN marts.possession_noise n ON n.season_end_year = x.season_end_year AND n.season_type = x.season_type
            WHERE {extra} AND {where}) ORDER BY {order} LIMIT {int(limit)}"""


def show(df: pd.DataFrame, with_team: bool = True, with_season: bool = False) -> None:
    df = df.copy()
    df["signal"] = [("clear" if pd.notna(n) and pd.notna(m) and abs(n) > m else "within noise") for n, m in zip(df["net"], df["net_margin"])]
    if with_season:
        df.insert(1, "season", df["season_end_year"].map(season_label))
    df = df.drop(columns=["season_end_year"] + ([] if with_team else ["team"]))
    pct = lambda title: st.column_config.NumberColumn(title, format="percent")  # noqa: E731
    st.dataframe(df, hide_index=True, width="stretch", column_config={
        "group_name": "group", "gp": st.column_config.NumberColumn("GP", format="%d"), "minutes": st.column_config.NumberColumn("MIN", format="%d"),
        "o_poss": st.column_config.NumberColumn("O POSS", format="%d"), "ortg": st.column_config.NumberColumn("ORTG", format="%.1f"),
        "d_poss": st.column_config.NumberColumn("D POSS", format="%d"), "drtg": st.column_config.NumberColumn("DRTG", format="%.1f"),
        "net": st.column_config.NumberColumn("NET", format="%+.1f"),
        "net_margin": st.column_config.NumberColumn("± 95%", format="%.1f", help="approximate half-width of NET: 1.96 x 100 x the season's standard "
                                                                                  "deviation of points per possession x sqrt(1/O POSS + 1/D POSS)"),
        "signal": st.column_config.TextColumn("vs noise", help="'clear' when |NET| is larger than the approximate 95% half-width"),
        "o_efg": pct("eFG%"), "o_tov_pct": pct("TOV%"), "o_orb_pct": pct("ORB%"), "o_ft_rate": pct("FT rate"),
        "d_efg": pct("opp eFG%"), "d_tov_pct": pct("opp TOV%"), "d_orb_pct": pct("opp ORB%"), "d_ft_rate": pct("opp FT rate")})


def season_picker(prefix: str):
    c1, c2 = st.columns(2)
    season_type = c1.radio("Season type", ["regular", "playoffs"], horizontal=True, key=f"{prefix}_type")
    years = query("SELECT DISTINCT season_end_year FROM marts.lineup_stats WHERE season_type = ? ORDER BY 1 DESC", (season_type,))["season_end_year"].tolist()
    year = c2.selectbox("Season", years, format_func=season_label, key=f"{prefix}_year")
    return season_type, int(year)


def default_min_poss(size: int, season_type: str, league: bool) -> int:
    base = {2: 300, 3: 250, 4: 200, 5: 100}[size] * (1 if season_type == "regular" else 0.2)
    return int(base * (1.5 if league else 1))


def main() -> None:
    st.title("Lineups")
    if not DB_PATH.exists() or not has_tables():
        st.error("Lineup tables not found. Build them with `python -m nba_platform.marts.onoff`.")
        return
    st.caption("Two- to five-man groups, **counted from our play-by-play** (same crediting as the On/off page). ORTG / DRTG / NET are per 100 possessions; "
               "the four factors are shown for the group's offense and for its opponents. Small samples are noisy: the **± 95%** column is an "
               "approximate half-width of NET and the **vs noise** column says whether NET is larger than it. It is a statistical approximation, "
               "not a model. The four factors count all possessions (heaves and garbage time included).")
    hide = st.toggle("Exclude end-of-period heaves from ORTG / DRTG / NET", value=True,
                     help="0-point possessions starting with 2 s or less left in the period (pbpstats excludes them from efficiency).")

    team_tab, league_tab, player_tab = st.tabs(["Team", "League leaderboard", "By player"])

    with team_tab:
        season_type, year = season_picker("team")
        teams = query("""SELECT DISTINCT l.team_id, t.abbreviation FROM marts.lineup_stats l JOIN core.teams t USING (team_id)
                         WHERE l.season_end_year = ? AND l.season_type = ? ORDER BY 2""", (year, season_type))
        names = dict(zip(teams["team_id"], teams["abbreviation"]))
        c3, c4 = st.columns([1, 2])
        team = c3.selectbox("Team", list(names), format_func=names.get, key="team_team")
        size = c4.radio("Group size", list(SIZES), format_func=SIZE_LABEL.get, horizontal=True, index=3, key="team_size")
        min_poss = st.slider("Minimum offensive possessions", 0, 2000, default_min_poss(size, season_type, False), step=25, key="team_min")
        where = f"x.season_end_year = {year} AND x.season_type = '{season_type}' AND x.team_id = {int(team)} AND x.o_poss >= {int(min_poss)}"
        show(query(board_sql(size, hide, where, "o_poss DESC", 500)), with_team=False)

    with league_tab:
        season_type, year = season_picker("league")
        c3, c4, c5 = st.columns([2, 1, 1])
        size = c3.radio("Group size", list(SIZES), format_func=SIZE_LABEL.get, horizontal=True, index=3, key="league_size")
        min_poss = c4.slider("Minimum offensive possessions", 0, 3000, default_min_poss(size, season_type, True), step=25, key="league_min")
        sort_by = c5.selectbox("Sort by", list(SORTS), key="league_sort")
        where = f"x.season_end_year = {year} AND x.season_type = '{season_type}' AND x.o_poss >= {int(min_poss)}"
        board = query(board_sql(size, hide, where, SORTS[sort_by], 100))
        st.caption(f"Top {len(board)} of the league's {SIZE_LABEL[size].lower()} with at least {min_poss} offensive possessions.")
        show(board)

    with player_tab:
        season_type, year = season_picker("player")
        players = query("""SELECT o.player_id, p.name, max(o.on_secs) AS secs FROM marts.player_onoff_season o JOIN core.players p USING (player_id)
                           WHERE o.season_end_year = ? AND o.season_type = ? GROUP BY 1, 2 ORDER BY secs DESC""", (year, season_type))
        pnames = dict(zip(players["player_id"], players["name"]))
        c3, c4 = st.columns([1, 2])
        player = c3.selectbox("Player (most minutes first)", list(pnames), format_func=pnames.get, key="player_player")
        size = c4.radio("Group size", list(SIZES), format_func=SIZE_LABEL.get, horizontal=True, index=3, key="player_size")
        min_poss = st.slider("Minimum offensive possessions", 0, 2000, default_min_poss(size, season_type, False) // 2, step=25, key="player_min")
        keys = SIZES[size][1]
        member = " OR ".join(f"x.{k} = {int(player)}" for k in keys)
        where = f"x.season_end_year = {year} AND x.season_type = '{season_type}' AND ({member}) AND x.o_poss >= {int(min_poss)}"
        board = query(board_sql(size, hide, where, "o_poss DESC", 500))
        st.caption(f"{len(board)} {SIZE_LABEL[size].lower()} groups that include {pnames[player]} (a traded player appears for each team).")
        show(board)


main()
