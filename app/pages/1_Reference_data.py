"""Reference data (internal tool): possession-count benchmarks and NBA.com reference coverage.

Opens the DuckDB database **read-only** and shows no player metrics.
"""

from __future__ import annotations

import duckdb
import pandas as pd
import streamlit as st

from nba_platform.db import DB_PATH, PROJECT_ROOT
from nba_platform.seasons import season_label

st.set_page_config(page_title="Reference data", layout="wide")

NBA_TABLES = {
    "team_possessions": "official possessions per team-game (TeamGameLogs Advanced)",
    "tracking": "player tracking (12 measure types)",
    "hustle": "hustle (player + team)",
    "shot_context": "shot context (defender distance, touch time, dribbles, shot clock)",
    "play_type": "play types (Synergy, offense + defense, player + team)",
}
BOX_DIRS = {"box_tracking": "single-game tracking box score", "box_hustle": "single-game hustle box score"}


@st.cache_resource
def connection() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DB_PATH), read_only=True)


@st.cache_data(ttl=300)
def query(sql: str) -> pd.DataFrame:
    return connection().execute(sql).df()


def table_exists(schema: str, name: str) -> bool:
    return bool(query(f"""SELECT count(*) AS n FROM information_schema.tables
                          WHERE table_schema = '{schema}' AND table_name = '{name}'""")["n"].iloc[0])


def benchmark(table: str, exact: str, within1: str, season_type: str) -> pd.DataFrame:
    df = query(f"""SELECT season_end_year, count(*) AS team_games,
                          avg(({exact})::INT) AS diff_0, avg(({within1})::INT) AS diff_le_1
                   FROM reference.{table} WHERE season_type = '{season_type}'
                   GROUP BY 1 ORDER BY 1""")
    df.insert(0, "season", df["season_end_year"].map(season_label))
    return df


def main() -> None:
    st.title("Reference data")
    st.caption(f"Database: `{DB_PATH}` (read-only). Reference sources only — not our possession logic, no player metrics.")
    if not DB_PATH.exists():
        st.error("Database not found. Build it with `python -m nba_platform.pipeline --all`.")
        return

    st.header("Possession-count benchmarks (per team-game)")
    st.markdown(
        "ramirobentes' own possession counts compared with **pbpstats** (minus possessions starting with "
        "≤ 2 s left and 0 points) and with the **NBA official** `POSS`. The break at **2016-17** comes from "
        "ramirobentes' processing pipeline (2020-21 playoffs used the old pipeline and follow the pre-2016 "
        "pattern). The main reference for our possession code is **pbpstats** (`docs/decisions.md`)."
    )
    season_type = st.radio("Season type", ["regular", "playoffs"], horizontal=True)
    frames = {}
    if table_exists("reference", "possession_count_benchmark"):
        frames["vs pbpstats"] = benchmark("possession_count_benchmark", "abs(diff) = 0", "abs(diff) <= 1", season_type)
    if table_exists("reference", "possession_count_benchmark_official"):
        frames["vs NBA official"] = benchmark("possession_count_benchmark_official", "abs(diff) < 0.5",
                                              "abs(diff) < 1.5", season_type)
    if not frames:
        st.info("No benchmark tables yet (overnight batch tasks D and G).")
    else:
        chart = pd.concat([f.set_index("season")["diff_0"].rename(name) for name, f in frames.items()], axis=1)
        st.line_chart(chart, y_label="share of team-games with identical counts")
        cols = st.columns(len(frames))
        for col, (name, f) in zip(cols, frames.items()):
            with col:
                st.subheader(name)
                st.dataframe(f.drop(columns="season_end_year"), hide_index=True, width="stretch",
                             column_config={"diff_0": st.column_config.NumberColumn("diff 0", format="percent"),
                                            "diff_le_1": st.column_config.NumberColumn("diff ≤ 1", format="percent")})

    st.header("NBA.com reference tables")
    rows = []
    for name, what in NBA_TABLES.items():
        if table_exists("reference", f"nba_{name}"):
            r = query(f"SELECT count(*) AS n, count(DISTINCT season) AS seasons, min(season) AS first, "
                      f"max(season) AS last FROM reference.nba_{name}").iloc[0]
            rows.append({"table": f"reference.nba_{name}", "data": what, "rows": int(r["n"]),
                         "seasons": int(r["seasons"]), "first": r["first"], "last": r["last"]})
        else:
            rows.append({"table": f"reference.nba_{name}", "data": what, "rows": None, "seasons": None,
                         "first": "not loaded", "last": ""})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    st.header("Single-game box scores")
    loaded = []
    for t in ("nba_box_tracking", "nba_box_hustle"):
        if table_exists("reference", t):
            loaded.append(query(f"""SELECT '{t}' AS table_name, season, season_type, count(DISTINCT game_id) AS games,
                                           count(*) AS player_rows FROM reference.{t} GROUP BY ALL ORDER BY season DESC"""))
    if loaded:
        st.subheader("Loaded into DuckDB")
        st.dataframe(pd.concat(loaded, ignore_index=True), hide_index=True, width="stretch")
    st.subheader("Raw JSON files downloaded")
    base = PROJECT_ROOT / "data" / "raw" / "nba_api"
    counts = []
    for d, what in BOX_DIRS.items():
        for season_dir in sorted((base / d).glob("*")) if (base / d).exists() else []:
            counts.append({"data": what, "season": season_dir.name, "files": sum(1 for _ in season_dir.glob("*.json"))})
    if counts:
        st.dataframe(pd.DataFrame(counts).pivot_table(index="season", columns="data", values="files", fill_value=0)
                     .sort_index(ascending=False), width="stretch")
    else:
        st.info("No single-game box scores downloaded yet.")


main()
