"""RAPM prototype: regularized adjusted plus-minus from our own possessions (ridge regression).

One observation per possession: y = the points the offense scored in it. Features: for each player an
offense column (+1 when he is one of the five on offense) and a defense column (+1 when he is one of the
five on defense), and one home-court column (+1 when the offense is the home team). Ridge regression
(scikit-learn, scipy.sparse) with an intercept (the league average). The penalty is chosen by
cross-validation **grouped by game** (CLAUDE.md Phase 6): the grid starts at the range in config/rules.yaml
`rapm` and is extended while the best value lies at an edge; there is no fixed range.

Players with fewer than `min_possessions_for_own_column` possessions (offense + defense, in the window) share
one "replacement" column on each side. Possessions flagged as end-of-period heaves or garbage time are left out
when the config says so. The whole possession, free throws included, goes to the lineup on the floor when it
ends (option A of the open substitution-credit question). Every choice is a configuration value, recorded on
every output row.

Units: coefficients are points per possession; the reported ratings are per 100 possessions. `o_rapm` is the
points per 100 possessions a player adds on offense, `d_rapm` the points per 100 he prevents on defense
(positive = good; the sign of the defense coefficient is flipped), `rapm` = `o_rapm + d_rapm`.

Prototype: `marts.player_rapm` is a new table, waiting for the owner's approval. Not a final metric: the ridge
has no standard errors; `docs/validation/rapm_<window>.md` shows cross-validation, split-half reliability and
how much the choices matter.

Usage:
    python -m nba_platform.metrics.rapm [--seasons 2025:regular,2024:regular] [--report]   # report: docs/validation/rapm_<window>.md
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold

from nba_platform import db
from nba_platform.rules import load_rules
from nba_platform.seasons import season_label

REPLACEMENT = 0            # player id of the shared low-possession column (never a real NBA id)
HOME = "home_court"
OFF_COLS = [f"off_{i}" for i in range(1, 6)]
DEF_COLS = [f"def_{i}" for i in range(1, 6)]


class RapmError(RuntimeError):
    """The RAPM fit cannot be done as is."""


# ------------------------------------------------------------------ data


def load_possessions(con, seasons: list[tuple[int, str]], cfg: dict) -> pd.DataFrame:
    """One row per possession of the window: game_id, season_end_year, points, offense_is_home, off_1..5, def_1..5.

    The five players of each side are those of the stint on the floor when the possession ends.
    """
    if not seasons:
        raise RapmError("no seasons given")
    where = " OR ".join(["(g.season_end_year = ? AND g.season_type = ?)"] * len(seasons))
    params = [x for season in seasons for x in season]
    flags = ""
    if cfg["exclude_end_of_period_heave"]:
        flags += " AND NOT p.is_end_of_period_heave"
    if cfg["exclude_garbage_time"]:
        flags += " AND NOT p.is_garbage_time"
    home, away = "s.home_p1, s.home_p2, s.home_p3, s.home_p4, s.home_p5", "s.away_p1, s.away_p2, s.away_p3, s.away_p4, s.away_p5"
    df = con.execute(f"""
        WITH e AS (SELECT game_id, possession_id, arg_max(stint_id, segment_seq) AS end_stint
                   FROM core.possession_stint_segments GROUP BY ALL)
        SELECT p.game_id, g.season_end_year, p.points, p.offense_team_id = g.home_team_id AS offense_is_home,
               CASE WHEN p.offense_team_id = g.home_team_id THEN [{home}] ELSE [{away}] END AS off,
               CASE WHEN p.offense_team_id = g.home_team_id THEN [{away}] ELSE [{home}] END AS def
        FROM core.possessions p JOIN core.games g USING (game_id)
        JOIN e ON e.game_id = p.game_id AND e.possession_id = p.possession_id
        JOIN core.stints s ON s.game_id = p.game_id AND s.stint_id = e.end_stint
        WHERE ({where}){flags}
        ORDER BY p.game_id, p.possession_id""", params).df()
    if df.empty:
        raise RapmError(f"no possessions for {seasons}")
    off, de = np.array(df.pop("off").tolist()), np.array(df.pop("def").tolist())
    for i in range(5):
        df[OFF_COLS[i]], df[DEF_COLS[i]] = off[:, i], de[:, i]
    return df


# ------------------------------------------------------------------ design


def bucket_players(obs: pd.DataFrame, min_possessions: int) -> pd.DataFrame:
    """Possessions on the floor per player (offense + defense). Returns player_id, off_poss, def_poss, own_column."""
    off = pd.Series(obs[OFF_COLS].to_numpy().ravel()).value_counts().rename("off_poss")
    de = pd.Series(obs[DEF_COLS].to_numpy().ravel()).value_counts().rename("def_poss")
    players = pd.concat([off, de], axis=1).fillna(0).astype(int).rename_axis("player_id").reset_index()
    players["own_column"] = players["off_poss"] + players["def_poss"] >= min_possessions
    return players.sort_values("player_id").reset_index(drop=True)


def design_matrix(obs: pd.DataFrame, own_players: np.ndarray) -> tuple[sparse.csr_matrix, list[str]]:
    """Sparse X: [offense columns | defense columns | replacement offense, replacement defense | home court].

    A player without his own column adds 1 to the replacement column of his side (so a possession with three
    of them adds 3). Returns X and the column names.
    """
    index = {int(p): i for i, p in enumerate(own_players)}
    n_own, n = len(own_players), len(obs)
    names = [f"off:{p}" for p in own_players] + [f"def:{p}" for p in own_players] + ["off:replacement", "def:replacement", HOME]
    rep_off, rep_def, home_col = 2 * n_own, 2 * n_own + 1, 2 * n_own + 2
    rows, cols = [], []
    for side, columns, shift, rep in (("off", OFF_COLS, 0, rep_off), ("def", DEF_COLS, n_own, rep_def)):
        block = obs[columns].to_numpy()
        for k in range(5):
            idx = np.fromiter((index.get(int(p), -1) for p in block[:, k]), dtype=np.int64, count=n)
            rows.append(np.arange(n))
            cols.append(np.where(idx >= 0, idx + shift, rep))
    rows.append(np.arange(n)[obs["offense_is_home"].to_numpy(dtype=bool)])
    cols.append(np.full(len(rows[-1]), home_col))
    r, c = np.concatenate(rows), np.concatenate(cols)
    x = sparse.coo_matrix((np.ones(len(r)), (r, c)), shape=(n, 2 * n_own + 3)).tocsr()   # duplicates are summed
    return x, names


# ------------------------------------------------------------------ penalty


def alpha_grid(cfg: dict) -> np.ndarray:
    return np.logspace(cfg["alpha_log10_start"], cfg["alpha_log10_stop"], int(cfg["alpha_grid_size"]))


def cv_alpha(x, y: np.ndarray, groups: np.ndarray, cfg: dict) -> dict:
    """Choose the ridge penalty by cross-validation grouped by game; extend the grid while the best value sits at an edge.

    Returns {alpha, table (alpha, mean_mse, se_mse), baseline_mse, extensions}. The baseline predicts each fold's
    training mean.
    """
    folds = list(GroupKFold(n_splits=int(cfg["cv_folds"]), shuffle=True, random_state=int(cfg["seed"])).split(x, y, groups))
    baseline = float(np.mean([np.mean((y[te] - y[tr].mean()) ** 2) for tr, te in folds]))
    grid, results, extensions = list(alpha_grid(cfg)), {}, 0
    step = (cfg["alpha_log10_stop"] - cfg["alpha_log10_start"]) / (int(cfg["alpha_grid_size"]) - 1)
    while True:
        for a in grid:
            if a in results:
                continue
            mse = [np.mean((y[te] - Ridge(alpha=a, solver="sparse_cg", random_state=0).fit(x[tr], y[tr]).predict(x[te])) ** 2) for tr, te in folds]
            results[a] = (float(np.mean(mse)), float(np.std(mse, ddof=1) / np.sqrt(len(mse))))
        best = min(results, key=lambda a: results[a][0])
        ordered = sorted(results)
        if extensions >= int(cfg["max_grid_extensions"]) or ordered[0] < best < ordered[-1]:
            break
        extensions += 1
        new = [ordered[-1] * 10 ** (step * i) for i in range(1, 4)] if best == ordered[-1] else [ordered[0] / 10 ** (step * i) for i in range(1, 4)]
        grid = new
    table = pd.DataFrame([(a, m, se) for a, (m, se) in sorted(results.items())], columns=["alpha", "mean_mse", "se_mse"])
    return {"alpha": float(best), "table": table, "baseline_mse": baseline, "extensions": extensions,
            "at_edge": best in (ordered[0], ordered[-1])}


# ------------------------------------------------------------------ fit


def fit(obs: pd.DataFrame, cfg: dict, alpha: float | None = None) -> dict:
    """Fit RAPM on possession observations. Returns players (DataFrame), alpha, cv, home_points, n_obs."""
    players = bucket_players(obs, int(cfg["min_possessions_for_own_column"]))
    own = players.loc[players["own_column"], "player_id"].to_numpy()
    if len(own) == 0:
        raise RapmError("no player reaches min_possessions_for_own_column")
    x, names = design_matrix(obs, own)
    y = obs["points"].to_numpy(dtype=float)
    cv = None
    if alpha is None:
        cv = cv_alpha(x, y, obs["game_id"].to_numpy(), cfg)
        alpha = cv["alpha"]
    model = Ridge(alpha=alpha, solver="sparse_cg", random_state=0).fit(x, y)
    coef = pd.Series(model.coef_, index=names)
    n_own = len(own)
    out = players.loc[players["own_column"], ["player_id", "off_poss", "def_poss"]].reset_index(drop=True)
    out["o_rapm"] = 100.0 * coef.iloc[:n_own].to_numpy()
    out["d_rapm"] = -100.0 * coef.iloc[n_own:2 * n_own].to_numpy()
    out["rapm"] = out["o_rapm"] + out["d_rapm"]
    return {"players": out, "alpha": float(alpha), "cv": cv, "n_obs": len(obs), "n_own": n_own,
            "n_replacement": int((~players["own_column"]).sum()), "intercept_per100": 100.0 * float(model.intercept_),
            "home_points_per100": 100.0 * float(coef[HOME]),
            "replacement_o": 100.0 * float(coef["off:replacement"]), "replacement_d": -100.0 * float(coef["def:replacement"])}


def split_half(obs: pd.DataFrame, cfg: dict, alpha: float) -> dict:
    """Reliability: fit on two random halves of the games with the same penalty; correlate the players in both."""
    games = np.array(obs["game_id"].unique(), dtype=object)
    rng = np.random.default_rng(int(cfg["seed"]))
    rng.shuffle(games)
    half = set(games[: len(games) // 2])
    mask = obs["game_id"].isin(half).to_numpy()
    a, b = fit(obs[mask], cfg, alpha)["players"], fit(obs[~mask], cfg, alpha)["players"]
    m = a.merge(b, on="player_id", suffixes=("_a", "_b"))
    m = m[(m["off_poss_a"] + m["def_poss_a"] >= cfg["split_half_min_possessions"]) & (m["off_poss_b"] + m["def_poss_b"] >= cfg["split_half_min_possessions"])]
    if len(m) < 3:
        return {"players": len(m), "r_rapm": None, "r_o": None, "r_d": None}
    return {"players": len(m), "r_rapm": float(m["rapm_a"].corr(m["rapm_b"])), "r_o": float(m["o_rapm_a"].corr(m["o_rapm_b"])),
            "r_d": float(m["d_rapm_a"].corr(m["d_rapm_b"]))}


# ------------------------------------------------------------------ mart


DDL = """(
    window_id TEXT NOT NULL, player_id INTEGER NOT NULL, off_poss INTEGER NOT NULL, def_poss INTEGER NOT NULL,
    o_rapm DOUBLE NOT NULL, d_rapm DOUBLE NOT NULL, rapm DOUBLE NOT NULL,
    alpha DOUBLE NOT NULL, n_obs INTEGER NOT NULL, home_points_per100 DOUBLE NOT NULL,
    credit_method TEXT NOT NULL, exclude_end_of_period_heave BOOLEAN NOT NULL, exclude_garbage_time BOOLEAN NOT NULL,
    min_possessions_for_own_column INTEGER NOT NULL, rules_version TEXT NOT NULL, rules_profile TEXT NOT NULL,
    PRIMARY KEY (window_id, player_id))"""


def window_id(seasons: list[tuple[int, str]]) -> str:
    """'2025-26 regular' or '2023-24 + 2024-25 + 2025-26 regular' (all of one season type) or a plain list."""
    types = {t for _, t in seasons}
    years = sorted(y for y, _ in seasons)
    label = " + ".join(season_label(y) for y in years)
    return f"{label} {types.pop()}" if len(types) == 1 else ", ".join(f"{season_label(y)} {t}" for y, t in seasons)


def build(con, seasons: list[tuple[int, str]], cfg: dict | None = None) -> dict:
    """Fit one window and write its rows to marts.player_rapm (replacing that window's rows). Returns a summary."""
    cfg = cfg or load_rules()["rapm"]
    versions = con.execute("SELECT DISTINCT rules_version, rules_profile FROM core.possessions").fetchall()
    if len(versions) != 1:
        raise RapmError(f"core.possessions holds {len(versions)} rules versions / profiles; expected exactly one: {versions}")
    obs = load_possessions(con, seasons, cfg)
    res = fit(obs, cfg)
    wid = window_id(seasons)
    rows = res["players"].copy()
    rows.insert(0, "window_id", wid)
    for k, v in (("alpha", res["alpha"]), ("n_obs", res["n_obs"]), ("home_points_per100", res["home_points_per100"]),
                 ("credit_method", cfg["credit"]), ("exclude_end_of_period_heave", bool(cfg["exclude_end_of_period_heave"])),
                 ("exclude_garbage_time", bool(cfg["exclude_garbage_time"])),
                 ("min_possessions_for_own_column", int(cfg["min_possessions_for_own_column"])),
                 ("rules_version", versions[0][0]), ("rules_profile", versions[0][1])):
        rows[k] = v
    con.execute("CREATE SCHEMA IF NOT EXISTS marts")
    con.execute("BEGIN")
    try:
        con.execute(f"CREATE TABLE IF NOT EXISTS marts.player_rapm {DDL}")
        con.execute("DELETE FROM marts.player_rapm WHERE window_id = ?", [wid])
        con.register("rapm_rows", rows)
        con.execute("INSERT INTO marts.player_rapm SELECT * FROM rapm_rows")
        con.unregister("rapm_rows")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return {"window": wid, "observations": res["n_obs"], "players": len(rows), "alpha": round(res["alpha"], 1),
            "grid_extended": res["cv"]["extensions"], "home_points_per100": round(res["home_points_per100"], 2)}


# ------------------------------------------------------------------ report


def write_report(con, path: Path, seasons: list[tuple[int, str]], cfg: dict | None = None) -> dict:
    """docs/validation/rapm_<window>.md: cross-validation, reliability, sensitivity to the choices, sanity checks."""
    cfg = cfg or load_rules()["rapm"]
    names = dict(con.execute("SELECT player_id, name FROM core.players").fetchall())
    obs = load_possessions(con, seasons, cfg)
    res = fit(obs, cfg)
    cv, wid = res["cv"], window_id(seasons)
    half = split_half(obs, cfg, res["alpha"])
    variants = {}
    for label, heave, garbage in (("heaves and garbage time both in", False, False), ("heaves out, garbage time in", True, False)):
        v_cfg = {**cfg, "exclude_end_of_period_heave": heave, "exclude_garbage_time": garbage}
        v = fit(load_possessions(con, seasons, v_cfg), v_cfg, res["alpha"])["players"]
        m = res["players"].merge(v, on="player_id", suffixes=("", "_v"))
        m = m[m["off_poss"] + m["def_poss"] >= cfg["split_half_min_possessions"]]
        variants[label] = (len(m), float(m["rapm"].corr(m["rapm_v"])), float((m["rapm"] - m["rapm_v"]).abs().mean()), float((m["rapm"] - m["rapm_v"]).abs().max()))
    onoff = None
    if con.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'marts' AND table_name = 'player_onoff_season'").fetchone()[0]:
        ws = " OR ".join(["(season_end_year = ? AND season_type = ?)"] * len(seasons))
        o = con.execute(f"""SELECT player_id, sum(on_o_pts) * 100.0 / nullif(sum(on_o_poss), 0) - sum(on_d_pts) * 100.0 / nullif(sum(on_d_poss), 0) AS on_net,
                                   sum(on_o_poss) AS poss FROM marts.player_onoff_season WHERE {ws} GROUP BY 1""", [x for s in seasons for x in s]).df()
        m = res["players"].merge(o, on="player_id")
        m = m[m["poss"] >= cfg["split_half_min_possessions"]]
        onoff = (len(m), float(m["rapm"].corr(m["on_net"])))
    p = res["players"].assign(poss=lambda d: d["off_poss"] + d["def_poss"])
    big = p[p["poss"] >= cfg["split_half_min_possessions"]].copy()
    big["name"] = big["player_id"].map(names)
    top, bottom = big.nlargest(10, "rapm"), big.nsmallest(10, "rapm")
    best = cv["table"].loc[cv["table"]["alpha"] == cv["alpha"]].iloc[0]
    lines = [f"# RAPM prototype: {wid}", "",
             "Ridge regression on our own possessions (`metrics/rapm.py`). Numbers only. **Prototype**: `marts.player_rapm` waits for the owner's "
             "approval; every choice below is `rules.yaml` `rapm` and marked [待確認].", "",
             f"- Observations: **{res['n_obs']:,}** possessions; credit: `{cfg['credit']}`; end-of-period heaves "
             f"{'excluded' if cfg['exclude_end_of_period_heave'] else 'included'}; garbage time {'excluded' if cfg['exclude_garbage_time'] else 'included'}.",
             f"- Players with their own column: **{res['n_own']}**; pooled into the replacement column: {res['n_replacement']} "
             f"(fewer than {cfg['min_possessions_for_own_column']} possessions). Replacement player: offense {res['replacement_o']:+.2f}, defense {res['replacement_d']:+.2f} points per 100.",
             f"- League average: {res['intercept_per100']:.1f} points per 100 possessions; home court: **{res['home_points_per100']:+.2f}** points per 100.", "",
             "## Penalty (cross-validation grouped by game)", "",
             f"Folds: {cfg['cv_folds']}. Chosen alpha: **{cv['alpha']:,.0f}**; grid extended {cv['extensions']} time(s); best at the edge of the grid: {cv['at_edge']}. "
             f"Mean squared error {best['mean_mse']:.5f} (± {best['se_mse']:.5f}) against {cv['baseline_mse']:.5f} for predicting the mean: "
             f"**{100 * (1 - best['mean_mse'] / cv['baseline_mse']):.2f} %** lower (small by nature: points in one possession are mostly luck; "
             "what matters is that the gain is real, larger than its standard error, and the best penalty lies inside the grid).", "",
             "| alpha | mean squared error | standard error |", "|---|---|---|"]
    lines += [f"| {r.alpha:,.0f} | {r.mean_mse:.5f} | {r.se_mse:.5f} |" for r in cv["table"].itertuples()]
    lines += ["", "## Reliability (two random halves of the games, same penalty)", "",
              f"Players with {cfg['split_half_min_possessions']:,}+ possessions in both halves: **{half['players']}**. "
              + (f"Correlation between halves: RAPM **{half['r_rapm']:.2f}**, offense {half['r_o']:.2f}, defense {half['r_d']:.2f}." if half["r_rapm"] is not None else "Too few players."),
              "", "## How much the choices matter", "",
              f"Same penalty, players with {cfg['split_half_min_possessions']:,}+ possessions; RAPM of the configured fit against a variant.", "",
              "| variant | players | correlation | mean abs difference | max abs difference |", "|---|---|---|---|---|"]
    lines += [f"| {k} | {n} | {r:.3f} | {d:.2f} | {mx:.2f} |" for k, (n, r, d, mx) in variants.items()]
    if onoff:
        lines += ["", f"Correlation with the raw on/off net (`marts.player_onoff_season`, {onoff[0]} players): **{onoff[1]:.2f}**."]
    lines += ["", f"## Highest and lowest RAPM (players with {cfg['split_half_min_possessions']:,}+ possessions; points per 100)", "",
              "| | player | RAPM | offense | defense | possessions |", "|---|---|---|---|---|---|"]
    lines += [f"| top | {r.name} | {r.rapm:+.2f} | {r.o_rapm:+.2f} | {r.d_rapm:+.2f} | {r.poss:,} |" for r in top.itertuples()]
    lines += [f"| bottom | {r.name} | {r.rapm:+.2f} | {r.o_rapm:+.2f} | {r.d_rapm:+.2f} | {r.poss:,} |" for r in bottom.itertuples()]
    lines += ["", "Reading: ridge shrinks every player toward the average, so the spread is smaller than raw on/off; there are no standard errors "
              "in this prototype. Interpret differences of a point or two between players as noise.", ""]
    path.write_text(chr(10).join(lines), encoding="utf-8")
    return {"alpha": res["alpha"], "split_half_r": half["r_rapm"], "cv_improvement_pct": round(100 * (1 - best["mean_mse"] / cv["baseline_mse"]), 2)}


def slug(text: str) -> str:
    return re.sub(r"[^0-9a-z]+", "_", text.lower()).strip("_")


def parse_seasons(text: str) -> list[tuple[int, str]]:
    return [(int(a), b) for a, b in (x.split(":") for x in text.split(","))]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seasons", default="2025:regular", help="comma list like 2025:regular,2024:regular (season end years)")
    ap.add_argument("--report", action="store_true", help="also write docs/validation/rapm_<window>.md")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    seasons = parse_seasons(args.seasons)
    con = db.connect()
    try:
        print(build(con, seasons))
        if args.report:
            print(write_report(con, db.PROJECT_ROOT / "docs" / "validation" / f"rapm_{slug(window_id(seasons))}.md", seasons))
    finally:
        con.close()


if __name__ == "__main__":
    main()
