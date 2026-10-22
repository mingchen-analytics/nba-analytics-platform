"""Official box score vs the box score counted from our play-by-play (a warning-level report).

Compares reference.nba_player_box (NBA.com, official stat corrections included) with
marts.player_game_pbp (counted from core.events) player by player and game by game, and
writes docs/validation/box_vs_pbp.md: numbers and IDs only. Differences are reported, never
fixed (CLAUDE.md working agreement 11); the events table is not changed to match the box.

Usage:
    python -m nba_platform.validate.box_vs_pbp
"""

from __future__ import annotations

import sys
from pathlib import Path

from nba_platform import db
from nba_platform.marts.player_game_pbp import STATS
from nba_platform.seasons import season_label

PLAYED = "(coalesce(b.min, 0) > 0 OR coalesce(p.secs_played, 0) > 0)"


def _joined_cte() -> str:
    cols = ", ".join(f"b.{s} AS box_{s}, p.{s} AS pbp_{s}" for s in STATS)
    return f"""
        j AS (SELECT coalesce(b.game_id, p.game_id) AS game_id, coalesce(b.player_id, p.player_id) AS player_id,
                     coalesce(b.season_end_year, p.season_end_year) AS season_end_year,
                     coalesce(b.season_type, p.season_type) AS season_type,
                     b.game_id IS NOT NULL AS in_box, p.game_id IS NOT NULL AS in_pbp, {cols}
              FROM reference.nba_player_box b
              FULL JOIN marts.player_game_pbp p USING (game_id, player_id)
              WHERE b.game_id IN (SELECT game_id FROM core.games WHERE NOT coalesce(pbp_missing, FALSE))
                 OR p.game_id IS NOT NULL)"""


def season_rows(con) -> list[tuple]:
    exact = ", ".join(f"avg((box_{s} = pbp_{s})::INT)" for s in STATS)
    return con.execute(f"""
        WITH {_joined_cte()}
        SELECT season_end_year, season_type, count(*) FILTER (in_box AND in_pbp) AS n,
               count(*) FILTER (in_box AND NOT in_pbp) AS only_box, count(*) FILTER (in_pbp AND NOT in_box) AS only_pbp,
               {exact}
        FROM j GROUP BY ALL ORDER BY 2 DESC, 1""").fetchall()


def worst_games(con, limit: int = 15) -> list[tuple]:
    diffs = " + ".join(f"abs(box_{s} - pbp_{s})" for s in STATS)
    return con.execute(f"""
        WITH {_joined_cte()}
        SELECT game_id, count(*) AS players_off, sum({diffs}) AS stat_diff
        FROM j WHERE in_box AND in_pbp AND ({diffs}) > 0
        GROUP BY game_id ORDER BY stat_diff DESC, game_id LIMIT {limit}""").fetchall()


def write_report(con, path: Path) -> None:
    rows = season_rows(con)
    lines = ["# Official box score vs our play-by-play box score", "",
             "`reference.nba_player_box` (NBA.com) against `marts.player_game_pbp` (counted from `core.events`), per",
             "player and game. Share of player-games where the two counts are identical. Numbers and IDs only.",
             "Games without play-by-play (`pbp_missing`) are not compared. Differences are reported, never fixed.", "",
             "| season | type | player-games | only in box | only in PBP | " + " | ".join(s.upper() for s in STATS) + " |",
             "|---|---|---|---|---|" + "---|" * len(STATS)]
    for y, t, n, ob, op, *shares in rows:
        lines.append(f"| {season_label(y)} | {t} | {n:,} | {ob:,} | {op:,} | " + " | ".join(f"{v:.2%}" for v in shares) + " |")
    lines += ["", "## Games with the largest differences", "",
              "Sum of absolute differences over all compared stats.", "",
              "| game_id | players that differ | sum of differences |", "|---|---|---|"]
    lines += [f"| `{g}` | {p} | {d:,} |" for g, p, d in worst_games(con)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    from nba_platform.db import PROJECT_ROOT

    sys.stdout.reconfigure(encoding="utf-8")
    con = db.connect(read_only=True)
    try:
        write_report(con, PROJECT_ROOT / "docs" / "validation" / "box_vs_pbp.md")
    finally:
        con.close()
    print("docs/validation/box_vs_pbp.md written")


if __name__ == "__main__":
    main()
