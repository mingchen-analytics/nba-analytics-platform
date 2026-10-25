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

Two variants of the observation (`variant` in the mart): `raw` uses the points that were scored; `luck_adjusted` replaces the
result of every three-point attempt by 3 x the shooter's expected three-point percentage, and of every free throw by his expected free-throw
percentage (his own season's rate shrunk toward the league's with a prior of `luck_adjustment.*_prior_attempts` attempts). Whether
a three goes in is mostly the shooter's and luck's doing, so the defenders' share of it is mostly noise; adjusting it is the usual
practice of EPM-like metrics. A shot whose type is unknown (no row in `core.shots`) keeps its actual result: never guessed.

Windows: a single season, and the three seasons ending in that season (a trailing window, so that a window never uses the future).
`--all-windows` fits every one of them for both variants (resumable) and `--forecast-report` checks them out of sample.

Standard errors come from a bootstrap of whole games: the games are resampled with replacement (the number of times
a game is drawn becomes the weight of its possessions), the model is refitted with the same penalty, and the standard
error is the standard deviation of a player's rating over the resamples. They describe sampling noise only; they do
not include the bias that ridge shrinkage introduces.

Prototype: `marts.player_rapm` is a new table, waiting for the owner's approval. `docs/validation/rapm_<window>.md`
shows cross-validation, split-half reliability, the standard errors and how much the choices matter.

Usage:
    python -m nba_platform.metrics.rapm [--seasons 2025:regular,2024:regular] [--variant raw|luck_adjusted] [--report]
    python -m nba_platform.metrics.rapm --all-windows [--forecast-report]
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
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


VARIANTS = ("raw", "luck_adjusted")


def _luck_ctes(seasons: list[tuple[int, str]], three_prior: float, ft_prior: float) -> str:
    """CTEs `shots`, `rate`, `adj`: per possession, the expected minus the actual points of its three-point attempts and free throws.

    A shooter's expected rate is his season's (made + prior x league rate) / (attempts + prior); only attempts that have a row in
    core.shots (the type is known) and a shooter are adjusted.
    """
    lit = " OR ".join(f"(g.season_end_year = {int(y)} AND g.season_type = '{t}')" for y, t in seasons)
    return f"""
        shots AS (
            SELECT e.game_id, e.possession_id, e.player1_id AS shooter, g.season_end_year AS y, g.season_type AS t,
                   CAST(e.points > 0 AS INTEGER) AS made, e.points AS pts, 'three' AS kind
            FROM core.events e JOIN core.shots sh ON sh.game_id = e.game_id AND sh.source_event_num = e.source_event_num
            JOIN core.games g ON g.game_id = e.game_id
            WHERE e.event_type IN ('shot_made', 'shot_missed') AND sh.shot_type = '3PT Field Goal' AND e.player1_id IS NOT NULL AND ({lit})
            UNION ALL
            SELECT e.game_id, e.possession_id, e.player1_id, g.season_end_year, g.season_type, CAST(e.points > 0 AS INTEGER), e.points, 'ft'
            FROM core.events e JOIN core.games g ON g.game_id = e.game_id
            WHERE e.event_type = 'free_throw' AND e.possession_id IS NOT NULL AND e.player1_id IS NOT NULL AND ({lit})),
        league AS (SELECT y, t, kind, sum(made) * 1.0 / count(*) AS lg FROM shots GROUP BY ALL),
        rate AS (SELECT c.y, c.t, c.kind, c.shooter, (c.made + k.prior * l.lg) / (c.att + k.prior) AS p
                 FROM (SELECT y, t, kind, shooter, sum(made) AS made, count(*) AS att FROM shots GROUP BY ALL) c
                 JOIN league l USING (y, t, kind) JOIN (VALUES ('three', {float(three_prior)}), ('ft', {float(ft_prior)})) k(kind, prior) USING (kind)),
        adj AS (SELECT s.game_id, s.possession_id, sum(CASE WHEN s.kind = 'three' THEN 3.0 ELSE 1.0 END * r.p - s.pts) AS adj
                FROM shots s JOIN rate r ON r.y = s.y AND r.t = s.t AND r.kind = s.kind AND r.shooter = s.shooter
                WHERE s.possession_id IS NOT NULL GROUP BY 1, 2)"""


def load_possessions(con, seasons: list[tuple[int, str]], cfg: dict, luck: bool = False) -> pd.DataFrame:
    """One row per possession of the window: game_id, season_end_year, points, points_adj, offense_is_home, off_1..5, def_1..5.

    The five players of each side are those of the stint on the floor when the possession ends. `points_adj` equals `points`
    unless `luck` is set (see the module docstring).
    """
    if not seasons:
        raise RapmError("no seasons given")
    if any(t not in ("regular", "playoffs") for _, t in seasons):
        raise RapmError(f"unknown season type in {seasons}")
    where = " OR ".join(["(g.season_end_year = ? AND g.season_type = ?)"] * len(seasons))
    params = [x for season in seasons for x in season]
    luck_cfg = cfg.get("luck_adjustment", {})
    extra_ctes = f", {_luck_ctes(seasons, luck_cfg['three_prior_attempts'], luck_cfg['ft_prior_attempts'])}" if luck else ""
    adj_join = "LEFT JOIN adj a ON a.game_id = p.game_id AND a.possession_id = p.possession_id" if luck else ""
    points_adj = "p.points + coalesce(a.adj, 0)" if luck else "CAST(p.points AS DOUBLE)"
    flags = ""
    if cfg["exclude_end_of_period_heave"]:
        flags += " AND NOT p.is_end_of_period_heave"
    if cfg["exclude_garbage_time"]:
        flags += " AND NOT p.is_garbage_time"
    home, away = "s.home_p1, s.home_p2, s.home_p3, s.home_p4, s.home_p5", "s.away_p1, s.away_p2, s.away_p3, s.away_p4, s.away_p5"
    df = con.execute(f"""
        WITH e AS (SELECT game_id, possession_id, arg_max(stint_id, segment_seq) AS end_stint
                   FROM core.possession_stint_segments GROUP BY ALL){extra_ctes}
        SELECT p.game_id, g.season_end_year, p.points, {points_adj} AS points_adj, p.offense_team_id = g.home_team_id AS offense_is_home,
               CASE WHEN p.offense_team_id = g.home_team_id THEN [{home}] ELSE [{away}] END AS off,
               CASE WHEN p.offense_team_id = g.home_team_id THEN [{away}] ELSE [{home}] END AS def
        FROM core.possessions p JOIN core.games g USING (game_id)
        JOIN e ON e.game_id = p.game_id AND e.possession_id = p.possession_id
        JOIN core.stints s ON s.game_id = p.game_id AND s.stint_id = e.end_stint {adj_join}
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


def bootstrap_se(x, y: np.ndarray, groups: np.ndarray, alpha: float, n_own: int, n_boot: int, seed: int) -> pd.DataFrame:
    """Standard errors of o_rapm, d_rapm and rapm (per 100 possessions) from a bootstrap of whole games."""
    games, game_idx = np.unique(groups, return_inverse=True)
    rng = np.random.default_rng(seed)
    o, d = np.empty((n_boot, n_own)), np.empty((n_boot, n_own))
    for b in range(n_boot):
        weight = np.bincount(rng.integers(0, len(games), len(games)), minlength=len(games))[game_idx].astype(float)
        keep = weight > 0
        coef = Ridge(alpha=alpha, solver="sparse_cg", random_state=0).fit(x[keep], y[keep], sample_weight=weight[keep]).coef_
        o[b], d[b] = 100.0 * coef[:n_own], -100.0 * coef[n_own:2 * n_own]
    return pd.DataFrame({"o_se": o.std(axis=0, ddof=1), "d_se": d.std(axis=0, ddof=1), "rapm_se": (o + d).std(axis=0, ddof=1)})


def fit(obs: pd.DataFrame, cfg: dict, alpha: float | None = None, bootstrap: int = 0, y_col: str = "points") -> dict:
    """Fit RAPM on possession observations (the outcome is the column `y_col`: points, or points_adj for the luck-adjusted variant).
    Returns players (DataFrame), alpha, cv, home_points, n_obs.

    With `bootstrap` > 0 the players also carry o_se, d_se and rapm_se (bootstrap of whole games, same penalty)."""
    players = bucket_players(obs, int(cfg["min_possessions_for_own_column"]))
    own = players.loc[players["own_column"], "player_id"].to_numpy()
    if len(own) == 0:
        raise RapmError("no player reaches min_possessions_for_own_column")
    x, names = design_matrix(obs, own)
    y = obs[y_col].to_numpy(dtype=float)
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
    if bootstrap > 0:
        out = pd.concat([out, bootstrap_se(x, y, obs["game_id"].to_numpy(), alpha, n_own, bootstrap, int(cfg["seed"]))], axis=1)
    return {"players": out, "alpha": float(alpha), "cv": cv, "n_obs": len(obs), "n_own": n_own,
            "n_replacement": int((~players["own_column"]).sum()), "intercept_per100": 100.0 * float(model.intercept_),
            "home_points_per100": 100.0 * float(coef[HOME]),
            "replacement_o": 100.0 * float(coef["off:replacement"]), "replacement_d": -100.0 * float(coef["def:replacement"])}


def split_half(obs: pd.DataFrame, cfg: dict, alpha: float, y_col: str = "points") -> dict:
    """Reliability: fit on two random halves of the games with the same penalty; correlate the players in both."""
    games = np.array(obs["game_id"].unique(), dtype=object)
    rng = np.random.default_rng(int(cfg["seed"]))
    rng.shuffle(games)
    half = set(games[: len(games) // 2])
    mask = obs["game_id"].isin(half).to_numpy()
    a, b = fit(obs[mask], cfg, alpha, y_col=y_col)["players"], fit(obs[~mask], cfg, alpha, y_col=y_col)["players"]
    m = a.merge(b, on="player_id", suffixes=("_a", "_b"))
    m = m[(m["off_poss_a"] + m["def_poss_a"] >= cfg["split_half_min_possessions"]) & (m["off_poss_b"] + m["def_poss_b"] >= cfg["split_half_min_possessions"])]
    if len(m) < 3:
        return {"players": len(m), "r_rapm": None, "r_o": None, "r_d": None}
    return {"players": len(m), "r_rapm": float(m["rapm_a"].corr(m["rapm_b"])), "r_o": float(m["o_rapm_a"].corr(m["o_rapm_b"])),
            "r_d": float(m["d_rapm_a"].corr(m["d_rapm_b"]))}


# ------------------------------------------------------------------ mart


DDL = """(
    window_id TEXT NOT NULL, variant TEXT NOT NULL, player_id INTEGER NOT NULL, off_poss INTEGER NOT NULL, def_poss INTEGER NOT NULL,
    o_rapm DOUBLE NOT NULL, d_rapm DOUBLE NOT NULL, rapm DOUBLE NOT NULL, o_se DOUBLE, d_se DOUBLE, rapm_se DOUBLE,
    alpha DOUBLE NOT NULL, n_obs INTEGER NOT NULL, home_points_per100 DOUBLE NOT NULL,
    credit_method TEXT NOT NULL, exclude_end_of_period_heave BOOLEAN NOT NULL, exclude_garbage_time BOOLEAN NOT NULL,
    min_possessions_for_own_column INTEGER NOT NULL, luck_three_prior INTEGER, luck_ft_prior INTEGER,
    rules_version TEXT NOT NULL, rules_profile TEXT NOT NULL,
    PRIMARY KEY (window_id, variant, player_id))"""

DDL_WINDOWS = """(
    window_id TEXT NOT NULL, variant TEXT NOT NULL, n_obs INTEGER NOT NULL, players INTEGER NOT NULL, alpha DOUBLE NOT NULL,
    cv_improvement_pct DOUBLE, split_half_players INTEGER, split_half_r DOUBLE, split_half_r_o DOUBLE, split_half_r_d DOUBLE,
    home_points_per100 DOUBLE NOT NULL, rules_version TEXT NOT NULL, rules_profile TEXT NOT NULL,
    PRIMARY KEY (window_id, variant))"""


def window_id(seasons: list[tuple[int, str]]) -> str:
    """'2025-26 regular' or '2023-24 + 2024-25 + 2025-26 regular' (all of one season type) or a plain list."""
    types = {t for _, t in seasons}
    years = sorted(y for y, _ in seasons)
    label = " + ".join(season_label(y) for y in years)
    return f"{label} {types.pop()}" if len(types) == 1 else ", ".join(f"{season_label(y)} {t}" for y, t in seasons)


def _ensure_tables(con) -> None:
    """Create the RAPM tables; a table built before `variant` existed is migrated (its rows are the raw variant)."""
    con.execute("CREATE SCHEMA IF NOT EXISTS marts")
    old = con.execute("SELECT count(*) FROM information_schema.columns WHERE table_schema = 'marts' AND table_name = 'player_rapm'").fetchone()[0]
    has_variant = con.execute("SELECT count(*) FROM information_schema.columns WHERE table_schema = 'marts' AND table_name = 'player_rapm' "
                              "AND column_name = 'variant'").fetchone()[0]
    if old and not has_variant:
        con.execute("BEGIN")
        con.execute(f"CREATE TABLE marts.player_rapm_new {DDL}")
        have = {r[0] for r in con.execute("DESCRIBE marts.player_rapm").fetchall()}
        cols = [c for c in ("window_id", "player_id", "off_poss", "def_poss", "o_rapm", "d_rapm", "rapm", "o_se", "d_se", "rapm_se", "alpha", "n_obs",
                            "home_points_per100", "credit_method", "exclude_end_of_period_heave", "exclude_garbage_time",
                            "min_possessions_for_own_column", "rules_version", "rules_profile") if c in have]
        con.execute(f"INSERT INTO marts.player_rapm_new ({', '.join(cols)}, variant) SELECT {', '.join(cols)}, 'raw' FROM marts.player_rapm")
        con.execute("DROP TABLE marts.player_rapm")
        con.execute("ALTER TABLE marts.player_rapm_new RENAME TO player_rapm")
        con.execute("COMMIT")
    con.execute(f"CREATE TABLE IF NOT EXISTS marts.player_rapm {DDL}")
    con.execute(f"CREATE TABLE IF NOT EXISTS marts.rapm_windows {DDL_WINDOWS}")


def _version(con) -> tuple[str, str]:
    versions = con.execute("SELECT DISTINCT rules_version, rules_profile FROM core.possessions").fetchall()
    if len(versions) != 1:
        raise RapmError(f"core.possessions holds {len(versions)} rules versions / profiles; expected exactly one: {versions}")
    return versions[0]


def build(con, seasons: list[tuple[int, str]], cfg: dict | None = None, variant: str = "raw", diagnostics: bool = False) -> dict:
    """Fit one window of one variant and write its rows to marts.player_rapm (replacing that window's rows of that variant).

    With `diagnostics`, the cross-validation gain and the split-half reliability are stored in marts.rapm_windows. Returns a summary.
    """
    if variant not in VARIANTS:
        raise RapmError(f"unknown variant {variant!r}; known: {VARIANTS}")
    cfg = cfg or load_rules()["rapm"]
    version = _version(con)
    luck = variant == "luck_adjusted"
    y_col = "points_adj" if luck else "points"
    obs = load_possessions(con, seasons, cfg, luck=luck)
    res = fit(obs, cfg, bootstrap=int(cfg.get("bootstrap_samples", 0)), y_col=y_col)
    wid = window_id(seasons)
    rows = res["players"].copy()
    for c in ("o_se", "d_se", "rapm_se"):
        if c not in rows:
            rows[c] = np.nan
    rows = rows[["player_id", "off_poss", "def_poss", "o_rapm", "d_rapm", "rapm", "o_se", "d_se", "rapm_se"]]
    rows.insert(0, "variant", variant)
    rows.insert(0, "window_id", wid)
    luck_cfg = cfg.get("luck_adjustment", {})
    for k, v in (("alpha", res["alpha"]), ("n_obs", res["n_obs"]), ("home_points_per100", res["home_points_per100"]),
                 ("credit_method", cfg["credit"]), ("exclude_end_of_period_heave", bool(cfg["exclude_end_of_period_heave"])),
                 ("exclude_garbage_time", bool(cfg["exclude_garbage_time"])),
                 ("min_possessions_for_own_column", int(cfg["min_possessions_for_own_column"])),
                 ("luck_three_prior", int(luck_cfg["three_prior_attempts"]) if luck else None),
                 ("luck_ft_prior", int(luck_cfg["ft_prior_attempts"]) if luck else None),
                 ("rules_version", version[0]), ("rules_profile", version[1])):
        rows[k] = v
    diag = None
    if diagnostics:
        half = split_half(obs, cfg, res["alpha"], y_col=y_col)
        best = res["cv"]["table"].loc[res["cv"]["table"]["alpha"] == res["cv"]["alpha"]].iloc[0]
        diag = pd.DataFrame([{"window_id": wid, "variant": variant, "n_obs": res["n_obs"], "players": len(rows), "alpha": res["alpha"],
                              "cv_improvement_pct": float(100 * (1 - best["mean_mse"] / res["cv"]["baseline_mse"])),
                              "split_half_players": half["players"], "split_half_r": half["r_rapm"], "split_half_r_o": half["r_o"],
                              "split_half_r_d": half["r_d"], "home_points_per100": res["home_points_per100"],
                              "rules_version": version[0], "rules_profile": version[1]}])
    _ensure_tables(con)
    con.execute("BEGIN")
    try:
        con.execute("DELETE FROM marts.player_rapm WHERE window_id = ? AND variant = ?", [wid, variant])
        con.register("rapm_rows", rows)
        con.execute("INSERT INTO marts.player_rapm BY NAME SELECT * FROM rapm_rows")
        con.unregister("rapm_rows")
        if diag is not None:
            con.execute("DELETE FROM marts.rapm_windows WHERE window_id = ? AND variant = ?", [wid, variant])
            con.register("rapm_diag", diag)
            con.execute("INSERT INTO marts.rapm_windows BY NAME SELECT * FROM rapm_diag")
            con.unregister("rapm_diag")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return {"window": wid, "variant": variant, "observations": res["n_obs"], "players": len(rows), "alpha": round(res["alpha"], 1),
            "grid_extended": res["cv"]["extensions"], "home_points_per100": round(res["home_points_per100"], 2)}


def windows(first_year: int, last_year: int, length: int = 3, season_type: str = "regular") -> list[list[tuple[int, str]]]:
    """Every single-season window and every trailing window of `length` seasons that fits (first_year .. last_year)."""
    out = [[(y, season_type)] for y in range(first_year, last_year + 1)]
    out += [[(y - k, season_type) for k in range(length - 1, -1, -1)] for y in range(first_year + length - 1, last_year + 1)]
    return out


def all_windows(con, cfg: dict | None = None, variants: tuple[str, ...] = VARIANTS, skip_existing: bool = True, log=print) -> list[dict]:
    """Fit every window of every variant (regular seasons of core.games), one commit per window; a finished window is skipped,
    so an interrupted run can simply be started again."""
    cfg = cfg or load_rules()["rapm"]
    years = [y for (y,) in con.execute("SELECT DISTINCT season_end_year FROM core.possessions p JOIN core.games g USING (game_id) "
                                       "WHERE g.season_type = 'regular' ORDER BY 1").fetchall()]
    _ensure_tables(con)
    done = []
    todo = [(w, v) for w in windows(min(years), max(years), int(cfg.get("window_seasons", 3))) for v in variants]
    for i, (w, v) in enumerate(todo, 1):
        wid = window_id(w)
        if skip_existing and con.execute("SELECT count(*) FROM marts.rapm_windows WHERE window_id = ? AND variant = ?", [wid, v]).fetchone()[0]:
            continue
        t0 = datetime.now()
        out = build(con, w, cfg, variant=v, diagnostics=True)
        out["seconds"] = round((datetime.now() - t0).total_seconds())
        log(f"[{i}/{len(todo)}] {out}")
        done.append(out)
    return done


# ------------------------------------------------------------------ report


def write_report(con, path: Path, seasons: list[tuple[int, str]], cfg: dict | None = None, variant: str = "raw") -> dict:
    """docs/validation/rapm_<window>.md: cross-validation, reliability, sensitivity to the choices, sanity checks."""
    cfg = cfg or load_rules()["rapm"]
    names = dict(con.execute("SELECT player_id, name FROM core.players").fetchall())
    luck = variant == "luck_adjusted"
    y_col = "points_adj" if luck else "points"
    obs = load_possessions(con, seasons, cfg, luck=luck)
    n_boot = int(cfg.get("bootstrap_samples", 0))
    res = fit(obs, cfg, bootstrap=n_boot, y_col=y_col)
    cv, wid = res["cv"], window_id(seasons)
    half = split_half(obs, cfg, res["alpha"], y_col=y_col)
    variants = {}
    for label, heave, garbage in (("heaves and garbage time both in", False, False), ("heaves out, garbage time in", True, False)):
        v_cfg = {**cfg, "exclude_end_of_period_heave": heave, "exclude_garbage_time": garbage}
        v = fit(load_possessions(con, seasons, v_cfg, luck=luck), v_cfg, res["alpha"], y_col=y_col)["players"]
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
    se_note = []
    if n_boot:
        se_note = [f"Standard errors: bootstrap of whole games, {n_boot} resamples, same penalty. Players with {cfg['split_half_min_possessions']:,}+ possessions: "
                   f"median standard error **{big['rapm_se'].median():.2f}** points per 100 (offense {big['o_se'].median():.2f}, defense {big['d_se'].median():.2f}); "
                   f"**{int((big['rapm'].abs() > 2 * big['rapm_se']).sum())}** of {len(big)} players have a rating more than two standard errors from zero "
                   f"({int((top['rapm'] > 2 * top['rapm_se']).sum())} of the top 10, {int((bottom['rapm'] < -2 * bottom['rapm_se']).sum())} of the bottom 10). "
                   "Sampling noise only; the shrinkage bias of ridge is not in it.", ""]
    luck_cfg = cfg.get("luck_adjustment", {})
    luck_line = (f"- Variant **luck_adjusted**: every three-point attempt counts 3 x the shooter's expected percentage and every free throw his expected percentage "
                 f"(season rate shrunk toward the league's, priors {luck_cfg.get('three_prior_attempts')} / {luck_cfg.get('ft_prior_attempts')} attempts); unknown shot types keep their result."
                 if luck else "- Variant **raw**: the points that were scored.")
    lines = [f"# RAPM: {wid} ({variant})", "",
             "Ridge regression on our own possessions (`metrics/rapm.py`). Numbers only. **Prototype**: `marts.player_rapm` waits for the owner's "
             "approval; every choice below is `rules.yaml` `rapm` and marked [待確認].", "",
             luck_line,
             f"- Observations: **{res['n_obs']:,}** possessions; credit: `{cfg['credit']}`; end-of-period heaves "
             f"{'excluded' if cfg['exclude_end_of_period_heave'] else 'included'}; garbage time {'excluded' if cfg['exclude_garbage_time'] else 'included'}.",
             f"- Players with their own column: **{res['n_own']}**; pooled into the replacement column: {res['n_replacement']} "
             f"(fewer than {cfg['min_possessions_for_own_column']} possessions). Replacement player: offense {res['replacement_o']:+.2f}, defense {res['replacement_d']:+.2f} points per 100.",
             f"- League average: {res['intercept_per100']:.1f} points per 100 possessions; home court: **{res['home_points_per100']:+.2f}** points per 100.", "",
             *se_note,
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
              "| | player | RAPM | ± standard error | offense | defense | possessions |", "|---|---|---|---|---|---|---|"]
    fmt = lambda r: f"{r.rapm_se:.2f}" if n_boot else "-"  # noqa: E731
    lines += [f"| top | {r.name} | {r.rapm:+.2f} | {fmt(r)} | {r.o_rapm:+.2f} | {r.d_rapm:+.2f} | {r.poss:,} |" for r in top.itertuples()]
    lines += [f"| bottom | {r.name} | {r.rapm:+.2f} | {fmt(r)} | {r.o_rapm:+.2f} | {r.d_rapm:+.2f} | {r.poss:,} |" for r in bottom.itertuples()]
    lines += ["", "Reading: ridge shrinks every player toward the average, so the spread is smaller than raw on/off. "
              "Differences between players that are smaller than their standard errors are noise.", ""]
    path.write_text(chr(10).join(lines), encoding="utf-8")
    return {"alpha": res["alpha"], "split_half_r": half["r_rapm"], "cv_improvement_pct": round(100 * (1 - best["mean_mse"] / cv["baseline_mse"]), 2)}


def forecast_table(con, variant: str, kind: str) -> pd.DataFrame:
    """Out-of-sample check: the RAPM of the window that ends the season before predicts a team's net rating of the next season.

    prediction = sum over the team's players of (share of the team's offensive possessions he was on the floor) x his RAPM
    (a player without a rating counts 0, an average player); actual = the team's net rating of that season without heaves and garbage time
    (the possessions RAPM is trained on). `kind` is 'single' (the previous season) or 'trailing' (the three seasons ending in it).
    """
    years = [y for (y,) in con.execute("SELECT DISTINCT season_end_year FROM marts.team_efficiency_season WHERE season_type = 'regular' ORDER BY 1").fetchall()]
    rows = []
    for y in years[1:]:
        w = [(y - 1, "regular")] if kind == "single" else [(y - k, "regular") for k in (3, 2, 1)]
        if any(season not in [(a, "regular") for a in years] for season in w):
            continue
        wid = window_id(w)
        if not con.execute("SELECT count(*) FROM marts.rapm_windows WHERE window_id = ? AND variant = ?", [wid, variant]).fetchone()[0]:
            continue
        df = con.execute("""
            SELECT o.team_id, sum(o.on_o_poss * 1.0 / t.o_poss * coalesce(r.rapm, 0)) AS predicted,
                   sum(o.on_o_poss * 1.0 / t.o_poss) FILTER (r.rapm IS NOT NULL) / 5 AS rated_share,
                   any_value(t.net_ex_heave_garbage) AS actual, any_value(p.net_ex_heave_garbage) AS last_net
            FROM marts.player_onoff_season o
            JOIN marts.team_efficiency_season t ON t.season_end_year = o.season_end_year AND t.season_type = o.season_type AND t.team_id = o.team_id
            LEFT JOIN marts.team_efficiency_season p ON p.season_end_year = o.season_end_year - 1 AND p.season_type = o.season_type AND p.team_id = o.team_id
            LEFT JOIN marts.player_rapm r ON r.player_id = o.player_id AND r.window_id = ? AND r.variant = ?
            WHERE o.season_end_year = ? AND o.season_type = 'regular' GROUP BY o.team_id""", [wid, variant, y]).df()
        df.insert(0, "season_end_year", y)
        rows.append(df)
    out = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["season_end_year", "team_id", "predicted", "rated_share", "actual", "last_net"])
    out.insert(0, "kind", kind)
    out.insert(0, "variant", variant)
    return out


def _skill(actual: np.ndarray, predicted: np.ndarray) -> dict:
    """Correlation and the RMSE after the best linear rescaling of the prediction (a + b x prediction)."""
    r = float(np.corrcoef(actual, predicted)[0, 1])
    b, a = np.polyfit(predicted, actual, 1)
    return {"r": r, "rmse": float(np.sqrt(np.mean((actual - (a + b * predicted)) ** 2))), "slope": float(b)}


def forecast_report(con, path: Path) -> dict:
    """docs/validation/rapm_forecast.md: how well each variant and window length predicts the next season's team net rating."""
    tables = {(v, k): forecast_table(con, v, k) for v in VARIANTS for k in ("single", "trailing")}
    keys = None
    for t in tables.values():
        ks = set(zip(t["season_end_year"], t["team_id"]))
        keys = ks if keys is None else keys & ks
    keys = {k for k in keys if all(pd.notna(t.loc[(t["season_end_year"] == k[0]) & (t["team_id"] == k[1]), "last_net"]).all() for t in tables.values())}
    lines = ["# RAPM out of sample: predicting the next season's team net rating", "",
             "For each team-season, the sum over its players of (share of the team's offensive possessions he was on the floor) x (his RAPM from the window that ends the season **before**) is compared with "
             "the team's net rating of the season (without end-of-period heaves and garbage time). A player without a rating counts 0. Numbers only.", "",
             f"Team-seasons in the common sample: **{len(keys):,}** (every method has a prediction for each of them). `RMSE` is after the best linear rescaling of the prediction; "
             "the baseline predicts a team's net rating by last season's net rating.", "",
             "| method | window | correlation | RMSE | slope |", "|---|---|---|---|---|"]
    out = {}
    common = pd.DataFrame(sorted(keys), columns=["season_end_year", "team_id"])
    base = None
    for (v, k), t in tables.items():
        m = common.merge(t, on=["season_end_year", "team_id"])
        if m.empty:
            continue
        sk = _skill(m["actual"].to_numpy(float), m["predicted"].to_numpy(float))
        out[f"{v}/{k}"] = sk
        lines.append(f"| RAPM {v} | {'one season' if k == 'single' else 'three seasons'} | {sk['r']:.3f} | {sk['rmse']:.2f} | {sk['slope']:.2f} |")
        base = m
    if base is not None:
        sk = _skill(base["actual"].to_numpy(float), base["last_net"].to_numpy(float))
        out["last season's net rating"] = sk
        lines.append(f"| last season's net rating | - | {sk['r']:.3f} | {sk['rmse']:.2f} | {sk['slope']:.2f} |")
    lines += ["", "Reading: a higher correlation and a lower RMSE are better. A prediction that uses the players' ratings knows the roster of the season it predicts "
              "(a roster known in advance, which is the usual forecasting set-up) but not its results.", ""]
    path.write_text(chr(10).join(lines), encoding="utf-8")
    return out


def slug(text: str) -> str:
    return re.sub(r"[^0-9a-z]+", "_", text.lower()).strip("_")


def parse_seasons(text: str) -> list[tuple[int, str]]:
    return [(int(a), b) for a, b in (x.split(":") for x in text.split(","))]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seasons", default="2025:regular", help="comma list like 2025:regular,2024:regular (season end years)")
    ap.add_argument("--variant", default="raw", choices=VARIANTS)
    ap.add_argument("--report", action="store_true", help="also write docs/validation/rapm_<window>[_luck_adjusted].md")
    ap.add_argument("--all-windows", action="store_true", help="fit every one-season and trailing three-season window for both variants (resumable)")
    ap.add_argument("--forecast-report", action="store_true", help="write docs/validation/rapm_forecast.md from the fitted windows")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    con = db.connect()
    try:
        if args.all_windows:
            all_windows(con, log=lambda m: print(m, flush=True))
        elif not args.forecast_report:
            seasons = parse_seasons(args.seasons)
            print(build(con, seasons, variant=args.variant, diagnostics=True))
            if args.report:
                suffix = "" if args.variant == "raw" else f"_{args.variant}"
                print(write_report(con, db.PROJECT_ROOT / "docs" / "validation" / f"rapm_{slug(window_id(seasons))}{suffix}.md", seasons, variant=args.variant))
        if args.forecast_report or args.all_windows:
            print(forecast_report(con, db.PROJECT_ROOT / "docs" / "validation" / "rapm_forecast.md"))
    finally:
        con.close()


if __name__ == "__main__":
    main()
