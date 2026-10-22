"""Load cached single-game box scores (NBA.com) into reference tables.

Reads data/raw/nba_api/box_tracking/{season}/{game_id}.json (BoxScorePlayerTrackV3) and
data/raw/nba_api/box_hustle/{season}/{game_id}.json (BoxScoreHustleV2) — read only — and
rebuilds:
- reference.nba_box_tracking : one row per player and game (distance, speed, touches,
  passes, contested shots, ...)
- reference.nba_box_hustle   : one row per player and game (contested shots, deflections,
  loose balls, box outs, screen assists, ...)
Empty shells (no players) are counted, not loaded. Reference only — no player metrics.

Usage:
    python -m nba_platform.reference.boxscores
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

from nba_platform import db
from nba_platform.ingest.download import RAW_DIR

SOURCES = {"box_tracking": "nba_box_tracking", "box_hustle": "nba_box_hustle"}
PREFIX_TYPE = {"002": "regular", "004": "playoffs", "005": "play_in", "001": "preseason"}


def snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def minutes_to_secs(value) -> float | None:
    """'33:18' -> 1998; 'PT33M18.00S' -> 1998; empty / None -> None."""
    if value is None or value == "":
        return None
    s = str(value)
    m = re.fullmatch(r"PT(\d+)M([\d.]+)S", s)
    if m:
        return int(m.group(1)) * 60 + float(m.group(2))
    m = re.fullmatch(r"(\d+):(\d{1,2}(?:\.\d+)?)", s)
    if m:
        return int(m.group(1)) * 60 + float(m.group(2))
    raise ValueError(f"unparseable minutes {value!r}")


def flatten(data: dict, season: str) -> list[dict]:
    """One dict per player in one box-score response (empty list for an empty shell)."""
    body = next((v for k, v in data.items() if k != "meta" and isinstance(v, dict)), {})
    game_id = str(body.get("gameId", "")).zfill(10)
    rows = []
    for side in ("homeTeam", "awayTeam"):
        team = body.get(side) or {}
        for p in team.get("players") or []:
            stats = p.get("statistics") or {}
            row = {"game_id": game_id, "season": season, "season_type": PREFIX_TYPE.get(game_id[:3], "other"),
                   "team_id": team.get("teamId"), "is_home": side == "homeTeam", "person_id": p.get("personId"),
                   "position": p.get("position") or None, "comment": p.get("comment") or None,
                   "secs_played": minutes_to_secs(stats.get("minutes"))}
            row.update({snake(k): v for k, v in stats.items() if k != "minutes"})
            rows.append(row)
    return rows


def load_all(con, raw_dir: Path = RAW_DIR / "nba_api") -> dict[str, dict]:
    con.execute("CREATE SCHEMA IF NOT EXISTS reference")
    out = {}
    for folder, table in SOURCES.items():
        rows, files, empty = [], 0, 0
        for path in sorted((raw_dir / folder).glob("*/*.json")):
            files += 1
            r = flatten(json.loads(path.read_text(encoding="utf-8")), path.parent.name)
            if not r:
                empty += 1
            rows += r
        if rows:
            con.register("box_df", pd.DataFrame(rows))
            con.execute(f"CREATE OR REPLACE TABLE reference.{table} AS SELECT * FROM box_df")
            con.unregister("box_df")
        out[table] = {"files": files, "empty_shells": empty, "player_rows": len(rows),
                      "games": len({r["game_id"] for r in rows})}
    return out


def write_report(con, stats: dict, path: Path) -> None:
    """docs/validation/boxscore_reference.md: coverage and box-vs-PBP seconds (numbers only)."""
    from nba_platform.seasons import season_label
    from nba_platform.validate.checks import pbp_player_seconds_sql

    lines = ["# Single-game box scores (NBA.com, reference)", "",
             "Loaded from cached raw JSON by `nba_platform.reference.boxscores`. Numbers only.", "",
             "| table | files | empty shells | games | player rows |", "|---|---|---|---|---|"]
    lines += [f"| `reference.{t}` | {s['files']:,} | {s['empty_shells']:,} | {s['games']:,} | {s['player_rows']:,} |"
              for t, s in stats.items()]
    try:
        seasons = con.execute("""SELECT DISTINCT g.season_end_year, g.season_type FROM reference.nba_box_tracking b
                                 JOIN core.games g USING (game_id) ORDER BY 2, 1 DESC""").fetchall()
    except Exception:
        seasons = []
    lines += ["", "## Tracking-box minutes (to the second) vs our play-by-play minutes", "",
              "Players with time on court in either source. A third, independent check of on-court time.", "",
              "| season | type | games | player-games | in core.games | \\|diff\\| ≤ 10 s | ≤ 60 s | > 60 s | only in box | only in PBP |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for y, t in seasons:
        r = con.execute(f"""
            WITH pbp AS ({pbp_player_seconds_sql(y, t)}),
                 box AS (SELECT b.game_id, b.person_id AS player_id, b.secs_played
                         FROM reference.nba_box_tracking b JOIN core.games g USING (game_id)
                         WHERE g.season_end_year = {y} AND g.season_type = '{t}'),
                 j AS (SELECT * FROM box FULL JOIN pbp USING (game_id, player_id)
                       WHERE game_id IN (SELECT game_id FROM box)
                         AND (coalesce(secs_played, 0) > 0 OR coalesce(pbp_secs, 0) > 0))
            SELECT count(DISTINCT game_id), count(*),
                   avg((secs_played IS NOT NULL AND pbp_secs IS NOT NULL AND abs(secs_played - pbp_secs) <= 10)::INT),
                   avg((secs_played IS NOT NULL AND pbp_secs IS NOT NULL AND abs(secs_played - pbp_secs) <= 60)::INT),
                   avg((secs_played IS NOT NULL AND pbp_secs IS NOT NULL AND abs(secs_played - pbp_secs) > 60)::INT),
                   count(*) FILTER (coalesce(pbp_secs, 0) = 0), count(*) FILTER (coalesce(secs_played, 0) = 0)
            FROM j""").fetchone()
        lines.append(f"| {season_label(y)} | {t} | {r[0]:,} | {r[1]:,} | 100% | {r[2]:.1%} | {r[3]:.1%} | {r[4]:.1%} | {r[5]:,} | {r[6]:,} |")
    try:
        n_missing = con.execute("""SELECT count(DISTINCT game_id) FROM reference.nba_box_tracking
                                   WHERE game_id NOT IN (SELECT game_id FROM core.games)""").fetchone()[0]
        lines += ["", f"Box-score games not in `core.games`: {n_missing}."]
    except Exception:
        pass
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    from nba_platform.db import PROJECT_ROOT

    sys.stdout.reconfigure(encoding="utf-8")
    con = db.connect()
    try:
        stats = load_all(con)
        write_report(con, stats, PROJECT_ROOT / "docs" / "validation" / "boxscore_reference.md")
        print(stats)
    finally:
        con.close()


if __name__ == "__main__":
    main()
