"""Games (layer 1): the official box score of a game and its score margin.

Opens the DuckDB database **read-only**. Reads marts and the event table only; nothing is
computed here. The box score is NBA.com's (official); the score chart is from our events.
"""

from __future__ import annotations

import duckdb
import pandas as pd
import streamlit as st

from nba_platform.db import DB_PATH
from nba_platform.seasons import season_label

st.set_page_config(page_title="Games", layout="wide")

BOX_COLUMNS = {"name": "Player", "min": "MIN", "pts": "PTS", "reb": "REB", "ast": "AST", "stl": "STL", "blk": "BLK",
               "tov": "TOV", "pf": "PF", "fg": "FG", "fg3": "3P", "ft": "FT", "plus_minus": "+/-"}


@st.cache_resource
def connection() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DB_PATH), read_only=True)


@st.cache_data(ttl=300)
def query(sql: str, params: tuple = ()) -> pd.DataFrame:
    return connection().execute(sql, list(params)).df()


def box_table(game_id: str, team_id: int) -> pd.DataFrame:
    df = query("""
        SELECT p.name, g.min, g.pts, g.reb, g.ast, g.stl, g.blk, g.tov, g.pf,
               g.fgm::INT || '-' || g.fga::INT AS fg, g.fg3m::INT || '-' || g.fg3a::INT AS fg3,
               g.ftm::INT || '-' || g.fta::INT AS ft, g.plus_minus
        FROM marts.player_game g JOIN core.players p USING (player_id)
        WHERE g.game_id = ? AND g.team_id = ? ORDER BY g.min DESC, g.pts DESC""", (game_id, team_id))
    return df.rename(columns=BOX_COLUMNS)


def main() -> None:
    st.title("Games")
    if not DB_PATH.exists():
        st.error("Database not found. Build it with `python -m nba_platform.pipeline --all`.")
        return
    st.caption("Official NBA.com box score (`marts.player_game`). The score chart is drawn from our play-by-play events.")

    c1, c2, c3 = st.columns([1, 1, 1])
    season_type = c1.radio("Season type", ["regular", "playoffs"], horizontal=True)
    years = query("SELECT DISTINCT season_end_year FROM marts.team_game WHERE season_type = ? ORDER BY 1 DESC",
                  (season_type,))["season_end_year"].tolist()
    year = c2.selectbox("Season", years, format_func=season_label)
    teams = query("""SELECT DISTINCT t.team_id, t.abbreviation FROM marts.team_game m JOIN core.teams t USING (team_id)
                     WHERE m.season_end_year = ? AND m.season_type = ? ORDER BY 2""", (year, season_type))
    team_choice = c3.selectbox("Team", [None] + teams["team_id"].tolist(), format_func=lambda t: "All teams" if t is None else
                               teams.set_index("team_id").loc[t, "abbreviation"])

    games = query("""
        SELECT g.game_id, g.game_date, g.home_team_id, g.away_team_id, g.home_score, g.away_score,
               h.abbreviation AS home, a.abbreviation AS away
        FROM core.games g JOIN core.teams h ON h.team_id = g.home_team_id JOIN core.teams a ON a.team_id = g.away_team_id
        WHERE g.season_end_year = ? AND g.season_type = ?
          AND (? IS NULL OR g.home_team_id = ? OR g.away_team_id = ?)
          AND g.game_id IN (SELECT game_id FROM marts.team_game)
        ORDER BY g.game_date DESC, g.game_id DESC""", (year, season_type, team_choice, team_choice, team_choice))
    games["game_date"] = games["game_date"].astype(str).str[:10]
    if games.empty:
        st.info("No games for this selection.")
        return
    labels = {r.game_id: f"{r.game_date}  {r.away} {r.away_score:.0f} @ {r.home} {r.home_score:.0f}"
              if pd.notna(r.home_score) else f"{r.game_date}  {r.away} @ {r.home}" for r in games.itertuples()}
    game_id = st.selectbox("Game", list(labels), format_func=labels.get)
    g = games.set_index("game_id").loc[game_id]

    st.subheader(f"{g['away']} @ {g['home']}  ·  {g['game_date']}")
    left, right = st.columns(2)
    for col, team_id, abbr in ((left, int(g["away_team_id"]), g["away"]), (right, int(g["home_team_id"]), g["home"])):
        with col:
            st.markdown(f"**{abbr}**")
            st.dataframe(box_table(game_id, team_id), hide_index=True, width="stretch",
                         column_config={"MIN": st.column_config.NumberColumn(format="%d"),
                                        "+/-": st.column_config.NumberColumn(format="%+d")})

    st.markdown("**Score margin** (home minus away, from our play-by-play)")
    events = query("""SELECT secs_elapsed_game / 60.0 AS minute, home_score - away_score AS margin FROM core.events
                      WHERE game_id = ? AND home_score IS NOT NULL AND away_score IS NOT NULL ORDER BY event_seq""", (game_id,))
    if events.empty:
        st.info("No play-by-play for this game.")
    else:
        st.line_chart(events.set_index("minute")["margin"], x_label="game minute", y_label=f"{g['home']} lead")


main()
