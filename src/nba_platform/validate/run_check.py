"""Re-run single validation checks on every loaded season without reloading data.

Usage:
    python -m nba_platform.validate.run_check --check 5
"""

from __future__ import annotations

import argparse
import sys

from nba_platform import db
from nba_platform.validate import checks, report

CHECKS = {1: checks.check_1_game_count, 5: checks.check_5_minutes_vs_box}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", type=int, required=True, choices=sorted(CHECKS))
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    con = db.connect()
    try:
        seasons = con.execute("SELECT DISTINCT season_end_year, season_type FROM core.games ORDER BY 2, 1").fetchall()
        for y, t in seasons:
            r = CHECKS[args.check](con, y, t)
            checks.save_check_results(con, y, t, [r])
            print(f"{y} {t}: {r.status} checked={r.n_checked} failed={r.n_failed}")
        report.write_season_report(con)
    finally:
        con.close()


if __name__ == "__main__":
    main()
