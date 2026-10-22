"""Teams (layer 1): season table, roster and shot mix of a team.

Opens the DuckDB database **read-only** and reads only marts. Pace and ratings use NBA.com's
official possession counts (labelled "official") until our own possessions exist.
"""

from __future__ import annotations

import duckdb
import pandas as pd
import streamlit as st

from nba_platform.db import DB_PATH
from nba_platform.seasons import season_label

st.set_page_config(page_title="Teams", layout="wide")


@st.cache_resource
def connection() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DB_PATH), read_only=True)


@st.cache_data(ttl=300)
def query(sql: str, params: tuple = ()) -> pd.DataFrame:
    return connection().execute(sql, list(params)).df()


def main() -> None:
    st.title("Teams")
    if not DB_PATH.exists():
        st.error("Database not found. Build it with `python -m nba_platform.pipeline --all`.")
        return
    st.caption("Totals from the official NBA.com box score. ORTG / DRTG / pace use NBA.com's official possession "
               "counts (**official**, not ours); they are replaced once our own possessions exist.")

    c1, c2 = st.columns(2)
    season_type = c1.radio("Season type", ["regular", "playoffs"], horizontal=True)
    years = query("SELECT DISTINCT season_end_year FROM marts.team_season WHERE season_type = ? ORDER BY 1 DESC",
                  (season_type,))["season_end_year"].tolist()
    year = c2.selectbox("Season", years, format_func=season_label)

    table = query("""
        SELECT s.team_id, t.abbreviation AS team, s.games AS GP, s.wins AS W, s.losses AS L,
               s.pts / s.games AS ppg, s.opponent_pts / s.games AS opp_ppg, (s.pts - s.opponent_pts) / s.games AS margin,
               s.ortg_official_poss AS ortg, s.drtg_official_poss AS drtg, s.ortg_official_poss - s.drtg_official_poss AS net,
               s.pace_official_poss AS pace, s.efg_pct, s.ts_pct
        FROM marts.team_season s JOIN core.teams t USING (team_id)
        WHERE s.season_end_year = ? AND s.season_type = ? ORDER BY s.wins DESC, margin DESC""", (year, season_type))
    st.dataframe(table.drop(columns="team_id").rename(columns={
        "ppg": "PPG", "opp_ppg": "OPP PPG", "margin": "MARGIN", "ortg": "ORTG (official)", "drtg": "DRTG (official)",
        "net": "NET (official)", "pace": "PACE (official)", "efg_pct": "eFG%", "ts_pct": "TS%"}),
        hide_index=True, width="stretch", column_config={
            "PPG": st.column_config.NumberColumn(format="%.1f"), "OPP PPG": st.column_config.NumberColumn(format="%.1f"),
            "MARGIN": st.column_config.NumberColumn(format="%+.1f"), "ORTG (official)": st.column_config.NumberColumn(format="%.1f"),
            "DRTG (official)": st.column_config.NumberColumn(format="%.1f"), "NET (official)": st.column_config.NumberColumn(format="%+.1f"),
            "PACE (official)": st.column_config.NumberColumn(format="%.1f"), "eFG%": st.column_config.NumberColumn(format="percent"),
            "TS%": st.column_config.NumberColumn(format="percent")})

    st.header("Team")
    names = table.set_index("team_id")["team"].to_dict()
    team_id = st.selectbox("Team", list(names), format_func=names.get)

    left, right = st.columns(2)
    with left:
        st.markdown("**Roster** (minutes order)")
        roster = query("""
            SELECT p.name AS player, s.games AS GP, s.mpg, s.ppg, s.rpg, s.apg, s.ts_pct
            FROM marts.player_season s JOIN core.players p USING (player_id)
            WHERE s.season_end_year = ? AND s.season_type = ? AND s.team_id = ? ORDER BY s.min DESC""", (year, season_type, int(team_id)))
        st.dataframe(roster, hide_index=True, width="stretch", column_config={
            "mpg": st.column_config.NumberColumn("MPG", format="%.1f"), "ppg": st.column_config.NumberColumn("PPG", format="%.1f"),
            "rpg": st.column_config.NumberColumn("RPG", format="%.1f"), "apg": st.column_config.NumberColumn("APG", format="%.1f"),
            "ts_pct": st.column_config.NumberColumn("TS%", format="percent")})
    with right:
        st.markdown("**Shot mix by zone** (offense = own shots, defense = shots allowed; league = same season)")
        zones = query("""
            SELECT side, zone, fga, freq, league_freq, fg_pct, league_fg_pct
            FROM marts.shot_zones_team WHERE season_end_year = ? AND season_type = ? AND team_id = ?
            ORDER BY side DESC, fga DESC""", (year, season_type, int(team_id)))
        st.dataframe(zones, hide_index=True, width="stretch", column_config={
            "freq": st.column_config.NumberColumn("freq", format="percent"), "league_freq": st.column_config.NumberColumn("league freq", format="percent"),
            "fg_pct": st.column_config.NumberColumn("FG%", format="percent"), "league_fg_pct": st.column_config.NumberColumn("league FG%", format="percent")})

    st.markdown("**Results**")
    games = query("""
        SELECT m.game_date, o.abbreviation AS opponent, m.is_home, m.won, m.pts, m.opponent_pts
        FROM marts.team_game m JOIN core.teams o ON o.team_id = m.opponent_team_id
        WHERE m.season_end_year = ? AND m.season_type = ? AND m.team_id = ? ORDER BY m.game_date""", (year, season_type, int(team_id)))
    games["game_date"] = games["game_date"].astype(str).str[:10]
    st.dataframe(games, hide_index=True, width="stretch")
    if not games.empty:
        games["margin"] = games["pts"] - games["opponent_pts"]
        st.bar_chart(games.set_index("game_date")["margin"], y_label="point margin")


main()
