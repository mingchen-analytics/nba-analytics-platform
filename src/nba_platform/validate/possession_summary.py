"""One table of the possession checks per season (docs/validation/possession_summary.md).

Reads core.possessions and the latest validation.results (checks 7, 8, 111); numbers only.
Usage:
    python -m nba_platform.validate.possession_summary
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from nba_platform import db
from nba_platform.seasons import season_label


def write_report(con, path: Path) -> int:
    res = {(y, t, c): (st, nf, d) for y, t, c, st, nf, d in con.execute("""
        SELECT season_end_year, season_type, check_id, status, n_failed, detail FROM validation.results
        WHERE check_id IN (7, 8, 111)
        QUALIFY row_number() OVER (PARTITION BY season_end_year, season_type, check_id ORDER BY run_at DESC) = 1""").fetchall()}
    poss = {(y, t): (n, imp) for y, t, n, imp in con.execute("""
        SELECT g.season_end_year, g.season_type, count(*), count(*) FILTER (p.start_type = 'implied')
        FROM core.possessions p JOIN core.games g USING (game_id) GROUP BY ALL""").fetchall()}
    games = {(y, t): n for y, t, n in con.execute("""
        SELECT season_end_year, season_type, count(*) FROM core.games WHERE NOT coalesce(pbp_missing, FALSE) GROUP BY ALL""").fetchall()}
    lines = ["# Possession checks, all seasons (profile `pbpstats_compat`)", "",
             "Per season: our possessions against the sources. Numbers only. `identical` and `within 1` are shares of team-games",
             "against pbpstats (check 8; possessions flagged as end-of-period heaves excluded; `-` = no pbpstats reference).",
             "`games > 2` = check 7 failures (games where the two teams' counts differ by more than 2); `implied` = possessions",
             "opened because the source never showed how the previous one ended. Check 111 (hard): possession points + free",
             "throws outside possessions = final score (known source score conflicts are not failures).", "",
             "| season | type | games | possessions | 111 | games > 2 (7) | identical (8) | within 1 (8) | implied |",
             "|---|---|---|---|---|---|---|---|---|"]
    for (y, t) in sorted(poss, key=lambda k: (k[1] != "regular", k[0])):
        s111, s7, s8 = (res.get((y, t, c), ("-", 0, "{}")) for c in (111, 7, 8))
        d8 = json.loads(s8[2]) if s8[2] else {}
        ident = f"{d8['share_identical']:.2%}" if "share_identical" in d8 else "-"
        w1 = f"{d8['within_1']:.2%}" if "within_1" in d8 else "-"
        lines.append(f"| {season_label(y)} | {t} | {games.get((y, t), 0):,} | {poss[(y, t)][0]:,} | {s111[0]} | {s7[1]} | {ident} | {w1} | {poss[(y, t)][1]} |")
    path.write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
    return len(poss)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    con = db.connect(read_only=True)
    try:
        n = write_report(con, db.PROJECT_ROOT / "docs" / "validation" / "possession_summary.md")
    finally:
        con.close()
    print(f"possession_summary.md: {n} seasons")


if __name__ == "__main__":
    main()
