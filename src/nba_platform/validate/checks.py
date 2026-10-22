"""Per-season validation checks (CLAUDE.md "Validation checklist").

Each check returns a CheckResult; results are stored in validation.results and written
to docs/validation/. Two levels:
- 'hard'    : a failure stops the season (its load is rolled back, no results produced)
- 'warning' : a failure is reported for review; the season is still loaded
A failing check never changes data: failures are reported, not fixed.
Checks the review did not classify are 'warning' until the owner decides (decisions.md).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime

import duckdb
import pandas as pd

# Reference numbers from general knowledge, not from data (docs/decisions.md). [待確認]
_REGULAR_SEASON_GAMES_SPECIAL = {1999: 725, 2012: 990, 2013: 1229, 2020: 1059, 2021: 1080}


def expected_regular_season_games(season_end_year: int) -> int:
    if season_end_year in _REGULAR_SEASON_GAMES_SPECIAL:
        return _REGULAR_SEASON_GAMES_SPECIAL[season_end_year]
    return 1189 if season_end_year <= 2004 else 1230  # 29 teams before 2004-05, then 30


@dataclass
class CheckResult:
    check_id: int
    check_name: str
    status: str  # 'pass' | 'fail' | 'skip'
    n_checked: int | None = None
    n_failed: int | None = None
    detail: dict = field(default_factory=dict)
    level: str = "warning"  # 'hard' | 'warning'


def _season_games_cte(season_end_year: int, season_type: str, pbp_only: bool = False) -> str:
    """CTE `g` = the season's games; `pbp_only` drops known `pbp_missing` games (no events)."""
    extra = " AND NOT coalesce(pbp_missing, FALSE)" if pbp_only else ""
    return (
        "WITH g AS (SELECT * FROM core.games "
        f"WHERE season_end_year = {int(season_end_year)} AND season_type = '{season_type}'{extra})"
    )


def _known_gaps(con, y: int, t: str) -> dict[str, str]:
    try:
        from nba_platform.known_gaps import season_gaps
        return season_gaps(con, y, t)
    except duckdb.CatalogException:  # database built before known_gaps existed
        return {}


def _status(n_failed: int) -> str:
    return "pass" if n_failed == 0 else "fail"


def check_1_game_count(con, y: int, t: str) -> CheckResult:
    n = con.execute(f"{_season_games_cte(y, t)} SELECT count(*) FROM g").fetchone()[0]
    if t == "regular":
        expected = expected_regular_season_games(y)
        r = CheckResult(1, "game count matches schedule", _status(int(n != expected)), n, abs(n - expected),
                        {"games": n, "expected": expected})
    else:
        r = check_1_playoff_series(con, y, t, n)
    r = _add_box_schedule(con, y, t, r)
    missing = sorted(g for g, issue in _known_gaps(con, y, t).items() if issue == "pbp_missing")
    if missing:
        r.detail["known_gaps_pbp_missing"] = missing
        if r.status == "pass":
            r.status = "known"  # complete only thanks to a known gap: a warning, not a failure
    return r


def _add_box_schedule(con, y: int, t: str, r: CheckResult) -> CheckResult:
    """When nba_api box scores are cached, their game list is a schedule: compare game IDs."""
    from nba_platform.validate.box_minutes import load_box_minutes

    box = load_box_minutes(y, t)
    if box is None:
        r.detail["box_score_schedule"] = "not cached"
        return r
    ours = {row[0] for row in con.execute(f"{_season_games_cte(y, t)} SELECT game_id FROM g").fetchall()}
    theirs = set(box["game_id"])
    missing, extra = sorted(theirs - ours), sorted(ours - theirs)
    r.detail["box_score_schedule"] = {"box_games": len(theirs), "missing_from_ours": missing[:20],
                                      "not_in_box": extra[:20]}
    if missing or extra:
        r.status = "fail"
        r.n_failed = (r.n_failed or 0) + len(missing) + len(extra)
    return r


PLAYOFF_SERIES = 15  # 16-team bracket, 1983-84 onwards (play-in games are not in the files)


def check_1_playoff_series(con, y: int, t: str, n_games: int) -> CheckResult:
    """No schedule source for playoffs: check the series structure instead.

    A series = the unordered pair of teams (two teams meet at most once per playoffs).
    Older game IDs are sequential (004YY000GG) so the round is not in the ID: the 8
    series that start first are round 1. Required wins: 3 for round 1 through 2001-02
    (best-of-5), otherwise 4. Every series must end with the winner at exactly the
    required wins, the loser below it, and no game after the clinching game.
    """
    games = con.execute(f"""
        {_season_games_cte(y, t)}
        SELECT least(home_team_id, away_team_id) AS a, greatest(home_team_id, away_team_id) AS b,
               game_date, game_id,
               CASE WHEN home_score > away_score THEN home_team_id
                    WHEN away_score > home_score THEN away_team_id END AS winner
        FROM g ORDER BY game_date, game_id""").fetchall()
    series: dict[tuple[int, int], list] = {}
    for a, b, d, gid, w in games:
        series.setdefault((a, b), []).append((d, gid, w))
    first_round = set(sorted(series, key=lambda k: (series[k][0][0], series[k][0][1]))[:8])
    bad = []
    for key, gs in series.items():
        need = 3 if (key in first_round and y <= 2002) else 4
        wins: dict[int, int] = {}
        problem = None
        for i, (_, gid, w) in enumerate(gs):
            if w is None:
                problem = f"tied/unknown score in {gid}"
                break
            wins[w] = wins.get(w, 0) + 1
            if wins[w] == need and i != len(gs) - 1:
                problem = f"game after clincher ({gid})"
                break
        top = sorted(wins.values(), reverse=True) + [0, 0]
        if problem is None and not (top[0] == need and top[1] < need):
            problem = f"wins {top[:2]} (need {need})"
        if problem:
            bad.append({"teams": list(key), "games": len(gs), "problem": problem})
    n_bad = len(bad) + int(len(series) != PLAYOFF_SERIES)
    return CheckResult(1, "playoff series complete (no schedule source)", _status(n_bad), len(series), n_bad,
                       {"games": n_games, "series": len(series), "expected_series": PLAYOFF_SERIES,
                        "bad_series": bad[:10]})


def check_2_points_equal_score(con, y: int, t: str) -> CheckResult:
    rows = con.execute(f"""
        {_season_games_cte(y, t, pbp_only=True)},
        pts AS (
            SELECT e.game_id,
                   sum(CASE WHEN e.team_id = g.home_team_id THEN e.points ELSE 0 END) AS home_pts,
                   sum(CASE WHEN e.team_id = g.away_team_id THEN e.points ELSE 0 END) AS away_pts,
                   sum(CASE WHEN e.points > 0 AND e.team_id IS DISTINCT FROM g.home_team_id
                                 AND e.team_id IS DISTINCT FROM g.away_team_id THEN e.points ELSE 0 END) AS orphan_pts
            FROM core.events e JOIN g USING (game_id) GROUP BY e.game_id
        )
        SELECT g.game_id, g.home_score, pts.home_pts, g.away_score, pts.away_pts, pts.orphan_pts
        FROM g LEFT JOIN pts USING (game_id)
        WHERE pts.home_pts IS DISTINCT FROM g.home_score OR pts.away_pts IS DISTINCT FROM g.away_score
              OR pts.orphan_pts <> 0
        ORDER BY 1""").fetchall()
    n = con.execute(f"{_season_games_cte(y, t, pbp_only=True)} SELECT count(*) FROM g").fetchone()[0]
    cols = ["game_id", "home_score", "home_pts", "away_score", "away_pts", "orphan_pts"]
    gaps = _known_gaps(con, y, t)
    known = [r[0] for r in rows if r[0] in gaps]
    status = _status(len(rows))
    if rows and len(known) == len(rows):
        status = "known"  # every mismatch is a documented source contradiction
    return CheckResult(2, "sum of event points = final score", status, n, len(rows),
                       {"examples": [dict(zip(cols, r)) for r in rows[:10]], "known_gaps": known,
                        "pbp_missing_games_excluded": sorted(g for g, i in gaps.items() if i == "pbp_missing")})


def check_3_five_players(con, y: int, t: str) -> CheckResult:
    n, bad, games, ex = con.execute(f"""
        {_season_games_cte(y, t)},
        l AS (
            SELECT l.*, len(list_distinct(home_player_ids)) AS nh, len(list_distinct(away_player_ids)) AS na,
                   len(list_intersect(home_player_ids, away_player_ids)) AS overlap
            FROM staging.event_lineups l JOIN g USING (game_id)
        )
        SELECT count(*), count(*) FILTER (nh <> 5 OR na <> 5 OR overlap > 0),
               count(DISTINCT game_id) FILTER (nh <> 5 OR na <> 5 OR overlap > 0),
               list(game_id || ':' || event_seq || ' h' || nh || ' a' || na) FILTER (nh <> 5 OR na <> 5 OR overlap > 0)[1:10]
        FROM l""").fetchone()
    n_events = con.execute(f"{_season_games_cte(y, t)} SELECT count(*) FROM core.events JOIN g USING (game_id)").fetchone()[0]
    missing = n_events - n
    return CheckResult(3, "5 distinct home + 5 distinct away players on every event",
                       _status(bad + missing), n_events, bad + missing,
                       {"events_without_lineup": missing, "games_affected": games, "examples": ex or []})


def check_104_no_duplicate_player_in_lineup(con, y: int, t: str) -> CheckResult:
    n, bad, ex = con.execute(f"""
        {_season_games_cte(y, t)},
        l AS (
            SELECT l.game_id, l.event_seq,
                   len(list_distinct(home_player_ids)) <> len(home_player_ids)
                   OR len(list_distinct(away_player_ids)) <> len(away_player_ids)
                   OR len(list_intersect(home_player_ids, away_player_ids)) > 0 AS dup
            FROM staging.event_lineups l JOIN g USING (game_id)
        )
        SELECT count(*), count(*) FILTER (dup), list(game_id || ':' || event_seq) FILTER (dup)[1:10]
        FROM l""").fetchone()
    return CheckResult(104, "no player twice in one lineup (within or across teams)", _status(bad), n, bad,
                       {"examples": ex or []}, level="hard")


def check_105_game_time_in_range(con, y: int, t: str) -> CheckResult:
    n, bad, ex = con.execute(f"""
        {_season_games_cte(y, t)},
        e AS (
            SELECT e.game_id, e.event_seq, e.period, e.secs_elapsed_game AS s, g.num_periods,
                   CASE WHEN e.period <= 4 THEN (e.period - 1) * 720 ELSE 2880 + (e.period - 5) * 300 END AS p0,
                   CASE WHEN e.period <= 4 THEN e.period * 720 ELSE 2880 + (e.period - 4) * 300 END AS p1
            FROM core.events e JOIN g USING (game_id)
        ),
        b AS (SELECT *, (period < 1 OR period > num_periods OR s < p0 OR s > p1) AS bad FROM e)
        SELECT count(*), count(*) FILTER (bad),
               list(game_id || ':' || event_seq || ' p' || period || ' s' || s) FILTER (bad)[1:10]
        FROM b""").fetchone()
    return CheckResult(105, "game time within its period and game length", _status(bad), n, bad,
                       {"examples": ex or []}, level="hard")


def check_106_no_row_inflation(con, y: int, t: str, expected: dict[str, int]) -> CheckResult:
    """Loaded row counts must equal staged row counts (no many-to-many join inflation)."""
    got = dict(zip(["games", "events", "lineups", "distinct_game_ids"], con.execute(f"""
        {_season_games_cte(y, t)}
        SELECT (SELECT count(*) FROM g),
               (SELECT count(*) FROM core.events JOIN g USING (game_id)),
               (SELECT count(*) FROM staging.event_lineups JOIN g USING (game_id)),
               (SELECT count(DISTINCT game_id) FROM g)""").fetchone()))
    exp = {**expected, "lineups": expected["events"], "distinct_game_ids": expected["games"]}
    diff = {k: {"expected": exp[k], "loaded": got[k]} for k in exp if exp[k] != got[k]}
    return CheckResult(106, "loaded row counts = staged row counts (no join inflation)",
                       _status(len(diff)), len(exp), len(diff), {"counts": got, "diff": diff}, level="hard")


def check_9_ids_resolve(con, y: int, t: str) -> CheckResult:
    """Every player / team ID used by this season exists in core.players / core.teams."""
    bad_players, bad_teams = con.execute(f"""
        {_season_games_cte(y, t)},
        ids AS (
            SELECT unnest([player1_id, player2_id, player3_id]) AS pid FROM core.events JOIN g USING (game_id)
            UNION SELECT unnest(home_player_ids || away_player_ids) FROM staging.event_lineups JOIN g USING (game_id)
        ),
        tids AS (
            SELECT team_id AS tid FROM core.events JOIN g USING (game_id) WHERE team_id IS NOT NULL
            UNION SELECT home_team_id FROM g UNION SELECT away_team_id FROM g
        )
        SELECT (SELECT list(pid) FROM ids WHERE pid IS NOT NULL AND pid NOT IN (SELECT player_id FROM core.players)),
               (SELECT list(tid) FROM tids WHERE tid NOT IN (SELECT team_id FROM core.teams))""").fetchone()
    bad_players, bad_teams = bad_players or [], bad_teams or []
    n_bad = len(bad_players) + len(bad_teams)
    return CheckResult(9, "every player_id / team_id resolves in players / teams", _status(n_bad), None, n_bad,
                       {"players": bad_players[:20], "teams": bad_teams[:20]}, level="hard")


def check_4_substitutions(con, y: int, t: str) -> CheckResult:
    """On a substitution row the source lineup is already post-sub (docs/decisions.md)."""
    n, bad, no_ids, not_on_before, ex = con.execute(f"""
        {_season_games_cte(y, t)},
        s AS (
            SELECT e.game_id, e.event_seq, e.player1_id AS out_id, e.player2_id AS in_id,
                   CASE WHEN e.team_id = g.home_team_id THEN l.home_player_ids
                        WHEN e.team_id = g.away_team_id THEN l.away_player_ids END AS after_ids,
                   CASE WHEN e.team_id = g.home_team_id THEN lp.home_player_ids
                        WHEN e.team_id = g.away_team_id THEN lp.away_player_ids END AS before_ids
            FROM core.events e JOIN g USING (game_id)
            LEFT JOIN staging.event_lineups l ON l.game_id = e.game_id AND l.event_seq = e.event_seq
            LEFT JOIN staging.event_lineups lp ON lp.game_id = e.game_id AND lp.event_seq = e.event_seq - 1
            WHERE e.event_type = 'substitution'
        ),
        f AS (
            SELECT *,
                   (out_id IS NULL OR in_id IS NULL OR after_ids IS NULL) AS no_ids,
                   (NOT list_contains(after_ids, in_id) OR list_contains(after_ids, out_id)) AS bad_after,
                   (before_ids IS NOT NULL AND NOT list_contains(before_ids, out_id)) AS out_not_on_before
            FROM s
        )
        SELECT count(*), count(*) FILTER (no_ids OR bad_after), count(*) FILTER (no_ids),
               count(*) FILTER (out_not_on_before),
               list(game_id || ':' || event_seq) FILTER (no_ids OR bad_after)[1:10]
        FROM f""").fetchone()
    return CheckResult(4, "substitution consistency (entering on court, leaving off court)",
                       _status(bad), n, bad,
                       {"subs_missing_ids_or_team": no_ids,
                        "info_leaving_player_not_on_court_before": not_on_before,
                        "examples": ex or []})


def pbp_player_seconds_sql(y: int, t: str) -> str:
    """Seconds on court per (game, player): time to the next event credited to the lineup
    shown on each event (the same accounting as check 6)."""
    return f"""
        {_season_games_cte(y, t)},
        d AS (
            SELECT e.game_id, e.event_seq,
                   coalesce(lead(e.secs_elapsed_game) OVER w, e.secs_elapsed_game) - e.secs_elapsed_game AS dt
            FROM core.events e JOIN g USING (game_id)
            WINDOW w AS (PARTITION BY e.game_id ORDER BY e.event_seq)
        ),
        pl AS (
            SELECT d.game_id, unnest(l.home_player_ids || l.away_player_ids) AS player_id, d.dt
            FROM d JOIN staging.event_lineups l USING (game_id, event_seq)
        )
        SELECT game_id, player_id, sum(dt) AS pbp_secs FROM pl GROUP BY ALL"""


def check_5_minutes_vs_box(con, y: int, t: str, box=None, rules: dict | None = None) -> CheckResult:
    """PBP minutes vs box-score minutes (nba_api LeagueGameLog). Warning level."""
    from nba_platform.rules import load_rules
    from nba_platform.validate.box_minutes import load_box_minutes

    box = load_box_minutes(y, t) if box is None else box
    if box is None:
        return CheckResult(5, "player minutes ≈ box score minutes", "skip",
                           detail={"reason": "no cached nba_api LeagueGameLog for this season"})
    v = (rules or load_rules())["validation"]
    tol, large = float(v["minutes_rounding_tolerance"]), float(v["minutes_large_diff"])
    con.register("box_minutes", box)
    try:
        df = con.execute(f"""
            WITH pbp AS ({pbp_player_seconds_sql(y, t)}),
                 b AS (SELECT * FROM box_minutes WHERE game_id IN (SELECT game_id FROM core.games
                       WHERE season_end_year = {int(y)} AND season_type = '{t}'
                         AND NOT coalesce(pbp_missing, FALSE)))
            SELECT coalesce(p.game_id, b.game_id) AS game_id, coalesce(p.player_id, b.player_id) AS player_id,
                   p.pbp_secs / 60.0 AS pbp_min, b.box_min
            FROM pbp p FULL JOIN b USING (game_id, player_id)""").df()
    finally:
        con.unregister("box_minutes")
    both = df.dropna(subset=["pbp_min", "box_min"]).copy()
    both["abs_diff"] = (both["pbp_min"] - both["box_min"]).abs()
    pbp_only = df[df["box_min"].isna() & (df["pbp_min"] > 0)]
    box_only = df[df["pbp_min"].isna() & (df["box_min"] > 0)]
    bins = [-0.001, 0.5, tol, 2, large, float("inf")]
    labels = ["<=0.5", f"<={tol:g}", "<=2", f"<={large:g}", f">{large:g}"]
    dist = pd.cut(both["abs_diff"], bins=bins, labels=labels).value_counts().reindex(labels).fillna(0).astype(int)
    big_games = (both[both["abs_diff"] > large].groupby("game_id")["abs_diff"]
                 .agg(["count", "max"]).sort_values("max", ascending=False).head(15))
    n_over_tol = int((both["abs_diff"] > tol).sum())
    n_bad = n_over_tol + len(pbp_only) + len(box_only)
    return CheckResult(5, f"player minutes ≈ box score minutes (warning above {tol:g} min)",
                       _status(n_bad), len(both), n_bad,
                       {"player_games_compared": len(both), "abs_diff_distribution": dist.to_dict(),
                        "over_tolerance": n_over_tol, "pbp_only_player_games": len(pbp_only),
                        "box_only_player_games": len(box_only),
                        "mean_abs_diff_min": round(float(both["abs_diff"].mean()), 4) if len(both) else None,
                        "largest_diff_games": [{"game_id": g, "players": int(r["count"]), "max_diff_min": round(float(r["max"]), 2)}
                                               for g, r in big_games.iterrows()]})


def check_6_player_seconds(con, y: int, t: str) -> CheckResult:
    rows = con.execute(f"""
        {_season_games_cte(y, t, pbp_only=True)},
        d AS (
            SELECT e.game_id, e.event_seq,
                   coalesce(lead(e.secs_elapsed_game) OVER w, e.secs_elapsed_game) - e.secs_elapsed_game AS dt
            FROM core.events e JOIN g USING (game_id)
            WINDOW w AS (PARTITION BY e.game_id ORDER BY e.event_seq)
        ),
        ps AS (
            SELECT d.game_id, sum(d.dt * len(l.home_player_ids)) AS home_ps,
                   sum(d.dt * len(l.away_player_ids)) AS away_ps,
                   count(*) FILTER (d.dt < 0) AS n_negative_dt
            FROM d JOIN staging.event_lineups l USING (game_id, event_seq) GROUP BY d.game_id
        )
        SELECT g.game_id, 5 * (2880 + 300 * (g.num_periods - 4)) AS expected, ps.home_ps, ps.away_ps, ps.n_negative_dt
        FROM g LEFT JOIN ps USING (game_id)
        WHERE abs(ps.home_ps - 5 * (2880 + 300 * (g.num_periods - 4))) > 1e-6
           OR abs(ps.away_ps - 5 * (2880 + 300 * (g.num_periods - 4))) > 1e-6
           OR ps.home_ps IS NULL OR ps.n_negative_dt > 0
        ORDER BY 1""").fetchall()
    n = con.execute(f"{_season_games_cte(y, t, pbp_only=True)} SELECT count(*) FROM g").fetchone()[0]
    cols = ["game_id", "expected", "home_ps", "away_ps", "n_negative_dt"]
    return CheckResult(6, "team player-seconds = 5 × game length", _status(len(rows)), n, len(rows),
                       {"examples": [dict(zip(cols, r)) for r in rows[:10]]})


def check_101_clock_vs_source_secs(con, y: int, t: str, source_secs_mismatches: int) -> CheckResult:
    """Our secs_elapsed_game (from period + clock) vs the source's secs_game column."""
    n = con.execute(f"{_season_games_cte(y, t)} SELECT count(*) FROM core.events JOIN g USING (game_id)").fetchone()[0]
    return CheckResult(101, "secs_elapsed_game (from clock) = source secs_game",
                       _status(source_secs_mismatches), n, source_secs_mismatches)


def check_102_unique_event_keys(con, y: int, t: str) -> CheckResult:
    dup = con.execute(f"""
        {_season_games_cte(y, t)}
        SELECT (SELECT count(*) FROM (SELECT game_id, event_seq FROM core.events JOIN g USING (game_id)
                                      GROUP BY ALL HAVING count(*) > 1))
             + (SELECT count(*) FROM (SELECT game_id, source_event_num FROM core.events JOIN g USING (game_id)
                                      GROUP BY ALL HAVING count(*) > 1))""").fetchone()[0]
    return CheckResult(102, "events unique on (game_id, event_seq) and (game_id, source_event_num)",
                       _status(dup), None, dup, level="hard")


def check_10_shot_join(con, y: int, t: str) -> CheckResult:
    """Shot coordinates join rate to shot events (expect ~100%)."""
    n_fga, n_joined, n_with_xy, n_orphan_shots, n_mismatch = con.execute(f"""
        {_season_games_cte(y, t)},
        fga AS (SELECT e.* FROM core.events e JOIN g USING (game_id)
                WHERE e.event_type IN ('shot_made', 'shot_missed')),
        sh AS (SELECT s.* FROM core.shots s JOIN g USING (game_id))
        SELECT (SELECT count(*) FROM fga),
               (SELECT count(*) FROM fga JOIN sh USING (game_id, source_event_num)),
               (SELECT count(*) FROM fga JOIN sh USING (game_id, source_event_num)
                WHERE sh.loc_x IS NOT NULL AND sh.loc_y IS NOT NULL),
               (SELECT count(*) FROM sh ANTI JOIN fga USING (game_id, source_event_num)),
               (SELECT count(*) FROM fga JOIN sh USING (game_id, source_event_num)
                WHERE sh.made <> (fga.event_type = 'shot_made')
                   OR sh.player_id IS DISTINCT FROM fga.player1_id
                   OR sh.team_id IS DISTINCT FROM fga.team_id)
        """).fetchone()
    rate = (n_with_xy / n_fga) if n_fga else 0.0
    # Threshold: >= 99% of FGA must have coordinates, and joined shots must agree.
    failed = (n_fga - n_with_xy) if rate < 0.99 else 0
    return CheckResult(10, "shot coordinates join rate to FGA events",
                       "pass" if rate >= 0.99 and n_mismatch == 0 else "fail",
                       n_fga, failed + n_mismatch,
                       {"fga": n_fga, "joined": n_joined, "with_xy": n_with_xy,
                        "join_rate_xy": round(rate, 6), "shots_without_event": n_orphan_shots,
                        "joined_but_disagree": n_mismatch})


# Hard checks run inside the load transaction; any failure rolls the season back.
PBP_HARD_CHECKS = (
    check_9_ids_resolve,
    check_102_unique_event_keys,
    check_104_no_duplicate_player_in_lineup,
    check_105_game_time_in_range,
)
PBP_WARNING_CHECKS = (
    check_1_game_count,
    check_2_points_equal_score,
    check_3_five_players,
    check_4_substitutions,
    check_5_minutes_vs_box,
    check_6_player_seconds,
)


def save_results(con: duckdb.DuckDBPyConnection, y: int, t: str, results: list[CheckResult]) -> None:
    """Replace every stored result of this season with this run's results."""
    run_at = datetime.now()
    con.execute("DELETE FROM validation.results WHERE season_end_year = ? AND season_type = ?", [y, t])
    con.executemany(
        "INSERT INTO validation.results VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            [run_at, y, t, r.check_id, r.check_name, r.level, r.status, r.n_checked, r.n_failed,
             json.dumps(r.detail, default=str, ensure_ascii=False)]
            for r in results
        ],
    )


def format_results(results: list[CheckResult]) -> str:
    lines = []
    for r in results:
        counts = "" if r.n_checked is None and r.n_failed is None else f"  checked={r.n_checked} failed={r.n_failed}"
        lines.append(f"[{r.status.upper():4}] {r.level:7} {r.check_id:>3} {r.check_name}{counts}")
        if r.status != "pass" and r.detail:
            lines.append(f"         {json.dumps(r.detail, default=str, ensure_ascii=False)[:600]}")
    return "\n".join(lines)


def check_107_shots_unique_and_complete(con, y: int, t: str, n_staged: int, n_orphan_game: int) -> CheckResult:
    """Shots unique on (game_id, source_event_num) and loaded rows = staged rows.

    ``n_orphan_game``: staged shots whose game_id is not a game of this season (loaded,
    reported, but not counted in the season's rows).
    """
    n_loaded, n_dup = con.execute(f"""
        {_season_games_cte(y, t)},
        sh AS (SELECT s.* FROM core.shots s JOIN g USING (game_id))
        SELECT (SELECT count(*) FROM sh),
               (SELECT count(*) FROM (SELECT game_id, source_event_num FROM sh GROUP BY ALL HAVING count(*) > 1))
        """).fetchone()
    n_bad = n_dup + int(n_loaded + n_orphan_game != n_staged)
    return CheckResult(107, "shots unique per event and loaded rows = staged rows", _status(n_bad), n_staged, n_bad,
                       {"staged": n_staged, "loaded_for_season_games": n_loaded,
                        "shots_for_unknown_games": n_orphan_game, "duplicate_keys": n_dup}, level="hard")


def save_check_results(con: duckdb.DuckDBPyConnection, y: int, t: str, results: list[CheckResult]) -> None:
    """Replace only the given checks of a season (used when a check is re-run on its own)."""
    run_at = datetime.now()
    for r in results:
        con.execute("DELETE FROM validation.results WHERE season_end_year = ? AND season_type = ? AND check_id = ?",
                    [y, t, r.check_id])
        con.execute("INSERT INTO validation.results VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [run_at, y, t, r.check_id, r.check_name, r.level, r.status, r.n_checked, r.n_failed,
                     json.dumps(r.detail, default=str, ensure_ascii=False)])
