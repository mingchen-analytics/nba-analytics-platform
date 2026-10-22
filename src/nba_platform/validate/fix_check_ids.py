"""One-off repair of validation.results after check id 111 was used by two checks (run once, safe to repeat).

Until 2026-10-22 both the staging check "known gaps / source contradictions applied" and the possession check "possession
points + FTs outside possessions = final score" were stored as check 111, so each season's possession run replaced the
known-gaps result. The possession check is now 112. This moves the stored possession rows to 112 and writes the known-gaps
result again for every season from core.known_gaps (the same function the pipeline uses), then rewrites the season report.

Usage:
    python -m nba_platform.validate.fix_check_ids
"""

from __future__ import annotations

import json
import sys
from datetime import datetime

from nba_platform import db, known_gaps
from nba_platform.validate import checks, report

POSSESSION_NAME = "possession points%"


def fix(con) -> dict:
    moved = con.execute("SELECT count(*) FROM validation.results WHERE check_id = 111 AND check_name LIKE ?", [POSSESSION_NAME]).fetchone()[0]
    con.execute("UPDATE validation.results SET check_id = 112 WHERE check_id = 111 AND check_name LIKE ?", [POSSESSION_NAME])
    seasons = con.execute("SELECT DISTINCT season_end_year, season_type FROM validation.results ORDER BY 1, 2").fetchall()
    written = 0
    for y, t in seasons:
        if con.execute("SELECT count(*) FROM validation.results WHERE season_end_year = ? AND season_type = ? AND check_id = 111", [y, t]).fetchone()[0]:
            continue
        r = checks.check_111_known_gaps(known_gaps.season_gaps(con, y, t), [])
        con.execute("INSERT INTO validation.results VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [datetime.now(), y, t, r.check_id, r.check_name, r.level, r.status, r.n_checked, r.n_failed,
                     json.dumps(r.detail, default=str, ensure_ascii=False)])
        written += 1
    return {"possession_rows_moved_to_112": moved, "known_gap_rows_written": written, "seasons": len(seasons)}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    con = db.connect()
    try:
        print(fix(con))
        report.write_season_report(con)
    finally:
        con.close()


if __name__ == "__main__":
    main()
