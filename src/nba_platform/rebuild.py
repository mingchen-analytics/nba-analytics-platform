"""Rebuild everything derived from the loaded play-by-play, in order, in one run (the only writer).

1. core tables for every loaded season: stints, possessions, segments, event links
   (nba_platform.build_core, profile `pbpstats_compat`), with checks 111 / 7 / 8 and per-season reports;
2. reference.nba_player_box and the marts: player_game_pbp, player_game / player_season / team_game /
   team_season, shot zones, player tracking (each a full rebuild in one transaction);
3. the reports: box_vs_pbp, tracking_vs_box, box_marts, possession_summary.

A step that fails is printed and recorded, the run continues; the exit code is 1 if any failed.
Close DBeaver and Streamlit first: the database is opened for writing for the whole run.

Usage:
    python -m nba_platform.rebuild [--skip-core] [--seasons 2005:regular,2019:regular]
"""

from __future__ import annotations

import argparse
import sys
import time
import traceback

from nba_platform import build_core, db
from nba_platform.db import PROJECT_ROOT

VALIDATION = PROJECT_ROOT / "docs" / "validation"


def keep_awake() -> bool:
    """Ask Windows not to sleep while this process runs (reset when it exits); no power setting changes."""
    import os

    if os.name != "nt":
        return False
    import ctypes

    return bool(ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001))  # CONTINUOUS | SYSTEM_REQUIRED


def _step(name, fn, results):
    t0 = time.time()
    try:
        out = fn()
        results.append((name, "ok", round(time.time() - t0, 1), out))
        print(f"[ok]    {name} ({time.time() - t0:.0f}s): {out}", flush=True)
    except Exception as exc:  # reported, never swallowed silently
        results.append((name, "error", round(time.time() - t0, 1), f"{type(exc).__name__}: {exc}"))
        print(f"[ERROR] {name}: {type(exc).__name__}: {exc}", flush=True)
        traceback.print_exc()


def marts_and_reports(con, results) -> None:
    from nba_platform.marts import box_marts, player_game_pbp, shot_zones, tracking
    from nba_platform.reference import player_box
    from nba_platform.validate import box_vs_pbp, possession_summary, tracking_quality, tracking_vs_box

    _step("reference.nba_player_box", lambda: player_box.load_all(con), results)
    _step("marts.player_game_pbp", lambda: player_game_pbp.build(con), results)

    def box():
        out = box_marts.build(con)
        box_marts.write_report(con, out, VALIDATION / "box_marts.md")
        return out

    _step("marts: player_game, player_season, team_game, team_season", box, results)
    _step("marts: shot zones", lambda: shot_zones.build(con), results)
    _step("marts: player tracking", lambda: tracking.build(con), results)
    _step("report: box_vs_pbp", lambda: box_vs_pbp.write_report(con, VALIDATION / "box_vs_pbp.md"), results)
    _step("report: tracking_vs_box", lambda: tracking_vs_box.write_report(con, VALIDATION / "tracking_vs_box.md"), results)
    _step("report: tracking_quality", lambda: tracking_quality.write_report(con, VALIDATION / "tracking_quality.md"), results)
    _step("report: possession_summary", lambda: possession_summary.write_report(con, VALIDATION / "possession_summary.md"), results)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--skip-core", action="store_true", help="only the marts and reports")
    ap.add_argument("--seasons", help="comma list like 2005:regular,2019:playoffs (default: every loaded season)")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"keep-awake: {keep_awake()}", flush=True)
    seasons = None
    if args.seasons:
        seasons = [(int(a), b) for a, b in (x.split(":") for x in args.seasons.split(","))]
    results: list = []
    con = db.connect()
    try:
        if not args.skip_core:
            t0 = time.time()
            runs = build_core.run_all(con, "possessions", build_core.PROFILE, seasons)
            bad = [r for r in runs if r["status"] != "ok"]
            results.append(("core tables", "error" if bad else "ok", round(time.time() - t0, 1),
                            f"{len(runs) - len(bad)} of {len(runs)} seasons ok"))
        marts_and_reports(con, results)
    finally:
        con.close()
    failed = [r for r in results if r[1] != "ok"]
    print(f"\nrebuild done: {len(results) - len(failed)} of {len(results)} steps ok", flush=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
