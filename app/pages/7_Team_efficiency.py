"""Team efficiency (layer 2): points per 100 of our own possessions, with heave / garbage switches.

Opens the DuckDB database **read-only** and reads only marts (marts.team_efficiency_season, and
marts.team_season for NBA.com's official ratings next to ours).
"""

from __future__ import annotations

import duckdb
import pandas as pd
import streamlit as st

from nba_platform.db import DB_PATH
from nba_platform.seasons import season_label

st.set_page_config(page_title="Team efficiency", layout="wide")

VERSIONS = {"Without end-of-period heaves": "_ex_heave", "All possessions": "",
            "Without heaves and garbage time": "_ex_heave_garbage"}


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


def main() -> None:
    st.title("Team efficiency")
    if not DB_PATH.exists() or not has_table("marts.team_efficiency_season"):
        st.error("marts.team_efficiency_season not found. Build it with `python -m nba_platform.marts.team_efficiency`.")
        return
    meta = query("SELECT any_value(rules_version) AS v, any_value(rules_profile) AS p FROM marts.team_efficiency_season").iloc[0]
    st.caption(f"Points per 100 possessions **counted from our play-by-play** (rules {meta['v']}, profile `{meta['p']}`). "
               "Technical free throws and free throws between possessions are outside possessions. "
               "NBA.com's **official** ratings are shown next to ours for comparison.")

    c1, c2, c3 = st.columns([1, 1, 2])
    season_type = c1.radio("Season type", ["regular", "playoffs"], horizontal=True)
    years = query("SELECT DISTINCT season_end_year FROM marts.team_efficiency_season WHERE season_type = ? ORDER BY 1 DESC",
                  (season_type,))["season_end_year"].tolist()
    year = c2.selectbox("Season", years, format_func=season_label)
    label = c3.radio("Possessions", list(VERSIONS), horizontal=True,
                     help="Heave: a possession starting with 2 s or less left in the period and scoring 0 (pbpstats). "
                          "Garbage time: Cleaning the Glass definition.")
    v = VERSIONS[label]

    table = query(f"""
        SELECT t.abbreviation AS team, e.games AS GP, e.o_poss{v} AS o_poss, e.ortg{v} AS ortg, e.d_poss{v} AS d_poss,
               e.drtg{v} AS drtg, e.net{v} AS net, e.poss_per_game AS pace,
               s.ortg_official_poss AS ortg_official, s.drtg_official_poss AS drtg_official,
               s.ortg_official_poss - s.drtg_official_poss AS net_official, e.pts_outside_possessions
        FROM marts.team_efficiency_season e JOIN core.teams t USING (team_id)
        LEFT JOIN marts.team_season s USING (season_end_year, season_type, team_id)
        WHERE e.season_end_year = ? AND e.season_type = ? ORDER BY net DESC""", (year, season_type))
    num = lambda title, fmt="%.1f", help=None: st.column_config.NumberColumn(title, format=fmt, help=help)  # noqa: E731
    st.dataframe(table, hide_index=True, width="stretch", column_config={
        "o_poss": num("O POSS", "%d"), "ortg": num("ORTG"), "d_poss": num("D POSS", "%d"), "drtg": num("DRTG"),
        "net": num("NET", "%+.1f"), "pace": num("POSS / GAME", help="(offense + defense possessions) / 2 / games, all possessions"),
        "ortg_official": num("ORTG (official)"), "drtg_official": num("DRTG (official)"), "net_official": num("NET (official)", "%+.1f"),
        "pts_outside_possessions": num("PTS outside poss.", "%d", "technical and between-possession free throws")})

    st.header("Four factors")
    st.caption("From our own events and possessions. eFG% = (FGM + 0.5 x 3PM) / FGA; TOV% = possessions ending in a turnover / "
               "possessions; ORB% = offensive rebounds / (offensive + the opponents' possession-ending defensive rebounds), team rebounds "
               "included; FT rate = made free throws in possessions / FGA. Defense = the opponents' numbers.")
    factors = query("""
        SELECT t.abbreviation AS team, o_efg, o_tov_pct, o_orb_pct, o_ft_rate, d_efg, d_tov_pct, d_orb_pct, d_ft_rate
        FROM marts.team_efficiency_season e JOIN core.teams t USING (team_id)
        WHERE e.season_end_year = ? AND e.season_type = ? ORDER BY o_efg DESC""", (year, season_type))
    pct = lambda title: st.column_config.NumberColumn(title, format="percent")  # noqa: E731
    st.dataframe(factors, hide_index=True, width="stretch", column_config={
        "o_efg": pct("eFG%"), "o_tov_pct": pct("TOV%"), "o_orb_pct": pct("ORB%"), "o_ft_rate": pct("FT rate"),
        "d_efg": pct("opp eFG%"), "d_tov_pct": pct("opp TOV%"), "d_orb_pct": pct("opp ORB%"), "d_ft_rate": pct("opp FT rate")})

    st.header("League across seasons")
    league = query(f"""
        SELECT season_end_year, 100.0 * sum(o_pts{v}) / sum(o_poss{v}) AS ortg, sum(o_poss) / sum(games) AS poss_per_game
        FROM marts.team_efficiency_season WHERE season_type = ? GROUP BY 1 ORDER BY 1""", (season_type,))
    league.index = league.pop("season_end_year").map(season_label)
    left, right = st.columns(2)
    left.markdown("**Points per 100 possessions** (league)")
    left.line_chart(league["ortg"])
    right.markdown("**Possessions per team-game** (all possessions)")
    right.line_chart(league["poss_per_game"])


main()
