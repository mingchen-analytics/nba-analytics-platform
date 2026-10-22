"""Our own player box score, counted from core.events (validation of the event table only).

marts.player_game_pbp: one row per (game, player) that appears on court or in an event.
It is **not** what the dashboard shows (that is the official box, reference.nba_player_box);
it is compared with the official box game by game (validate/box_vs_pbp.py) to show that
the events table can be trusted before possession-level metrics are built on it.

Counting (one source event = one count; nothing here decides possessions or stints):
- FGA / FGM: shot_missed + shot_made by player1; 3PA when the shot is a 3 (points = 3,
  shot chart `3PT Field Goal`, or — only without a shot-chart row — '3PT' in the text).
- FTA / FTM: free_throw by player1; made when points > 0.
- REB: rebound by player1 (team rebounds have no player).
- AST: player2 on shot_made. TOV: player1 on turnover. STL: the stealer is player2 on the
  turnover up to 2015-16 and in 2025-26, player3 in 2016-17 → 2024-25 (2020-21 playoffs have
  both); the two are never set together, so `coalesce(player2, player3)` is used.
- BLK: player3 on shot_missed (1996-97 → 2024-25), player2 in 2025-26 (roles differ by era,
  docs/validation/format_diff_2004-05_vs_2025-26.md). The 2025-26 extra block/steal rows
  (msg 92 / 95, event_type `other`) are not counted, so nothing is counted twice.
- PF: player1 on foul, except technical-type codes; a double personal foul also counts
  for player2.
- Seconds on court and plus-minus: the lineup shown on each event (staging.event_lineups,
  the same accounting as checks 5 and 6).

Usage:
    python -m nba_platform.marts.player_game_pbp
"""

from __future__ import annotations

import sys

from nba_platform import db
from nba_platform.validate.checks import _season_games_cte, pbp_player_seconds_sql

# NBA foul action-type codes that are not personal fouls (technicals, delay of game,
# defensive 3 seconds, excess timeout, too many players; 32 = flopping technical, new in
# 2023-24) — not counted in PF.
NON_PERSONAL_FOUL_SUBTYPES = (11, 12, 13, 16, 17, 18, 19, 25, 30, 32)
DOUBLE_PERSONAL_FOUL_SUBTYPE = 10
STATS = ["pts", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "reb", "ast", "stl", "blk", "tov", "pf"]


def player_game_pbp_sql(y: int, t: str) -> str:
    """One season's rows (same columns as marts.player_game_pbp)."""
    non_pf = ", ".join(map(str, NON_PERSONAL_FOUL_SUBTYPES))
    return f"""
        {_season_games_cte(y, t, pbp_only=True)},
        s AS (SELECT s.game_id, s.source_event_num, s.shot_type FROM core.shots s JOIN g USING (game_id)),
        e AS MATERIALIZED (
            SELECT e.game_id, e.event_seq, e.event_type, e.event_subtype, e.points, e.team_id,
                   e.player1_id, e.player2_id, e.player3_id, e.description, s.shot_type
            FROM core.events e JOIN g USING (game_id) LEFT JOIN s USING (game_id, source_event_num)),
        c AS (
            SELECT game_id, player1_id AS player_id, 'fga' AS k FROM e WHERE event_type IN ('shot_made', 'shot_missed')
            UNION ALL SELECT game_id, player1_id, 'fgm' FROM e WHERE event_type = 'shot_made'
            UNION ALL SELECT game_id, player1_id, 'fg3a' FROM e WHERE event_type IN ('shot_made', 'shot_missed')
                AND (points = 3 OR shot_type = '3PT Field Goal' OR (shot_type IS NULL AND description ILIKE '%3PT%'))
            UNION ALL SELECT game_id, player1_id, 'fg3m' FROM e WHERE event_type = 'shot_made' AND points = 3
            UNION ALL SELECT game_id, player1_id, 'fta' FROM e WHERE event_type = 'free_throw'
            UNION ALL SELECT game_id, player1_id, 'ftm' FROM e WHERE event_type = 'free_throw' AND points > 0
            UNION ALL SELECT game_id, player1_id, 'reb' FROM e WHERE event_type = 'rebound'
            UNION ALL SELECT game_id, player2_id, 'ast' FROM e WHERE event_type = 'shot_made'
            UNION ALL SELECT game_id, coalesce(player2_id, player3_id), 'stl' FROM e WHERE event_type = 'turnover'
            UNION ALL SELECT game_id, coalesce(player3_id, player2_id), 'blk' FROM e WHERE event_type = 'shot_missed'
            UNION ALL SELECT game_id, player1_id, 'tov' FROM e WHERE event_type = 'turnover'
            UNION ALL SELECT game_id, player1_id, 'pf' FROM e
                WHERE event_type = 'foul' AND coalesce(event_subtype, -1) NOT IN ({non_pf})
            UNION ALL SELECT game_id, player2_id, 'pf' FROM e
                WHERE event_type = 'foul' AND event_subtype = {DOUBLE_PERSONAL_FOUL_SUBTYPE}),
        counts AS (
            SELECT game_id, player_id,
                   {", ".join(f"count(*) FILTER (k = '{k}') AS {k}" for k in STATS if k != "pts")}
            FROM c WHERE player_id IS NOT NULL GROUP BY ALL),
        on_court AS (
            SELECT e.game_id, e.points, e.team_id AS scoring_team_id,
                   unnest(l.home_player_ids) AS player_id, g.home_team_id AS team_id
            FROM e JOIN staging.event_lineups l USING (game_id, event_seq) JOIN g USING (game_id)
            UNION ALL
            SELECT e.game_id, e.points, e.team_id, unnest(l.away_player_ids), g.away_team_id
            FROM e JOIN staging.event_lineups l USING (game_id, event_seq) JOIN g USING (game_id)),
        side AS (
            SELECT game_id, player_id, mode(team_id) AS team_id,
                   sum(CASE WHEN points = 0 THEN 0 WHEN scoring_team_id = team_id THEN points ELSE -points END) AS plus_minus
            FROM on_court GROUP BY ALL),
        event_team AS (
            SELECT game_id, player1_id AS player_id, mode(team_id) AS team_id FROM e
            WHERE player1_id IS NOT NULL AND team_id IS NOT NULL GROUP BY ALL),
        secs AS ({pbp_player_seconds_sql(y, t)}),
        keys AS (SELECT game_id, player_id FROM counts UNION SELECT game_id, player_id FROM side)
        SELECT k.game_id, {int(y)} AS season_end_year, '{t}' AS season_type, k.player_id,
               coalesce(side.team_id, event_team.team_id) AS team_id,
               coalesce(secs.pbp_secs, 0) AS secs_played,
               2 * coalesce(fgm, 0) + coalesce(fg3m, 0) + coalesce(ftm, 0) AS pts,
               {", ".join(f"coalesce({k}, 0) AS {k}" for k in STATS if k != "pts")},
               coalesce(side.plus_minus, 0) AS plus_minus
        FROM keys k
        LEFT JOIN counts USING (game_id, player_id)
        LEFT JOIN side USING (game_id, player_id)
        LEFT JOIN event_team USING (game_id, player_id)
        LEFT JOIN secs USING (game_id, player_id)"""


def build(con, seasons=None) -> int:
    """Rebuild marts.player_game_pbp for every loaded season (or the given (year, type) list)."""
    if seasons is None:
        seasons = con.execute("""SELECT DISTINCT season_end_year, season_type FROM core.games
                                 WHERE NOT coalesce(pbp_missing, FALSE) ORDER BY 1, 2""").fetchall()
    con.execute("CREATE SCHEMA IF NOT EXISTS marts")
    con.execute("BEGIN")
    try:
        con.execute("DROP TABLE IF EXISTS marts.player_game_pbp")
        for i, (y, t) in enumerate(seasons):
            sql = player_game_pbp_sql(y, t)
            con.execute(f"CREATE TABLE marts.player_game_pbp AS {sql}" if i == 0
                        else f"INSERT INTO marts.player_game_pbp {sql}")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return con.execute("SELECT count(*) FROM marts.player_game_pbp").fetchone()[0]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    con = db.connect()
    try:
        print(f"marts.player_game_pbp: {build(con):,} rows")
    finally:
        con.close()


if __name__ == "__main__":
    main()
