"""Plausibility of NBA.com's season tracking numbers (docs/validation/tracking_quality.md).

tracking_vs_box.py checks the box statistics repeated inside the tracking tables; this report
checks the tracking measurements themselves. Per season it lists the league medians of a few
measurements (so a change in how NBA.com measures shows up as a break in the series) and the
player-seasons flagged `movement_suspect` (average speed above the plausible maximum in
rules.yaml). Flagged rows are kept; pages hide them by default.

Found 2026-10-22: in the 2025-26 regular season 44 players (MIL, DAL, NYK, POR, a few traded players)
have an average speed of up to 22.6 mph and distances about 2.7 times the normal level; no earlier
season has a value above 5.08 mph. The single-game boxes (marts.player_game_tracking) show the cause:
three games carry speeds of 60-338 mph for nearly every player; recomputed from the single-game boxes
without those games, the flagged players' speeds are normal. Numbers only; reported, not corrected.

Usage:
    python -m nba_platform.validate.tracking_quality
"""

from __future__ import annotations

import sys
from pathlib import Path

from nba_platform import db
from nba_platform.rules import load_rules
from nba_platform.seasons import season_label


def write_report(con, path: Path, rules: dict | None = None) -> int:
    limit = float((rules or load_rules())["dashboard"]["tracking_max_plausible_avg_speed_mph"])
    rows = con.execute("""
        SELECT season_end_year, season_type, count(*) AS n, count(*) FILTER (movement_suspect) AS flagged,
               round(median(dist_miles / nullif(min, 0) * 36) FILTER (gp >= 20 AND min > 300), 2) AS miles36,
               round(median(avg_speed) FILTER (gp >= 20 AND min > 300), 2) AS speed,
               round(median(time_of_poss / nullif(min, 0)) FILTER (gp >= 20 AND min > 300), 3) AS poss_per_min,
               round(median(touches / nullif(min, 0) * 36) FILTER (gp >= 20 AND min > 300), 1) AS touches36,
               round(max(avg_speed), 2) AS max_speed
        FROM marts.player_tracking_season WHERE gp IS NOT NULL GROUP BY ALL ORDER BY 2 DESC, 1""").fetchall()
    teams = con.execute("""
        SELECT p.season_end_year, p.season_type, t.abbreviation, count(*) FILTER (p.movement_suspect) AS flagged,
               round(100 * sum(p.min) FILTER (p.movement_suspect) / sum(p.min), 0) AS pct_min
        FROM marts.player_tracking_season p JOIN core.teams t USING (team_id) WHERE p.gp IS NOT NULL
        GROUP BY ALL HAVING count(*) FILTER (p.movement_suspect) >= 1 ORDER BY 1, 2, 4 DESC""").fetchall()
    lines = ["# NBA.com season tracking: plausibility", "",
             f"League medians (players with 20+ games and 300+ minutes) per season, and player-seasons flagged `movement_suspect`",
             f"(average speed above {limit:g} mph; kept in `marts.player_tracking_season`, hidden by default on the Tracking page). Numbers only.", "",
             "| season | type | player-seasons | flagged | max speed (mph) | median miles / 36 min | median speed (mph) | median possession time / min | median touches / 36 min |",
             "|---|---|---|---|---|---|---|---|---|"]
    for y, t, n, fl, m36, spd, tp, tc36, mx in rows:
        lines.append(f"| {season_label(y)} | {t} | {n:,} | {fl} | {mx} | {m36} | {spd} | {tp} | {tc36} |")
    lines += ["", "Reading the table: miles / 36 min and speed are stable from 2013-14 to 2024-25 and break only in the flagged "
              "season. Possession time per minute and touches per 36 minutes change level from 2024-25 (NBA.com's tracking "
              "measurement changed), so they are not comparable across that line.", "",
              "## Teams with flagged player-seasons", "", "| season | type | team | flagged players | share of the flagged players' minutes in the team's tracked minutes |",
              "|---|---|---|---|---|"]
    lines += [f"| {season_label(y)} | {t} | {ab} | {fl} | {pm:.0f} % |" for y, t, ab, fl, pm in teams]
    has_games = con.execute("""SELECT count(*) FROM information_schema.tables WHERE table_schema = 'marts'
                               AND table_name = 'player_game_tracking'""").fetchone()[0]
    if has_games:
        lines += _games_section(con)
    path.write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
    return sum(r[3] for r in rows)


def _games_section(con) -> list[str]:
    """Single games flagged in marts.player_game_tracking, and the flagged season rows recomputed without them."""
    games = con.execute("""
        SELECT m.game_id, g.game_date, h.abbreviation, a.abbreviation, count(*) AS players, round(max(m.speed), 1),
               round(median(m.speed) FILTER (m.secs_played >= 300), 1)
        FROM marts.player_game_tracking m JOIN core.games g USING (game_id)
        JOIN core.teams h ON h.team_id = g.home_team_id JOIN core.teams a ON a.team_id = g.away_team_id
        WHERE m.movement_suspect GROUP BY ALL ORDER BY g.game_date""").fetchall()
    redo = con.execute("""
        SELECT count(*), round(min(clean), 2), round(max(clean), 2), round(min(s.avg_speed), 2), round(max(s.avg_speed), 2)
        FROM (SELECT m.season_end_year, m.season_type, m.player_id, m.team_id,
                     sum(m.distance) FILTER (NOT m.movement_suspect) / (sum(m.secs_played) FILTER (NOT m.movement_suspect) / 3600.0) AS clean
              FROM marts.player_game_tracking m GROUP BY ALL) c
        JOIN marts.player_tracking_season s USING (season_end_year, season_type, player_id, team_id)
        WHERE s.movement_suspect AND c.clean IS NOT NULL""").fetchone()
    out = ["", "## Single games (marts.player_game_tracking)", "",
           f"Games flagged `movement_suspect` (a player with 300+ seconds above the per-game limit in rules.yaml): **{len(games)}**.", ""]
    if games:
        out += ["| game | date | home | away | players | max speed (mph) | median speed, 300+ s (mph) |", "|---|---|---|---|---|---|---|"]
        out += [f"| `{gid}` | {str(d)[:10]} | {h} | {a} | {n} | {mx} | {md} |" for gid, d, h, a, n, mx, md in games]
    if redo and redo[0]:
        out += ["", f"Flagged season rows with single-game boxes: **{redo[0]}**. NBA.com's season average speed for them: {redo[3]}-{redo[4]} mph; "
                f"recomputed from their single-game boxes without the flagged games (distance / hours played): **{redo[1]}-{redo[2]} mph**."]
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    con = db.connect(read_only=True)
    try:
        n = write_report(con, db.PROJECT_ROOT / "docs" / "validation" / "tracking_quality.md")
    finally:
        con.close()
    print(f"tracking_quality.md: {n} flagged player-seasons")


if __name__ == "__main__":
    main()
