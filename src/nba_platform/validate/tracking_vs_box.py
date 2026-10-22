"""NBA.com season tracking tables vs the official box score season totals (a warning-level report).

reference.nba_tracking repeats a few box stats (AST in Passing; STL, BLK, DREB in Defense;
OREB, DREB, REB in Rebounding; GP in every measure). They are compared with the official box
score (marts.player_season) at the **player-season** level: in the regular season NBA.com
lists a traded player once, under his last team, with full-season totals, so the box score is
summed over a player's teams. Differences are reported, never fixed.

Expected pattern (explained in the report): tracking can be *lower* than the box score because
NBA.com's tracking data misses some games; tracking *higher* than the box score is not expected.

Usage:
    python -m nba_platform.validate.tracking_vs_box
"""

from __future__ import annotations

import sys
from pathlib import Path

from nba_platform import db
from nba_platform.seasons import season_label

# (label, tracking measure, tracking column, marts.player_season column)
PAIRS = [("GP", "Possessions", "GP", "games"), ("AST", "Passing", "AST", "ast"), ("STL", "Defense", "STL", "stl"),
         ("BLK", "Defense", "BLK", "blk"), ("OREB", "Rebounding", "OREB", "oreb"), ("DREB", "Rebounding", "DREB", "dreb"),
         ("REB", "Rebounding", "REB", "reb")]
KEYS = "CAST(substr(season, 1, 4) AS INTEGER) + 1 AS season_end_year, season_type, PLAYER_ID AS player_id"
BOX_TOTALS = ("SELECT season_end_year, season_type, player_id, " +
              ", ".join(f"sum({b}) AS {b}" for _, _, _, b in PAIRS) +
              " FROM marts.player_season GROUP BY ALL")


def season_rows(con) -> list[tuple]:
    out = []
    for lbl, m, col, bcol in PAIRS:
        rows = con.execute(f"""
            WITH t AS (SELECT {KEYS}, sum({col}) AS v FROM reference.nba_tracking
                       WHERE request_param_1 = '{m}' AND {col} IS NOT NULL GROUP BY ALL),
                 b AS ({BOX_TOTALS})
            SELECT t.season_end_year, t.season_type, count(*) AS n, count(b.player_id) AS matched,
                   avg((b.{bcol} = t.v)::INT) FILTER (b.player_id IS NOT NULL),
                   avg((t.v < b.{bcol})::INT) FILTER (b.player_id IS NOT NULL),
                   avg((t.v > b.{bcol})::INT) FILTER (b.player_id IS NOT NULL)
            FROM t LEFT JOIN b USING (season_end_year, season_type, player_id) GROUP BY ALL""").fetchall()
        out += [(lbl, *r) for r in rows]
    return out


def worst(con, limit: int = 12) -> list[tuple]:
    """Player-seasons where tracking is *higher* than the box score (not expected), largest first."""
    pairs = [p for p in PAIRS if p[0] in ("AST", "STL", "BLK", "REB")]
    sel = " + ".join(f"greatest(coalesce(t_{l.lower()}.v, 0) - coalesce(b.{bc}, 0), 0)" for l, _, _, bc in pairs)
    joins = "\n".join(
        f"LEFT JOIN (SELECT {KEYS}, sum({col}) AS v FROM reference.nba_tracking WHERE request_param_1 = '{m}' GROUP BY ALL) t_{l.lower()} "
        f"USING (season_end_year, season_type, player_id)" for l, m, col, _ in pairs)
    return con.execute(f"""
        WITH b AS ({BOX_TOTALS})
        SELECT season_end_year, season_type, player_id, {sel} AS diff FROM b {joins}
        WHERE season_end_year >= 2014 ORDER BY diff DESC NULLS LAST, 1, 2, 3 LIMIT {limit}""").fetchall()


def write_report(con, path: Path) -> None:
    rows = season_rows(con)
    labels = [p[0] for p in PAIRS]
    by: dict = {}
    for lbl, y, t, n, matched, same, lower, higher in rows:
        by.setdefault((y, t), {})[lbl] = (n, matched, same, lower, higher)
    lines = ["# NBA.com season tracking tables vs the official box score", "",
             "Box stats repeated inside `reference.nba_tracking` compared with the official box score (`marts.player_season`)",
             "per **player and season**: the box score is summed over a player's teams, because in the regular season NBA.com",
             "lists a traded player once (under his last team) with full-season totals. Each cell is `identical / tracking lower /",
             "tracking higher` as shares of player-seasons. Tracking *lower* is expected (NBA.com's tracking data misses some games,",
             "visible in GP); tracking *higher* is not. Numbers only; differences are reported, not fixed.", "",
             "| season | type | player-seasons | no box row | " + " | ".join(labels) + " |", "|---|---|---|---|" + "---|" * len(labels)]
    for (y, t), d in sorted(by.items(), key=lambda kv: (kv[0][1] != "regular", kv[0][0])):
        n = max(v[0] for v in d.values())
        missing = n - max(v[1] for v in d.values())
        cells = [f"{d[l][2]:.0%} / {d[l][3]:.0%} / {d[l][4]:.0%}" if l in d and d[l][2] is not None else "-" for l in labels]
        lines.append(f"| {season_label(y)} | {t} | {n:,} | {missing:,} | " + " | ".join(cells) + " |")
    lines += ["", "## Largest cases of tracking *higher* than the box score (AST + STL + BLK + REB)", "",
              "| season | type | player_id | sum of excess |", "|---|---|---|---|"]
    lines += [f"| {season_label(y)} | {t} | {p} | {d:.0f} |" for y, t, p, d in worst(con) if d]
    path.write_text(chr(10).join(lines) + chr(10), encoding="utf-8")


def main() -> None:
    from nba_platform.db import PROJECT_ROOT

    sys.stdout.reconfigure(encoding="utf-8")
    con = db.connect(read_only=True)
    try:
        write_report(con, PROJECT_ROOT / "docs" / "validation" / "tracking_vs_box.md")
    finally:
        con.close()
    print("docs/validation/tracking_vs_box.md written")


if __name__ == "__main__":
    main()
