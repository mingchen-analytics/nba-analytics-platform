"""Data health dashboard (internal tool): load status and validation results per season.

Opens the DuckDB database **read-only** and shows no player metrics.

Run:
    .venv/Scripts/streamlit run app/data_health.py
"""

from __future__ import annotations

import json

import duckdb
import pandas as pd
import streamlit as st

from nba_platform.db import DB_PATH
from nba_platform.seasons import season_label

st.set_page_config(page_title="Data health", layout="wide")


@st.cache_resource
def connection() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DB_PATH), read_only=True)


@st.cache_data(ttl=300)
def query(sql: str) -> pd.DataFrame:
    return connection().execute(sql).df()


def status_cell(level: str, status: str) -> str:
    if status == "pass":
        return "pass"
    if status == "skip":
        return "skip"
    if status == "known":
        return "known gap"
    return "FAIL" if level == "hard" else "warning"


def main() -> None:
    st.title("Data health")
    st.caption(f"Database: `{DB_PATH}` (read-only). Internal tool: load status and validation only.")
    if not DB_PATH.exists():
        st.error("Database not found. Build it with `python -m nba_platform.pipeline --all`.")
        return

    results = query("""
        SELECT season_end_year, season_type, check_id, check_name, level, status, n_checked, n_failed, detail
        FROM validation.results""")
    counts = query("""
        SELECT g.season_end_year, g.season_type, count(DISTINCT g.game_id) AS games,
               (SELECT count(*) FROM core.events e WHERE e.game_id IN
                   (SELECT game_id FROM core.games g2 WHERE g2.season_end_year = g.season_end_year
                    AND g2.season_type = g.season_type)) AS events,
               (SELECT count(*) FROM core.shots s WHERE s.game_id IN
                   (SELECT game_id FROM core.games g3 WHERE g3.season_end_year = g.season_end_year
                    AND g3.season_type = g.season_type)) AS shots
        FROM core.games g GROUP BY ALL""")

    seasons = results[["season_end_year", "season_type"]].drop_duplicates()
    hard_fail = (results[(results["level"] == "hard") & (results["status"] == "fail") & (~results["check_id"].isin([107, 108]))]
                 [["season_end_year", "season_type"]].drop_duplicates().assign(hard=True))
    summary = (seasons.merge(counts, how="left").merge(hard_fail, how="left")
               .fillna({"games": 0, "events": 0, "shots": 0, "hard": False}))
    summary["hard"] = summary["hard"].astype(bool)   # object after the merge; `~` on Python bools is deprecated
    summary["status"] = summary["hard"].map({True: "not loaded (hard fail)", False: "loaded"})
    summary["season"] = summary["season_end_year"].map(season_label)
    results["cell"] = [status_cell(lv, s) for lv, s in zip(results["level"], results["status"])]
    pivot = results.pivot_table(index=["season_end_year", "season_type"], columns="check_id", values="cell",
                                aggfunc="first").reset_index()
    pivot.columns = [c if isinstance(c, str) else f"check {c}" for c in pivot.columns]
    table = summary.merge(pivot, on=["season_end_year", "season_type"], how="left")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Season files", f"{len(summary)}")
    c2.metric("Loaded", f"{int((~summary['hard']).sum())}")
    c3.metric("Games", f"{int(summary['games'].sum()):,}")
    c4.metric("Events", f"{int(summary['events'].sum()):,}")

    season_type = st.radio("Season type", ["regular", "playoffs"], horizontal=True)
    shown = table[table["season_type"] == season_type].sort_values("season_end_year")
    check_cols = sorted([c for c in shown.columns if c.startswith("check ")], key=lambda c: int(c.split()[1]))
    st.dataframe(
        shown[["season", "status", "games", "events", "shots"] + check_cols],
        hide_index=True, width="stretch",
        column_config={"games": st.column_config.NumberColumn(format="%d"),
                       "events": st.column_config.NumberColumn(format="%d"),
                       "shots": st.column_config.NumberColumn(format="%d")},
    )
    st.caption("pass · warning = anomaly reported, season loaded · known gap = documented in corrections/known_gaps.csv · FAIL = hard check failed, season not loaded · skip")

    st.subheader("Season detail")
    options = shown["season"].tolist()
    if not options:
        return
    pick = st.selectbox("Season", options, index=len(options) - 1)
    y = int(shown.loc[shown["season"] == pick, "season_end_year"].iloc[0])
    detail = results[(results["season_end_year"] == y) & (results["season_type"] == season_type)].sort_values(
        ["level", "check_id"])
    st.dataframe(detail[["check_id", "check_name", "level", "status", "n_checked", "n_failed"]],
                 hide_index=True, width="stretch")
    for r in detail[detail["status"] != "pass"].itertuples(index=False):
        with st.expander(f"check {r.check_id} — {r.check_name} ({r.status})"):
            st.json(json.loads(r.detail) if r.detail else {})


main()
