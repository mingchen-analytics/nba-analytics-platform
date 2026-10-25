"""RAPM (layer 3): regularized adjusted plus-minus from our own possessions, with standard errors, two variants and career curves.

Opens the DuckDB database **read-only** and reads only marts (marts.player_rapm, marts.rapm_windows). Ratings are points per 100
possessions relative to an average player, **modelled** (ridge regression, `metrics/rapm.py`), not counted.
"""

from __future__ import annotations

import re

import duckdb
import pandas as pd
import streamlit as st

from nba_platform.db import DB_PATH
from nba_platform.seasons import season_label

st.set_page_config(page_title="RAPM", layout="wide")

VARIANT_LABEL = {"luck_adjusted": "luck-adjusted", "raw": "raw (points as scored)"}


@st.cache_resource
def connection() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DB_PATH), read_only=True)


@st.cache_data(ttl=300)
def query(sql: str, params: tuple = ()) -> pd.DataFrame:
    return connection().execute(sql, list(params)).df()


def has_table(name: str) -> bool:
    schema, table = name.split(".")
    return bool(query("SELECT count(*) AS n FROM information_schema.tables WHERE table_schema = ? AND table_name = ?", (schema, table))["n"].iloc[0])


def window_end_year(window_id: str) -> int:
    """'2022-23 + 2023-24 + 2024-25 regular' -> 2025 (the season the window ends with)."""
    return int(re.findall(r"(\d{4})-\d{2}", window_id)[-1]) + 1


def window_kind(window_id: str) -> str:
    return "three seasons" if " + " in window_id else "one season"


def main() -> None:
    st.title("RAPM")
    if not DB_PATH.exists() or not has_table("marts.player_rapm") or not has_table("marts.rapm_windows"):
        st.error("marts.player_rapm / marts.rapm_windows not found. Fit them with `python -m nba_platform.metrics.rapm --all-windows`.")
        return
    variants = query("SELECT DISTINCT variant FROM marts.player_rapm ORDER BY variant DESC")["variant"].tolist()
    variant = st.radio("Variant", variants, format_func=VARIANT_LABEL.get, horizontal=True,
                       help="Luck-adjusted: every three-point attempt counts 3 x the shooter's expected percentage and every free throw his expected percentage "
                            "(his season rate shrunk toward the league's), so the defenders' share of shooting luck is removed. Raw: the points that were scored.")
    diag = query("SELECT * FROM marts.rapm_windows WHERE variant = ?", (variant,))
    if diag.empty:
        st.info("No window of this variant fitted yet.")
        return
    diag["end_year"] = diag["window_id"].map(window_end_year)
    diag["kind"] = diag["window_id"].map(window_kind)
    st.caption("**Modelled**, not counted: ridge regression on our own possessions (end-of-period heaves and garbage time excluded; the whole possession goes to the lineup "
               "on the floor when it ends; penalty chosen by cross-validation grouped by game; players with few possessions share a replacement column). "
               "Points per 100 possessions relative to an average player; defense is positive when good. A window of three seasons ends with the season shown "
               "and uses only that season and the two before it.")
    st.warning("Ridge shrinks every player toward the average and the ratings are noisy. Split-half reliability (two random halves of the games): see the table below; "
               "differences smaller than the standard errors are noise.")

    board_tab, career_tab, windows_tab = st.tabs(["Leaderboard", "Career", "Windows"])

    with board_tab:
        c0, c1 = st.columns(2)
        kind = c0.radio("Window", ["three seasons", "one season"], horizontal=True, key="board_kind")
        years = sorted(diag.loc[diag["kind"] == kind, "end_year"].unique(), reverse=True)
        if not years:
            st.info("No window of this kind yet.")
        else:
            year = c1.selectbox("Season (the window ends with it)", years, format_func=season_label)
            window = diag.loc[(diag["kind"] == kind) & (diag["end_year"] == year), "window_id"].iloc[0]
            meta = query("""SELECT any_value(alpha) AS alpha, any_value(n_obs) AS n_obs, any_value(home_points_per100) AS home, any_value(credit_method) AS credit,
                                   any_value(rules_version) AS version, any_value(rules_profile) AS profile, any_value(min_possessions_for_own_column) AS min_poss
                            FROM marts.player_rapm WHERE window_id = ? AND variant = ?""", (window, variant)).iloc[0]
            d = diag.loc[diag["window_id"] == window].iloc[0]
            st.caption(f"{window}: {int(meta['n_obs']):,} possessions (rules {meta['version']}, profile `{meta['profile']}`); penalty {meta['alpha']:,.0f}; credit `{meta['credit']}`; "
                       f"home court {meta['home']:+.2f} points per 100; players below {int(meta['min_poss'])} possessions share a replacement column. "
                       f"Split-half reliability {d['split_half_r']:.2f} (players with 1,000+ possessions in both halves: {int(d['split_half_players'])}).")
            m1, m2, m3 = st.columns(3)
            min_poss = m1.slider("Minimum possessions (offense + defense)", 0, 20000, 2000 if kind == "three seasons" else 1000, step=250)
            sort_by = m2.selectbox("Sort by", ["rapm", "o_rapm", "d_rapm"], format_func=lambda c: {"rapm": "RAPM", "o_rapm": "offense", "d_rapm": "defense"}[c])
            clear = m3.toggle("Only players more than 2 standard errors from zero", value=False)
            board = query(f"""
                SELECT p.name AS player, r.off_poss + r.def_poss AS poss, r.rapm, r.rapm_se, r.o_rapm, r.o_se, r.d_rapm, r.d_se
                FROM marts.player_rapm r JOIN core.players p USING (player_id)
                WHERE r.window_id = ? AND r.variant = ? AND r.off_poss + r.def_poss >= ?{" AND abs(r.rapm) > 2 * r.rapm_se" if clear else ""}
                ORDER BY r.{sort_by} DESC""", (window, variant, min_poss))
            st.caption(f"{len(board)} players.")
            st.dataframe(board, hide_index=True, width="stretch", column_config={
                "poss": st.column_config.NumberColumn("possessions", format="%d"),
                "rapm": st.column_config.NumberColumn("RAPM", format="%+.2f"), "rapm_se": st.column_config.NumberColumn("± SE", format="%.2f"),
                "o_rapm": st.column_config.NumberColumn("offense", format="%+.2f"), "o_se": st.column_config.NumberColumn("± SE", format="%.2f"),
                "d_rapm": st.column_config.NumberColumn("defense", format="%+.2f"), "d_se": st.column_config.NumberColumn("± SE", format="%.2f")})
            if not board.empty:
                st.header("Offense and defense")
                st.scatter_chart(board, x="o_rapm", y="d_rapm", x_label="offense (points per 100)", y_label="defense (points per 100; positive = good)")

    with career_tab:
        names = query("""SELECT r.player_id, p.name, max(r.off_poss + r.def_poss) AS poss FROM marts.player_rapm r JOIN core.players p USING (player_id)
                         WHERE r.variant = ? GROUP BY 1, 2 HAVING max(r.off_poss + r.def_poss) >= 3000 ORDER BY 2""", (variant,))
        by_name = dict(zip(names["player_id"], names["name"]))
        c0, c1 = st.columns([2, 1])
        player = c0.selectbox("Player (3,000+ possessions in some window)", list(by_name), format_func=by_name.get)
        kind = c1.radio("Window", ["three seasons", "one season"], horizontal=True, key="career_kind")
        hist = query("""SELECT r.window_id, r.rapm, r.rapm_se, r.o_rapm, r.d_rapm, r.off_poss + r.def_poss AS poss FROM marts.player_rapm r
                        WHERE r.player_id = ? AND r.variant = ?""", (int(player), variant))
        hist["kind"] = hist["window_id"].map(window_kind)
        hist["end_year"] = hist["window_id"].map(window_end_year)
        hist = hist[hist["kind"] == kind].sort_values("end_year")
        if hist.empty:
            st.info("No window of this kind for this player.")
        else:
            curve = hist.assign(season=hist["end_year"].map(season_label), low=hist["rapm"] - 2 * hist["rapm_se"], high=hist["rapm"] + 2 * hist["rapm_se"]).set_index("season")
            st.line_chart(curve[["rapm", "low", "high"]])
            st.caption("RAPM with a band of two standard errors (sampling noise only). A three-season window shares two of its seasons with the next one, so neighbouring points are not independent.")
            st.dataframe(hist[["end_year", "poss", "rapm", "rapm_se", "o_rapm", "d_rapm"]].assign(season=hist["end_year"].map(season_label)).drop(columns="end_year")
                         [["season", "poss", "rapm", "rapm_se", "o_rapm", "d_rapm"]], hide_index=True, width="stretch", column_config={
                "poss": st.column_config.NumberColumn("possessions", format="%d"), "rapm": st.column_config.NumberColumn("RAPM", format="%+.2f"),
                "rapm_se": st.column_config.NumberColumn("± SE", format="%.2f"), "o_rapm": st.column_config.NumberColumn("offense", format="%+.2f"),
                "d_rapm": st.column_config.NumberColumn("defense", format="%+.2f")})

    with windows_tab:
        st.caption("How well each window is determined: possessions, the penalty chosen by cross-validation, the gain of the cross-validated error over predicting the mean, "
                   "and the split-half reliability of the ratings (correlation between two random halves of the games).")
        table = diag.sort_values(["kind", "end_year"], ascending=[True, False])[["kind", "end_year", "n_obs", "players", "alpha", "cv_improvement_pct", "split_half_r", "split_half_r_o", "split_half_r_d"]]
        table = table.assign(season=table["end_year"].map(season_label)).drop(columns="end_year")[["kind", "season", "n_obs", "players", "alpha", "cv_improvement_pct", "split_half_r", "split_half_r_o", "split_half_r_d"]]
        st.dataframe(table, hide_index=True, width="stretch", column_config={
            "n_obs": st.column_config.NumberColumn("possessions", format="%d"), "alpha": st.column_config.NumberColumn("penalty", format="%.0f"),
            "cv_improvement_pct": st.column_config.NumberColumn("CV gain %", format="%.2f"), "split_half_r": st.column_config.NumberColumn("reliability", format="%.2f"),
            "split_half_r_o": st.column_config.NumberColumn("offense", format="%.2f"), "split_half_r_d": st.column_config.NumberColumn("defense", format="%.2f")})


main()
