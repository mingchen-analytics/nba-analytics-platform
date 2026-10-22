"""Players (layer 1): season leaderboard and a player's game log.

Opens the DuckDB database **read-only** and reads only marts (official NBA.com box score).
"""

from __future__ import annotations

import duckdb
import pandas as pd
import streamlit as st

from nba_platform.db import DB_PATH
from nba_platform.seasons import season_label

st.set_page_config(page_title="Players", layout="wide")

# column -> label; the leaderboard sorts on any of them
STATS = {"ppg": "PPG", "rpg": "RPG", "apg": "APG", "spg": "SPG", "bpg": "BPG", "tpg": "TOV", "mpg": "MPG",
         "ts_pct": "TS%", "efg_pct": "eFG%", "fg3_pct": "3P%", "ft_pct": "FT%", "pts_per36": "PTS/36",
         "reb_per36": "REB/36", "ast_per36": "AST/36", "pts": "PTS", "min": "MIN"}
PCT = {"ts_pct", "efg_pct", "fg3_pct", "ft_pct"}


@st.cache_resource
def connection() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DB_PATH), read_only=True)


@st.cache_data(ttl=300)
def query(sql: str, params: tuple = ()) -> pd.DataFrame:
    return connection().execute(sql, list(params)).df()


def main() -> None:
    st.title("Players")
    if not DB_PATH.exists():
        st.error("Database not found. Build it with `python -m nba_platform.pipeline --all`.")
        return
    st.caption("Official NBA.com box score (`marts.player_season`, `marts.player_game`). "
               "Games = games in the box score; a traded player has one row per team.")

    c1, c2, c3, c4 = st.columns(4)
    season_type = c1.radio("Season type", ["regular", "playoffs"], horizontal=True)
    years = query("SELECT DISTINCT season_end_year FROM marts.player_season WHERE season_type = ? ORDER BY 1 DESC",
                  (season_type,))["season_end_year"].tolist()
    year = c2.selectbox("Season", years, format_func=season_label)
    sort_by = c3.selectbox("Sort by", list(STATS), format_func=STATS.get)
    max_games = int(query("SELECT max(games) AS g FROM marts.player_season WHERE season_end_year = ? AND season_type = ?",
                          (year, season_type))["g"].iloc[0])
    min_games = c4.slider("Minimum games", 1, max_games, min(max(1, max_games // 4), max_games))

    board = query(f"""
        SELECT p.player_id, p.name AS player, t.abbreviation AS team, s.games, {", ".join("s." + c for c in STATS)}
        FROM marts.player_season s JOIN core.players p USING (player_id) JOIN core.teams t USING (team_id)
        WHERE s.season_end_year = ? AND s.season_type = ? AND s.games >= ?
        ORDER BY s.{sort_by} DESC NULLS LAST LIMIT 200""", (year, season_type, min_games))
    show = board.drop(columns="player_id").rename(columns={"games": "GP", **STATS})
    st.dataframe(show, hide_index=True, width="stretch", column_config={
        **{STATS[c]: st.column_config.NumberColumn(format="percent") for c in PCT},
        **{STATS[c]: st.column_config.NumberColumn(format="%.1f") for c in STATS if c not in PCT and c not in ("pts", "min")},
        "PTS": st.column_config.NumberColumn(format="%d"), "MIN": st.column_config.NumberColumn(format="%d")})

    if board.empty:
        return
    st.header("Player")
    names = board.set_index("player_id")["player"].to_dict()
    player_id = st.selectbox("Player (from the table above)", list(names), format_func=names.get)
    seasons = query("""
        SELECT s.season_end_year, s.season_type, t.abbreviation AS team, s.games, s.mpg, s.ppg, s.rpg, s.apg, s.spg, s.bpg,
               s.fg_pct, s.fg3_pct, s.ft_pct, s.ts_pct
        FROM marts.player_season s JOIN core.teams t USING (team_id) WHERE s.player_id = ?
        ORDER BY s.season_end_year, s.season_type DESC""", (int(player_id),))
    seasons.insert(0, "season", seasons.pop("season_end_year").map(season_label))
    st.markdown("**Seasons**")
    st.dataframe(seasons, hide_index=True, width="stretch", column_config={
        c: st.column_config.NumberColumn(format="percent") for c in ("fg_pct", "fg3_pct", "ft_pct", "ts_pct")})

    log = query("""
        SELECT g.game_date, o.abbreviation AS opponent, g.is_home, g.won, g.min, g.pts, g.reb, g.ast, g.stl, g.blk, g.tov, g.pf,
               g.fgm::INT || '-' || g.fga::INT AS fg, g.fg3m::INT || '-' || g.fg3a::INT AS fg3, g.plus_minus
        FROM marts.player_game g JOIN core.teams o ON o.team_id = g.opponent_team_id
        WHERE g.player_id = ? AND g.season_end_year = ? AND g.season_type = ? ORDER BY g.game_date DESC""",
                (int(player_id), year, season_type))
    log["game_date"] = log["game_date"].astype(str).str[:10]
    st.markdown(f"**Game log {season_label(year)} ({season_type})**")
    st.dataframe(log, hide_index=True, width="stretch")
    if not log.empty:
        st.line_chart(log.sort_values("game_date").set_index("game_date")["pts"], y_label="points")


main()
