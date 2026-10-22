"""Stage -> load -> validate one season (or one game, as a checkpoint).

Usage:
    python -m nba_platform.pipeline --season-end-year 2005
    python -m nba_platform.pipeline --season-end-year 2005 --season-type playoffs
    python -m nba_platform.pipeline --season-end-year 2005 --game-id 0020400027 --db :memory:

Hard checks run inside the load transaction: a failure rolls the season back (nothing
loaded) and is reported. Warnings are reported and the season stays loaded.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass

from nba_platform import db, known_gaps, load
from nba_platform.db import PROJECT_ROOT
from nba_platform.staging import ramirobentes as rb
from nba_platform.staging import shufinskiy as sh
from nba_platform.validate import checks, report

CORRECTIONS_CSV = PROJECT_ROOT / "corrections" / "corrections.csv"


class HardFail(RuntimeError):
    def __init__(self, results: list[checks.CheckResult]):
        self.results = results
        failed = [f"{r.check_id} {r.check_name}" for r in results if r.status == "fail"]
        super().__init__(f"hard checks failed: {failed}")


@dataclass
class SeasonOutcome:
    season_end_year: int
    season_type: str
    outcome: str  # 'loaded' | 'hard fail — not loaded'
    results: list[checks.CheckResult]


def run_season(
    con,
    season_end_year: int,
    season_type: str = "regular",
    game_ids: list[str] | None = None,
    write_reports: bool = True,
    verbose: bool = True,
) -> SeasonOutcome:
    t0 = time.time()
    log = print if verbose else (lambda *a, **k: None)
    y, t = season_end_year, season_type

    results: list[checks.CheckResult] = []
    outcome = "loaded"
    try:
        raw = rb.read_raw(y, t)
        shotdetail = sh.read_shotdetail(sh.raw_path("shotdetail", y, t))
        if game_ids:
            raw = raw[raw["game_id"].isin(game_ids)]
            shotdetail = shotdetail[shotdetail["GAME_ID"].isin(game_ids)]
        team_xref = rb.derive_team_xref(raw, shotdetail, y)
        staged = rb.stage(raw, team_xref, y, t, rb.read_corrections(CORRECTIONS_CSV))
        log(f"staged {y} {t}: {len(staged.games)} games, {len(staged.events):,} events, "
            f"{staged.n_synthetic_rows} synthetic rows excluded, {staged.n_corrections_applied} corrections")
    except rb.StagingError as exc:
        results = [checks.CheckResult(0, "staging: every row maps (IDs, teams, event types)", "fail",
                                      None, None, {"error": str(exc)}, level="hard")]
        outcome = "hard fail — not loaded"
        log(f"STAGING FAILED {y} {t}: {exc}")
    else:
        secs_mismatch = int((staged.events["secs_elapsed_game"] != staged.events["source_secs_game"]).sum())
        expected = {"games": len(staged.games), "events": len(staged.events)}

        def hard_checks(c):
            hard = [check(c, y, t) for check in checks.PBP_HARD_CHECKS]
            hard.append(checks.check_106_no_row_inflation(c, y, t, expected))
            results.extend(hard)
            if any(r.status == "fail" for r in hard):
                raise HardFail(hard)

        out_dir = None
        if game_ids:
            out_dir = load.STAGING_DIR / "_checkpoint" / f"{t}_{y}"
        try:
            load.load_pbp_season(con, staged, team_xref, rb.SOURCE, y, t, before_commit=hard_checks, out_dir=out_dir)
        except HardFail as exc:
            outcome = "hard fail — not loaded"
            log(f"HARD FAIL {y} {t}: {exc}")
        else:
            gap_problems = known_gaps.apply(con, y, t) if not game_ids else []
            gaps = known_gaps.season_gaps(con, y, t)
            results.append(checks.CheckResult(
                111, "known gaps / source contradictions applied (corrections/known_gaps.csv)",
                "fail" if gap_problems else ("known" if gaps else "pass"), len(gaps), len(gap_problems),
                {"gaps": gaps, "problems": gap_problems}))
            warning_checks = checks.PBP_WARNING_CHECKS
            if game_ids:  # a single-game checkpoint has no schedule to compare against
                warning_checks = tuple(c for c in warning_checks if c is not checks.check_1_game_count)
            results += [check(con, y, t) for check in warning_checks]
            results.append(checks.check_101_clock_vs_source_secs(con, y, t, secs_mismatch))
            results.append(checks.CheckResult(
                103, "synthetic msg_type 99 rows excluded (info)", "pass", None, None,
                {"n_synthetic_rows": staged.n_synthetic_rows}))
            conflicting = team_xref[team_xref["n_conflicting"] > 0]
            results.append(checks.CheckResult(
                110, f"team xref: shots joined to another TEAM_ID (mapping uses >= {rb.TEAM_XREF_MIN_SHARE:.0%} share)",
                "pass" if conflicting.empty else "fail", int(team_xref["n_joined_shots"].sum()),
                int(team_xref["n_conflicting"].sum()),
                {"teams": conflicting[["source_team_key", "team_id", "n_joined_shots", "n_conflicting"]]
                 .to_dict("records")}))
            ties = staged.order_ties
            results.append(checks.CheckResult(
                109, "events sharing a ramirobentes number_event (ordered by event_num)",
                "pass" if ties.empty else "fail", len(staged.events), len(ties),
                {"rows": len(ties), "games": int(ties["game_id"].nunique()),
                 "examples": ties.head(10).astype(str).to_dict("records")}))
            shots_outcome = run_shots(con, y, t, shotdetail, staged.games, results, log,
                                      out_dir=out_dir)
            if shots_outcome != "loaded":
                outcome = f"loaded; {shots_outcome}"

    checks.save_results(con, y, t, results)
    log(checks.format_results(results))
    if write_reports and not game_ids:
        report.write_season_detail(y, t, outcome, results)
        report.write_season_report(con)
    log(f"{outcome} in {time.time() - t0:.1f}s")
    return SeasonOutcome(y, t, outcome, results)


def run_shots(con, y: int, t: str, shotdetail, games, results: list, log, out_dir=None) -> str:
    """Stage + load shots (shufinskiy shotdetail), hard check 107, warning check 10."""
    try:
        shots = sh.stage_shots(shotdetail)
    except sh.ShotStagingError as exc:
        results.append(checks.CheckResult(108, "staging: shots map", "fail", None, None,
                                          {"error": str(exc)}, level="hard"))
        return "shots hard fail — shots not loaded"
    season_games = {r[0] for r in con.execute(
        "SELECT game_id FROM core.games WHERE season_end_year = ? AND season_type = ?", [y, t]).fetchall()}
    n_orphan = int((~shots["game_id"].isin(season_games | set(games["game_id"]))).sum())

    def hard(c):
        r = checks.check_107_shots_unique_and_complete(c, y, t, len(shots), n_orphan)
        results.append(r)
        if r.status == "fail":
            raise HardFail([r])

    try:
        load.load_shots_season(con, shots, "shufinskiy", y, t, before_commit=hard, out_dir=out_dir)
    except HardFail as exc:
        log(f"HARD FAIL shots {y} {t}: {exc}")
        return "shots hard fail — shots not loaded"
    results.append(checks.check_10_shot_join(con, y, t))
    return "loaded"


FIRST_SEASON_END_YEAR = 1997  # 1996-97
LAST_SEASON_END_YEAR = 2026   # 2025-26


def run_all(con, years, season_types=("regular", "playoffs")) -> list[SeasonOutcome]:
    """Every season independently. An unexpected error is a hard fail for that season only."""
    outcomes = []
    for y in years:
        for t in season_types:
            try:
                outcomes.append(run_season(con, y, t))
            except Exception as exc:  # reported, never swallowed silently
                r = checks.CheckResult(0, "pipeline error", "fail", None, None,
                                       {"error": f"{type(exc).__name__}: {exc}"}, level="hard")
                checks.save_results(con, y, t, [r])
                report.write_season_detail(y, t, "hard fail — not loaded", [r])
                print(f"ERROR {y} {t}: {type(exc).__name__}: {exc}")
                outcomes.append(SeasonOutcome(y, t, "hard fail — not loaded", [r]))
            sys.stdout.flush()
    post_load(con)
    report.write_season_report(con)
    return outcomes


def post_load(con) -> None:
    """After --all: rebuild shot quality flags, the BigDataBall cross-check (check 11) and the core
    tables (stints, possessions: a season reload clears their ids on core.events).

    Each step runs on its own; a failure is printed and recorded (season 0, `post_load`) —
    it never hides the load results.
    """
    from nba_platform import build_core
    from nba_platform.validate import bdb_crosscheck, shot_quality

    def core_tables():
        """Stints, possessions and event links for every loaded season (a reload clears them)."""
        failed = [r for r in build_core.run_all(con, "possessions", build_core.PROFILE) if r["status"] != "ok"]
        if failed:
            raise RuntimeError(f"{len(failed)} seasons failed: " + "; ".join(
                f"{r['season_end_year']} {r['season_type']}: {r.get('error', '')[:80]}" for r in failed[:3]))

    con.execute("DELETE FROM validation.results WHERE season_type = 'post_load'")  # previous run's failures
    for name, step in (("shot quality flags", lambda: shot_quality.run(con)),
                       ("BigDataBall cross-check", lambda: bdb_crosscheck.run(con)),
                       ("core tables (stints, possessions)", core_tables)):
        try:
            print(f"post-load: {name} ...", flush=True)
            step()
            print(f"post-load: {name} done", flush=True)
        except Exception as exc:  # reported, not swallowed
            print(f"POST-LOAD ERROR {name}: {type(exc).__name__}: {exc}", flush=True)
            checks.save_check_results(con, 0, "post_load", [checks.CheckResult(
                0, f"post-load step failed: {name}", "fail", None, None,
                {"error": f"{type(exc).__name__}: {exc}"}, level="hard")])


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage, load and validate one season (or all)")
    parser.add_argument("--season-end-year", type=int)
    parser.add_argument("--season-type", choices=["regular", "playoffs"], default="regular")
    parser.add_argument("--all", action="store_true", help=f"every season {FIRST_SEASON_END_YEAR}-{LAST_SEASON_END_YEAR}, regular + playoffs")
    parser.add_argument("--game-id", nargs="*", help="checkpoint: only these games (use with --db :memory:)")
    parser.add_argument("--db", default=str(db.DB_PATH))
    args = parser.parse_args()
    if not args.all and args.season_end_year is None:
        parser.error("--season-end-year or --all is required")
    sys.stdout.reconfigure(encoding="utf-8")  # Windows console default (cp950) can't print every character
    con = db.connect(args.db)
    try:
        if args.all:
            outs = run_all(con, range(FIRST_SEASON_END_YEAR, LAST_SEASON_END_YEAR + 1))
            ok = all(o.outcome.startswith("loaded") for o in outs)
        else:
            out = run_season(con, args.season_end_year, args.season_type, game_ids=args.game_id)
            ok = out.outcome == "loaded"
            if ok and not args.game_id:   # a reload clears stint_id / possession_id: rebuild this season's core tables
                from nba_platform import build_core
                print(build_core.run(con, args.season_end_year, args.season_type, "possessions", build_core.PROFILE), flush=True)
    finally:
        con.close()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
