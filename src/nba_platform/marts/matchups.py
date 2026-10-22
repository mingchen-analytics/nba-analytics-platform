"""Matchup mart: who guarded whom, per game (NBA.com matchup data, official).

reference.matchups (shufinskiy `matchups_*`, 2017-18 -> 2024-25) holds one row per defender and guarded player
in a game, with every column as text and the NBA game id without its leading zeros ('21700001').
marts.matchup_pairs makes it typed and joinable: `game_id` is the 10-character id of core.games
('0021700001'), player and team ids are integers, seconds and counts are numbers. PRIMARY KEY
(game_id, defender_id, offender_id). Every number is NBA.com's (**official**); nothing is computed from our
events. The columns keep NBA.com's meaning:
- `matchup_secs` the time the defender was matched with the offender (NBA tracking), `partial_possessions` the
  possessions they shared (fractions of possessions), `pct_defender_time` / `pct_offense_time` / `pct_both_on`
  shares of the defender's / the offender's time / of the time both were on the floor;
- `player_pts` the offender's points and `team_pts` the offense's points while they were matched; the rest are
  counts while matched (assists, potential assists, turnovers, blocks, field goals, threes, free throws, help
  blocks and field goals, shooting fouls, switches onto the offender).

Hard fails (the build is rolled back): a game not in core.games, a player or team not in core.players /
core.teams, a defender whose team is not one of the game's two teams, a duplicate key, a value that is not
blank and not a number. Players not in that game's box score are counted (`not_in_box`), not failed.

Usage:
    python -m nba_platform.marts.matchups
"""

from __future__ import annotations

import sys
from pathlib import Path

from nba_platform import db
from nba_platform.seasons import season_label

# mart column -> (reference column, type)
NUMERIC = {
    "matchup_secs": ("matchup_minutes_sort", "DOUBLE"), "partial_possessions": ("partial_possessions", "DOUBLE"),
    "pct_defender_time": ("percentage_defender_total_time", "DOUBLE"), "pct_offense_time": ("percentage_offensive_total_time", "DOUBLE"),
    "pct_both_on": ("percentage_total_time_both_on", "DOUBLE"), "switches_on": ("switches_on", "INTEGER"),
    "player_pts": ("player_points", "INTEGER"), "team_pts": ("team_points", "INTEGER"), "assists": ("matchup_assists", "INTEGER"),
    "potential_assists": ("matchup_potential_assists", "INTEGER"), "turnovers": ("matchup_turnovers", "INTEGER"),
    "blocks": ("matchup_blocks", "INTEGER"), "fgm": ("matchup_field_goals_made", "INTEGER"), "fga": ("matchup_field_goals_attempted", "INTEGER"),
    "fg3m": ("matchup_three_pointers_made", "INTEGER"), "fg3a": ("matchup_three_pointers_attempted", "INTEGER"),
    "help_blocks": ("help_blocks", "INTEGER"), "help_fgm": ("help_field_goals_made", "INTEGER"), "help_fga": ("help_field_goals_attempted", "INTEGER"),
    "ftm": ("matchup_free_throws_made", "INTEGER"), "fta": ("matchup_free_throws_attempted", "INTEGER"), "shooting_fouls": ("shooting_fouls", "INTEGER"),
}


class MatchupMartError(RuntimeError):
    """The matchup mart cannot be built as is. The build is rolled back."""


DDL = f"""(
    game_id TEXT NOT NULL, season_end_year INTEGER NOT NULL, season_type TEXT NOT NULL, team_id INTEGER NOT NULL,
    defender_id INTEGER NOT NULL, offender_id INTEGER NOT NULL,
    {", ".join(f"{c} {t}" for c, (_, t) in NUMERIC.items())},
    PRIMARY KEY (game_id, defender_id, offender_id))"""


def _blank(col: str) -> str:
    return f"nullif(trim({col}), '')"


def insert_sql() -> str:
    casts = ", ".join(f"CAST({_blank(ref)} AS {t}) AS {c}" for c, (ref, t) in NUMERIC.items())
    return f"""
        SELECT lpad(game_id, 10, '0'), season_end_year, season_type, CAST(team_id AS INTEGER), CAST(person_id AS INTEGER),
               CAST(matchups_person_id AS INTEGER), {casts}
        FROM reference.matchups"""


def _one(con, sql: str):
    return con.execute(sql).fetchone()[0]


def _source_checks(con) -> None:
    """Before any cast: every value is blank or a number, the ids are numbers."""
    for c, (ref, t) in NUMERIC.items():
        bad = _one(con, f"SELECT count(*) FROM reference.matchups WHERE {_blank(ref)} IS NOT NULL AND try_cast({_blank(ref)} AS {t}) IS NULL")
        if bad:
            raise MatchupMartError(f"{bad} rows have a value in {ref} that is not a number")
    for col in ("person_id", "matchups_person_id", "team_id", "game_id"):
        bad = _one(con, f"SELECT count(*) FROM reference.matchups WHERE try_cast({_blank(col)} AS BIGINT) IS NULL")
        if bad:
            raise MatchupMartError(f"{bad} rows have a missing or non-numeric {col}")


def _checks(con) -> None:
    games = _one(con, "SELECT count(DISTINCT game_id) FROM marts_matchup_new WHERE game_id NOT IN (SELECT game_id FROM core.games)")
    if games:
        raise MatchupMartError(f"{games} games are not in core.games")
    players = _one(con, """SELECT count(DISTINCT p) FROM (SELECT defender_id AS p FROM marts_matchup_new UNION ALL SELECT offender_id FROM marts_matchup_new)
                           WHERE p NOT IN (SELECT player_id FROM core.players)""")
    if players:
        raise MatchupMartError(f"{players} players are not in core.players")
    if _one(con, "SELECT count(*) FROM marts_matchup_new WHERE team_id NOT IN (SELECT team_id FROM core.teams)"):
        raise MatchupMartError("a team is not in core.teams")
    wrong = _one(con, """SELECT count(*) FROM marts_matchup_new m JOIN core.games g USING (game_id)
                         WHERE m.team_id NOT IN (g.home_team_id, g.away_team_id)""")
    if wrong:
        raise MatchupMartError(f"{wrong} rows have a defender whose team did not play the game")
    dup = _one(con, "SELECT count(*) FROM (SELECT 1 FROM marts_matchup_new GROUP BY game_id, defender_id, offender_id HAVING count(*) > 1)")
    if dup:
        raise MatchupMartError(f"{dup} duplicate (game, defender, offender) keys")


def build(con) -> dict:
    """Rebuild marts.matchup_pairs in one transaction. Returns row counts."""
    con.execute("CREATE SCHEMA IF NOT EXISTS marts")
    con.execute("BEGIN")
    try:
        _source_checks(con)
        cols = ["game_id", "season_end_year", "season_type", "team_id", "defender_id", "offender_id", *NUMERIC]
        con.execute("DROP TABLE IF EXISTS marts_matchup_new")
        con.execute(f"CREATE TEMP TABLE marts_matchup_new AS SELECT * FROM ({insert_sql()}) AS t({', '.join(cols)})")
        _checks(con)
        con.execute("DROP TABLE IF EXISTS marts.matchup_pairs")
        con.execute(f"CREATE TABLE marts.matchup_pairs {DDL}")
        con.execute("INSERT INTO marts.matchup_pairs SELECT * FROM marts_matchup_new")
        out = {"rows": _one(con, "SELECT count(*) FROM marts.matchup_pairs"), "games": _one(con, "SELECT count(DISTINCT game_id) FROM marts.matchup_pairs"),
               "not_in_box": _one(con, """SELECT count(*) FROM marts.matchup_pairs m
                                          WHERE NOT EXISTS (SELECT 1 FROM marts.player_game b WHERE b.game_id = m.game_id AND b.player_id = m.defender_id)
                                             OR NOT EXISTS (SELECT 1 FROM marts.player_game b WHERE b.game_id = m.game_id AND b.player_id = m.offender_id)"""
                                 ) if _table_exists(con, "marts", "player_game") else None}
        con.execute("DROP TABLE marts_matchup_new")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return out


def _table_exists(con, schema: str, table: str) -> bool:
    return bool(_one(con, f"SELECT count(*) FROM information_schema.tables WHERE table_schema = '{schema}' AND table_name = '{table}'"))


def write_report(con, path: Path) -> dict:
    """Coverage of the matchup data against core.games (docs/validation/matchups_coverage.md). Numbers only."""
    rows = con.execute("""
        WITH m AS (SELECT season_end_year, season_type, count(*) AS pairs, count(DISTINCT game_id) AS games FROM marts.matchup_pairs GROUP BY ALL),
             c AS (SELECT season_end_year, season_type, count(*) FILTER (NOT coalesce(pbp_missing, FALSE)) AS core_games, count(*) AS all_games
                   FROM core.games GROUP BY ALL)
        SELECT m.season_end_year, m.season_type, m.pairs, m.games, c.core_games, c.all_games
        FROM m JOIN c USING (season_end_year, season_type) ORDER BY 2 DESC, 1""").fetchall()
    ratio = con.execute("""
        WITH x AS (SELECT game_id, defender_id AS p, sum(matchup_secs) AS secs FROM marts.matchup_pairs GROUP BY ALL),
             s AS (SELECT game_id, p, sum(end_secs - start_secs) AS floor_secs
                   FROM (SELECT game_id, start_secs, end_secs, unnest([home_p1, home_p2, home_p3, home_p4, home_p5, away_p1, away_p2, away_p3, away_p4, away_p5]) AS p
                         FROM core.stints) GROUP BY ALL)
        SELECT count(*), median(x.secs / s.floor_secs), quantile_cont(x.secs / s.floor_secs, 0.05), quantile_cont(x.secs / s.floor_secs, 0.95)
        FROM x JOIN s USING (game_id, p) WHERE s.floor_secs >= 600""").fetchone()
    lines = ["# Matchup data: coverage", "",
             "`marts.matchup_pairs` (NBA.com matchup data, 2017-18 -> 2024-25) against `core.games`. Numbers only.", "",
             "| season | type | player pairs | games in the matchup data | games in core (with play-by-play) | games without matchups |",
             "|---|---|---|---|---|---|"]
    for y, t, pairs, games, core, all_games in rows:
        lines.append(f"| {season_label(y)} | {t} | {pairs:,} | {games:,} | {core:,} | {max(core - games, 0):,} |")
    lines += ["", f"Sanity: for {int(ratio[0]):,} defender-games with 10+ minutes on the floor, the sum of a defender's matched seconds is "
              f"**{ratio[1]:.2f}** of his time on our stints (5th percentile {ratio[2]:.2f}, 95th {ratio[3]:.2f}); the defender is matched only "
              "while his team defends (about half the time) and not always, so the ratio is expected below 0.5.", ""]
    path.write_text(chr(10).join(lines), encoding="utf-8")
    return {"seasons": len(rows), "games_without_matchups": sum(max(r[4] - r[3], 0) for r in rows)}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    con = db.connect()
    try:
        print(build(con))
        print(write_report(con, db.PROJECT_ROOT / "docs" / "validation" / "matchups_coverage.md"))
    finally:
        con.close()


if __name__ == "__main__":
    main()
