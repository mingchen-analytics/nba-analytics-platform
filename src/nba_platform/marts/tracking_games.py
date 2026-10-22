"""Single-game tracking and hustle mart: one row per player and game (NBA.com, official).

Built from reference.nba_box_tracking (BoxScorePlayerTrackV3) and reference.nba_box_hustle
(BoxScoreHustleV2), which the overnight batch loads from cached JSON. marts.player_game_tracking,
PRIMARY KEY (game_id, player_id). Every number is NBA.com's; nothing is computed from our events.

Implausible movement data is flagged per **game**, never deleted: a game is `movement_suspect` when any
player with at least `dashboard.tracking_game_min_secs` seconds has an average speed above
`dashboard.tracking_game_max_plausible_speed_mph` (config/rules.yaml). Found 2026-10-22: three 2025-26
regular-season games carry speeds of 60-338 mph for nearly every player; they explain the whole 2025-26
season-level defect (docs/validation/tracking_quality.md).

Rows of players who did not play (`secs_played` 0 or empty: "DNP" rows, no measurements) are left out and
counted (`dnp_rows`); players who never played are not in core.players. Hard fails, on the rows of players
who played: an unknown player_id, a game not in core.games, a duplicate (game, player).

Usage:
    python -m nba_platform.marts.tracking_games
"""

from __future__ import annotations

import sys

from nba_platform import db
from nba_platform.rules import load_rules

TRACKING_COLS = ["distance", "speed", "touches", "passes", "assists", "secondary_assists", "free_throw_assists",
                 "rebound_chances_offensive", "rebound_chances_defensive", "rebound_chances_total",
                 "contested_field_goals_made", "contested_field_goals_attempted",
                 "uncontested_field_goals_made", "uncontested_field_goals_attempted",
                 "defended_at_rim_field_goals_made", "defended_at_rim_field_goals_attempted"]
HUSTLE_COLS = ["contested_shots", "contested_shots2pt", "contested_shots3pt", "deflections", "charges_drawn",
               "screen_assists", "screen_assist_points", "loose_balls_recovered_total", "box_outs"]


PLAYED = "coalesce(secs_played, 0) > 0"


class TrackingGamesError(RuntimeError):
    """The single-game tracking mart cannot be built as is. The build is rolled back."""


DDL = f"""(
    game_id TEXT NOT NULL, season_end_year INTEGER NOT NULL, season_type TEXT NOT NULL, team_id INTEGER, player_id INTEGER NOT NULL,
    secs_played DOUBLE, has_tracking BOOLEAN NOT NULL, has_hustle BOOLEAN NOT NULL, movement_suspect BOOLEAN NOT NULL,
    {", ".join(f"{c} DOUBLE" for c in TRACKING_COLS + HUSTLE_COLS)},
    PRIMARY KEY (game_id, player_id))"""


def insert_sql(max_speed: float, min_secs: float) -> str:
    return f"""
        WITH t AS (SELECT * FROM reference.nba_box_tracking WHERE {PLAYED}),
             h AS (SELECT * FROM reference.nba_box_hustle WHERE {PLAYED}),
             spine AS (SELECT game_id, person_id FROM t UNION SELECT game_id, person_id FROM h),
             bad AS (SELECT DISTINCT game_id FROM t WHERE speed > {float(max_speed)} AND secs_played >= {float(min_secs)})
        SELECT s.game_id, g.season_end_year, g.season_type, coalesce(t.team_id, h.team_id), s.person_id,
               coalesce(t.secs_played, h.secs_played), t.game_id IS NOT NULL, h.game_id IS NOT NULL,
               s.game_id IN (SELECT game_id FROM bad),
               {", ".join(f"t.{c}" for c in TRACKING_COLS)}, {", ".join(f"h.{c}" for c in HUSTLE_COLS)}
        FROM spine s JOIN core.games g USING (game_id)
        LEFT JOIN t ON t.game_id = s.game_id AND t.person_id = s.person_id
        LEFT JOIN h ON h.game_id = s.game_id AND h.person_id = s.person_id"""


def build(con, rules: dict | None = None) -> dict:
    """Rebuild marts.player_game_tracking in one transaction. Returns row counts."""
    cfg = (rules or load_rules())["dashboard"]
    max_speed, min_secs = float(cfg["tracking_game_max_plausible_speed_mph"]), float(cfg["tracking_game_min_secs"])
    for table in ("reference.nba_box_tracking", "reference.nba_box_hustle"):
        dup = con.execute(f"SELECT count(*) FROM (SELECT game_id, person_id FROM {table} WHERE {PLAYED} GROUP BY ALL HAVING count(*) > 1)").fetchone()[0]
        if dup:
            raise TrackingGamesError(f"{dup} duplicate (game, player) rows in {table}")
    unknown = con.execute(f"""SELECT count(DISTINCT person_id) FROM (SELECT person_id FROM reference.nba_box_tracking WHERE {PLAYED}
                                                                    UNION ALL SELECT person_id FROM reference.nba_box_hustle WHERE {PLAYED})
                              WHERE person_id NOT IN (SELECT player_id FROM core.players)""").fetchone()[0]
    if unknown:
        raise TrackingGamesError(f"{unknown} players in the single-game boxes are not in core.players")
    games = con.execute("""SELECT count(DISTINCT game_id) FROM (SELECT game_id FROM reference.nba_box_tracking
                                                                UNION ALL SELECT game_id FROM reference.nba_box_hustle)
                           WHERE game_id NOT IN (SELECT game_id FROM core.games)""").fetchone()[0]
    if games:
        raise TrackingGamesError(f"{games} games in the single-game boxes are not in core.games")
    con.execute("CREATE SCHEMA IF NOT EXISTS marts")
    con.execute("BEGIN")
    try:
        con.execute("DROP TABLE IF EXISTS marts.player_game_tracking")
        con.execute(f"CREATE TABLE marts.player_game_tracking {DDL}")
        con.execute(f"INSERT INTO marts.player_game_tracking {insert_sql(max_speed, min_secs)}")
        out = dict(zip(["rows", "games", "suspect_games"], con.execute(
            "SELECT count(*), count(DISTINCT game_id), count(DISTINCT game_id) FILTER (movement_suspect) FROM marts.player_game_tracking").fetchone()))
        out["dnp_rows"] = con.execute(f"""SELECT count(*) FROM (SELECT game_id, person_id FROM reference.nba_box_tracking WHERE NOT {PLAYED}
                                          UNION SELECT game_id, person_id FROM reference.nba_box_hustle WHERE NOT {PLAYED})""").fetchone()[0]
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    con = db.connect()
    try:
        print(build(con))
    finally:
        con.close()


if __name__ == "__main__":
    main()
