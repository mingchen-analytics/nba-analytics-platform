"""RAPM (layer 3, prototype): regularized adjusted plus-minus from our own possessions, with standard errors.

Opens the DuckDB database **read-only** and reads only marts (marts.player_rapm). Ratings are points per 100
possessions relative to an average player, **modelled** (ridge regression, `metrics/rapm.py`), not counted.
"""

from __future__ import annotations

import duckdb
import pandas as pd
import streamlit as st

from nba_platform.db import DB_PATH

st.set_page_config(page_title="RAPM", layout="wide")


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
    st.title("RAPM (prototype)")
    if not DB_PATH.exists() or not has_table("marts.player_rapm"):
        st.error("marts.player_rapm not found. Fit it with `python -m nba_platform.metrics.rapm --seasons 2025:regular`.")
        return
    windows = query("SELECT window_id, any_value(n_obs) AS n_obs FROM marts.player_rapm GROUP BY 1 ORDER BY max(n_obs) DESC")["window_id"].tolist()
    window = st.selectbox("Window", windows)
    meta = query("""SELECT any_value(alpha) AS alpha, any_value(n_obs) AS n_obs, any_value(home_points_per100) AS home, any_value(credit_method) AS credit,
                           any_value(exclude_end_of_period_heave) AS heave, any_value(exclude_garbage_time) AS garbage,
                           any_value(min_possessions_for_own_column) AS min_poss, any_value(rules_version) AS version, any_value(rules_profile) AS profile
                    FROM marts.player_rapm WHERE window_id = ?""", (window,)).iloc[0]
    st.caption(f"**Modelled**, not counted: ridge regression on {int(meta['n_obs']):,} of our possessions (rules {meta['version']}, profile `{meta['profile']}`; "
               f"penalty {meta['alpha']:,.0f} chosen by cross-validation grouped by game; credit `{meta['credit']}`: the whole possession goes to the lineup on the "
               f"floor when it ends; end-of-period heaves {'excluded' if meta['heave'] else 'included'}, garbage time {'excluded' if meta['garbage'] else 'included'}; "
               f"players with fewer than {int(meta['min_poss'])} possessions share a replacement column). Home court {meta['home']:+.2f} points per 100. "
               "Points per 100 possessions relative to an average player; defense is positive when good.")
    st.warning("Ridge shrinks every player toward the average and the ratings are noisy: a single season's split-half reliability is about 0.4, three seasons about 0.6 "
               "(`docs/validation/rapm_*.md`). Differences smaller than the standard errors are noise.")

    c1, c2, c3 = st.columns(3)
    min_poss = c1.slider("Minimum possessions (offense + defense)", 0, 20000, 2000, step=250)
    sort_by = c2.selectbox("Sort by", ["rapm", "o_rapm", "d_rapm"], format_func=lambda c: {"rapm": "RAPM", "o_rapm": "offense", "d_rapm": "defense"}[c])
    clear = c3.toggle("Only players more than 2 standard errors from zero", value=False)
    has_se = bool(query("SELECT count(*) FILTER (rapm_se IS NOT NULL) AS n FROM marts.player_rapm WHERE window_id = ?", (window,))["n"].iloc[0])
    board = query(f"""
        SELECT p.name AS player, r.off_poss + r.def_poss AS poss, r.rapm, r.rapm_se, r.o_rapm, r.o_se, r.d_rapm, r.d_se
        FROM marts.player_rapm r JOIN core.players p USING (player_id)
        WHERE r.window_id = ? AND r.off_poss + r.def_poss >= ?{" AND abs(r.rapm) > 2 * r.rapm_se" if clear and has_se else ""}
        ORDER BY r.{sort_by} DESC""", (window, min_poss))
    st.caption(f"{len(board)} players.")
    st.dataframe(board, hide_index=True, width="stretch", column_config={
        "poss": st.column_config.NumberColumn("possessions", format="%d"),
        "rapm": st.column_config.NumberColumn("RAPM", format="%+.2f"), "rapm_se": st.column_config.NumberColumn("± SE", format="%.2f"),
        "o_rapm": st.column_config.NumberColumn("offense", format="%+.2f"), "o_se": st.column_config.NumberColumn("± SE", format="%.2f"),
        "d_rapm": st.column_config.NumberColumn("defense", format="%+.2f"), "d_se": st.column_config.NumberColumn("± SE", format="%.2f")})

    st.header("Offense and defense")
    if not board.empty:
        st.scatter_chart(board, x="o_rapm", y="d_rapm", x_label="offense (points per 100)", y_label="defense (points per 100; positive = good)")


main()
