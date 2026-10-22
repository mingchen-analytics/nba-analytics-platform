"""Matchups (layer 2): who guarded a player in a series, game by game.

Opens the DuckDB database **read-only** and reads only marts (marts.matchup_pairs, from NBA.com matchup data,
2017-18 -> 2024-25; **official**). The idea of the Playoff Matchup Adjustment Tracker: a series total can hide
that a coach changed the defensive assignment between games, so the share of the player's guarded time is
shown for every game.
"""

from __future__ import annotations

import duckdb
import pandas as pd
import streamlit as st

from nba_platform.db import DB_PATH
from nba_platform.seasons import season_label

st.set_page_config(page_title="Matchups", layout="wide")


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


def mmss(secs: float) -> str:
    return f"{int(secs // 60)}:{int(secs % 60):02d}"


def main() -> None:
    st.title("Matchups")
    if not DB_PATH.exists() or not has_table("marts.matchup_pairs"):
        st.error("marts.matchup_pairs not found. Build it with `python -m nba_platform.marts.matchups`.")
        return
    st.caption("NBA.com matchup data (**official**, 2017-18 → 2024-25): the time each defender was matched with the offensive player, and what "
               "happened meanwhile. Matched time covers only the defender's team defending, and not every second is assigned. "
               "Coverage and gaps: `docs/validation/matchups_coverage.md`.")

    c1, c2 = st.columns(2)
    season_type = c1.radio("Season type", ["playoffs", "regular"], horizontal=True)
    years = query("SELECT DISTINCT season_end_year FROM marts.matchup_pairs WHERE season_type = ? ORDER BY 1 DESC", (season_type,))["season_end_year"].tolist()
    year = c2.selectbox("Season", years, format_func=season_label)

    teams = query("""SELECT DISTINCT t.team_id, t.abbreviation FROM marts.matchup_pairs m JOIN core.teams t USING (team_id)
                     WHERE m.season_end_year = ? AND m.season_type = ? ORDER BY 2""", (year, season_type))
    names = dict(zip(teams["team_id"], teams["abbreviation"]))
    c3, c4 = st.columns(2)
    offense = c3.selectbox("Offensive team", list(names), format_func=names.get)
    opponents = query("""SELECT DISTINCT CASE WHEN g.home_team_id = ? THEN g.away_team_id ELSE g.home_team_id END AS team_id
                         FROM core.games g WHERE g.season_end_year = ? AND g.season_type = ? AND ? IN (g.home_team_id, g.away_team_id)
                         AND g.game_id IN (SELECT game_id FROM marts.matchup_pairs)""", (int(offense), year, season_type, int(offense)))
    opp_names = {t: names.get(t, str(t)) for t in sorted(opponents["team_id"], key=lambda t: names.get(t, ""))}
    if not opp_names:
        st.info("No matchup data for this team.")
        return
    defense = c4.selectbox("Defending team", list(opp_names), format_func=opp_names.get)

    pairs = query("""
        SELECT m.game_id, g.game_date, g.home_team_id = ? AS offense_home, m.offender_id, o.name AS offender, m.defender_id, d.name AS defender,
               m.matchup_secs, m.partial_possessions, m.player_pts, m.fgm, m.fga, m.fg3m, m.fg3a, m.assists, m.turnovers, m.shooting_fouls, m.switches_on
        FROM marts.matchup_pairs m JOIN core.games g USING (game_id)
        JOIN core.players o ON o.player_id = m.offender_id JOIN core.players d ON d.player_id = m.defender_id
        WHERE g.season_end_year = ? AND g.season_type = ? AND m.team_id = ? AND ? IN (g.home_team_id, g.away_team_id)""",
                  (int(offense), year, season_type, int(defense), int(offense)))
    if pairs.empty:
        st.info("No matchup data for this pairing.")
        return
    games = pairs["game_id"].nunique()
    st.caption(f"{games} game(s) between {names[offense]} and {opp_names[defense]} with matchup data.")

    guarded = pairs.groupby(["offender_id", "offender"]).agg(secs=("matchup_secs", "sum")).reset_index().sort_values("secs", ascending=False)
    options = dict(zip(guarded["offender_id"], guarded["offender"]))
    player = st.selectbox("Offensive player (most guarded time first)", list(options), format_func=options.get)
    mine = pairs[pairs["offender_id"] == player]

    st.header("Who guarded him (all games shown)")
    total = mine["matchup_secs"].sum()
    by_def = (mine.groupby("defender").agg(secs=("matchup_secs", "sum"), poss=("partial_possessions", "sum"), pts=("player_pts", "sum"),
                                           fgm=("fgm", "sum"), fga=("fga", "sum"), fg3m=("fg3m", "sum"), fg3a=("fg3a", "sum"),
                                           ast=("assists", "sum"), tov=("turnovers", "sum"), fouls=("shooting_fouls", "sum"),
                                           switches=("switches_on", "sum")).reset_index().sort_values("secs", ascending=False))
    by_def.insert(2, "share", by_def["secs"] / total)
    by_def["secs"] = by_def["secs"].map(mmss)
    by_def["fg"] = by_def["fgm"].astype(int).astype(str) + "-" + by_def["fga"].astype(int).astype(str)
    by_def["fg3"] = by_def["fg3m"].astype(int).astype(str) + "-" + by_def["fg3a"].astype(int).astype(str)
    st.dataframe(by_def[["defender", "secs", "share", "poss", "pts", "fg", "fg3", "ast", "tov", "fouls", "switches"]], hide_index=True, width="stretch",
                 column_config={"secs": st.column_config.TextColumn("MIN", help="time matched with him"),
                                "share": st.column_config.ProgressColumn("share of his guarded time", format="percent", min_value=0, max_value=1),
                                "poss": st.column_config.NumberColumn("partial poss.", format="%.1f"), "pts": st.column_config.NumberColumn("PTS", format="%d"),
                                "fg": "FG", "fg3": "3P", "ast": "AST", "tov": "TOV", "fouls": "shooting fouls", "switches": "switches onto him"})
    st.caption("Matched time and points are NBA.com's, counted while that defender was matched with him; small samples are noisy, "
               "so matchup time and its share are the primary signal.")

    st.header("Game by game: share of his guarded time")
    per_game = mine.groupby(["game_id", "game_date", "offense_home", "defender"]).agg(secs=("matchup_secs", "sum")).reset_index()
    per_game["share"] = per_game["secs"] / per_game.groupby("game_id")["secs"].transform("sum")
    top = by_def.head(6)["defender"].tolist()
    wide = per_game[per_game["defender"].isin(top)].pivot(index=["game_date", "offense_home"], columns="defender", values="share")
    wide = wide[[d for d in top if d in wide.columns]].fillna(0.0).reset_index().sort_values("game_date")
    wide["game_date"] = wide["game_date"].astype(str).str[:10]
    wide.insert(1, "site", wide.pop("offense_home").map({True: "home", False: "away"}))
    mins = per_game.groupby("game_date")["secs"].sum().rename("matched")
    wide["matched"] = (pd.to_datetime(wide["game_date"]).map(lambda d: mins.get(d, float("nan"))) / 60.0).round(1)
    st.dataframe(wide, hide_index=True, width="stretch", column_config={
        **{d: st.column_config.ProgressColumn(d, format="percent", min_value=0, max_value=1) for d in top},
        "site": "site", "matched": st.column_config.NumberColumn("matched MIN", format="%.1f")})


main()
