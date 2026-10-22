"""On/off (layer 2): how a team does with a player on the floor and off it, per 100 of our possessions.

Opens the DuckDB database **read-only** and reads only marts (marts.player_onoff_season).
Possession counts are shown next to every rate.
"""

from __future__ import annotations

import duckdb
import pandas as pd
import streamlit as st

from nba_platform.db import DB_PATH
from nba_platform.seasons import season_label

st.set_page_config(page_title="On/off", layout="wide")


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


def select(hide_heaves: bool) -> str:
    """Columns of one row; heaves (0 points by definition) are removed from the possession counts only."""
    poss = {f"{w}_{s}": f"o.{w}_{s}_poss" + (f" - o.{w}_{s}_heave_poss" if hide_heaves else "") for w in ("on", "off") for s in ("o", "d")}
    on_net = f"{rate('o.on_o_pts', poss['on_o'])} - {rate('o.on_d_pts', poss['on_d'])}"
    off_net = f"{rate('o.off_o_pts', poss['off_o'])} - {rate('o.off_d_pts', poss['off_d'])}"
    return f"""o.games AS GP, o.on_secs / 60 AS on_min, {poss['on_o']} AS on_poss,
               {rate('o.on_o_pts', poss['on_o'])} AS on_ortg, {rate('o.on_d_pts', poss['on_d'])} AS on_drtg, {on_net} AS on_net,
               {poss['off_o']} AS off_poss, {off_net} AS off_net, ({on_net}) - ({off_net}) AS on_minus_off"""


CFG = {"on_min": st.column_config.NumberColumn("MIN on", format="%d"),
       "on_poss": st.column_config.NumberColumn("POSS on", format="%d", help="offensive possessions with the player on the floor"),
       "on_ortg": st.column_config.NumberColumn("ORTG on", format="%.1f"), "on_drtg": st.column_config.NumberColumn("DRTG on", format="%.1f"),
       "on_net": st.column_config.NumberColumn("NET on", format="%+.1f"),
       "off_poss": st.column_config.NumberColumn("POSS off", format="%d"), "off_net": st.column_config.NumberColumn("NET off", format="%+.1f"),
       "on_minus_off": st.column_config.NumberColumn("ON − OFF", format="%+.1f")}


def main() -> None:
    st.title("On/off")
    if not DB_PATH.exists() or not has_table("marts.player_onoff_season"):
        st.error("marts.player_onoff_season not found. Build it with `python -m nba_platform.marts.onoff`.")
        return
    meta = query("SELECT any_value(credit_method) AS m, any_value(rules_version) AS v, any_value(rules_profile) AS p "
                 "FROM marts.player_onoff_season").iloc[0]
    st.caption(f"Team points per 100 possessions with the player on and off the floor, **counted from our play-by-play** "
               f"(rules {meta['v']}, profile `{meta['p']}`, credit method `{meta['m']}`: a possession goes to the lineup on the floor "
               "when it ends, free-throw points to the lineup at the foul: pbpstats' method). Crediting every point to the lineup at the end of "
               "the possession instead would move about 7 % of points (`docs/validation/onoff_credit_methods.md`).")

    c1, c2, c3 = st.columns(3)
    season_type = c1.radio("Season type", ["regular", "playoffs"], horizontal=True)
    years = query("SELECT DISTINCT season_end_year FROM marts.player_onoff_season WHERE season_type = ? ORDER BY 1 DESC",
                  (season_type,))["season_end_year"].tolist()
    year = c2.selectbox("Season", years, format_func=season_label)
    teams = query("""SELECT DISTINCT o.team_id, t.abbreviation FROM marts.player_onoff_season o JOIN core.teams t USING (team_id)
                     WHERE o.season_end_year = ? AND o.season_type = ? ORDER BY 2""", (year, season_type))
    team_names = {0: "All teams", **dict(zip(teams["team_id"], teams["abbreviation"]))}
    team = c3.selectbox("Team", list(team_names), format_func=team_names.get)

    c4, c5 = st.columns([2, 1])
    default = 1000 if season_type == "regular" else 150
    min_poss = c4.slider("Minimum offensive possessions on the floor", 0, 4000 if season_type == "regular" else 1500, default, step=50)
    hide = c5.toggle("Exclude end-of-period heaves", value=True,
                     help="0-point possessions starting with 2 s or less left in the period (pbpstats excludes them from efficiency).")

    team_filter = "" if team == 0 else f" AND o.team_id = {int(team)}"
    board = query(f"""
        SELECT o.player_id, p.name AS player, t.abbreviation AS team, {select(hide)}
        FROM marts.player_onoff_season o JOIN core.players p USING (player_id) JOIN core.teams t USING (team_id)
        WHERE o.season_end_year = ? AND o.season_type = ?{team_filter} AND o.on_o_poss >= ?
        ORDER BY on_minus_off DESC NULLS LAST""", (year, season_type, min_poss))
    st.dataframe(board.drop(columns="player_id"), hide_index=True, width="stretch", column_config=CFG)
    if board.empty:
        st.info("No player reaches the minimum number of possessions.")
        return

    st.header("Player across seasons")
    names = board.drop_duplicates("player_id").set_index("player_id")["player"].to_dict()
    player_id = st.selectbox("Player (from the table above)", list(names), format_func=names.get)
    history = query(f"""
        SELECT o.season_end_year, o.season_type, t.abbreviation AS team, {select(hide)}
        FROM marts.player_onoff_season o JOIN core.teams t USING (team_id)
        WHERE o.player_id = ? ORDER BY o.season_end_year, o.season_type DESC, o.on_secs DESC""", (int(player_id),))
    history.insert(0, "season", history.pop("season_end_year").map(season_label))
    st.dataframe(history, hide_index=True, width="stretch", column_config=CFG)


main()
