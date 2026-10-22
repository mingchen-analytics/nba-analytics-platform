"""Season tracking and hustle mart: one row per player, season and team (NBA.com, official).

reference.nba_tracking is a wide table with one row per (season, type, measure, player, team);
each of the 12 measures fills only its own columns. This flattens the columns we show into
marts.player_tracking_season, PRIMARY KEY (season_end_year, season_type, player_id, team_id),
and adds the player hustle columns (2015-16 →; NULL before). A column that several measures
share (for example DRIVE_FG_PCT) is taken from its "home" measure only.

Everything here is an NBA.com value ("official"); nothing is computed from our events.
`kind` says how a page may scale a column: `count` (per game / per 36 minutes is meaningful)
or `rate` (a percentage, average or per-touch value; never scaled).

Hard fails: an unknown player_id, a duplicate key, a source column that is missing, or a
hustle row that has no tracking row would be lost (the spine is the union of both tables).

Usage:
    python -m nba_platform.marts.tracking
"""

from __future__ import annotations

import sys

from nba_platform import db

# group -> [(source measure, NBA column, kind)]; the mart column is the lower-case NBA column
GROUPS: dict[str, list[tuple[str, str, str]]] = {
    "Movement": [
        ("SpeedDistance", "DIST_MILES", "count"), ("SpeedDistance", "DIST_MILES_OFF", "count"),
        ("SpeedDistance", "DIST_MILES_DEF", "count"), ("SpeedDistance", "AVG_SPEED", "rate"),
        ("SpeedDistance", "AVG_SPEED_OFF", "rate"), ("SpeedDistance", "AVG_SPEED_DEF", "rate")],
    "Touches & passing": [
        ("Possessions", "TOUCHES", "count"), ("Possessions", "FRONT_CT_TOUCHES", "count"),
        ("Possessions", "TIME_OF_POSS", "count"), ("Possessions", "AVG_SEC_PER_TOUCH", "rate"),
        ("Possessions", "AVG_DRIB_PER_TOUCH", "rate"), ("Possessions", "PTS_PER_TOUCH", "rate"),
        ("Passing", "PASSES_MADE", "count"), ("Passing", "PASSES_RECEIVED", "count"),
        ("Passing", "POTENTIAL_AST", "count"), ("Passing", "AST_PTS_CREATED", "count"),
        ("Passing", "SECONDARY_AST", "count"), ("Passing", "FT_AST", "count"), ("Passing", "AST_TO_PASS_PCT", "rate"),
        ("PaintTouch", "PAINT_TOUCHES", "count"), ("PaintTouch", "PAINT_TOUCH_FGA", "count"),
        ("PostTouch", "POST_TOUCHES", "count"), ("PostTouch", "POST_TOUCH_FGA", "count"),
        ("ElbowTouch", "ELBOW_TOUCHES", "count")],
    "Drives & shooting": [
        ("Drives", "DRIVES", "count"), ("Drives", "DRIVE_FGA", "count"), ("Drives", "DRIVE_FG_PCT", "rate"),
        ("Drives", "DRIVE_PTS", "count"), ("Drives", "DRIVE_AST", "count"), ("Drives", "DRIVE_TOV", "count"),
        ("Drives", "DRIVE_PF", "count"),
        ("CatchShoot", "CATCH_SHOOT_FGA", "count"), ("CatchShoot", "CATCH_SHOOT_FG3A", "count"),
        ("CatchShoot", "CATCH_SHOOT_FG_PCT", "rate"), ("CatchShoot", "CATCH_SHOOT_EFG_PCT", "rate"),
        ("CatchShoot", "CATCH_SHOOT_PTS", "count"),
        ("PullUpShot", "PULL_UP_FGA", "count"), ("PullUpShot", "PULL_UP_FG3A", "count"),
        ("PullUpShot", "PULL_UP_FG_PCT", "rate"), ("PullUpShot", "PULL_UP_EFG_PCT", "rate"),
        ("PullUpShot", "PULL_UP_PTS", "count")],
    "Rebounding & rim defense": [
        ("Rebounding", "OREB_CHANCES", "count"), ("Rebounding", "OREB_CHANCE_PCT", "rate"),
        ("Rebounding", "DREB_CHANCES", "count"), ("Rebounding", "DREB_CHANCE_PCT", "rate"),
        ("Rebounding", "REB_CHANCES", "count"), ("Rebounding", "REB_CHANCE_PCT", "rate"),
        ("Rebounding", "REB_CONTEST_PCT", "rate"), ("Rebounding", "AVG_REB_DIST", "rate"),
        ("Defense", "DEF_RIM_FGA", "count"), ("Defense", "DEF_RIM_FGM", "count"), ("Defense", "DEF_RIM_FG_PCT", "rate")],
    "Hustle": [
        ("hustle", "CONTESTED_SHOTS", "count"), ("hustle", "CONTESTED_SHOTS_2PT", "count"),
        ("hustle", "CONTESTED_SHOTS_3PT", "count"), ("hustle", "DEFLECTIONS", "count"),
        ("hustle", "CHARGES_DRAWN", "count"), ("hustle", "SCREEN_ASSISTS", "count"),
        ("hustle", "SCREEN_AST_PTS", "count"), ("hustle", "LOOSE_BALLS_RECOVERED", "count"),
        ("hustle", "BOX_OUTS", "count")],
}
BASE_MEASURE = "Possessions"   # games and minutes come from here

KEYS = ["season_end_year", "season_type", "player_id", "team_id"]


def columns() -> list[tuple[str, str, str, str]]:
    """(group, measure, mart column, kind) for every shown column."""
    return [(g, m, c.lower(), k) for g, items in GROUPS.items() for m, c, k in items]


class TrackingMartError(RuntimeError):
    """The tracking mart cannot be built as is. The rebuild stops."""


def _check_source_columns(con) -> None:
    have_t = {r[0] for r in con.execute("DESCRIBE reference.nba_tracking").fetchall()}
    have_h = {r[0] for r in con.execute("DESCRIBE reference.nba_hustle").fetchall()}
    missing = [f"{m}.{c}" for m, c, _ in (x for items in GROUPS.values() for x in items)
               if c not in (have_h if m == "hustle" else have_t)]
    if missing:
        raise TrackingMartError(f"source columns missing: {missing}")


def ddl() -> str:
    cols = ",\n        ".join(f"{c} DOUBLE" for _, _, c, _ in columns())
    return f"""(
        season_end_year INTEGER NOT NULL, season_type TEXT NOT NULL, player_id INTEGER NOT NULL, team_id INTEGER NOT NULL,
        gp INTEGER, min DOUBLE, hustle_gp INTEGER, movement_suspect BOOLEAN,
        {cols},
        PRIMARY KEY (season_end_year, season_type, player_id, team_id))"""


def insert_sql(max_avg_speed: float = 5.5, min_minutes: float = 100) -> str:
    tracking = [f"any_value({c.upper()}) FILTER (request_param_1 = '{m}') AS {c}" for _, m, c, _ in columns() if m != "hustle"]
    # column order of the table = columns(); tracking and hustle columns are interleaved by group
    select = ", ".join(f"h.{c}" if m == "hustle" else f"t.{c}" for _, m, c, _ in columns())
    return f"""
        WITH spine AS (
            SELECT DISTINCT CAST(substr(season, 1, 4) AS INTEGER) + 1 AS season_end_year, season_type,
                            PLAYER_ID AS player_id, TEAM_ID AS team_id FROM reference.nba_tracking
            UNION
            SELECT DISTINCT CAST(substr(season, 1, 4) AS INTEGER) + 1, season_type, PLAYER_ID, TEAM_ID
            FROM reference.nba_hustle WHERE request_param_1 = 'player'),
        t AS (
            SELECT CAST(substr(season, 1, 4) AS INTEGER) + 1 AS season_end_year, season_type,
                   PLAYER_ID AS player_id, TEAM_ID AS team_id,
                   any_value(GP) FILTER (request_param_1 = '{BASE_MEASURE}') AS gp,
                   any_value(MIN) FILTER (request_param_1 = '{BASE_MEASURE}') AS min,
                   {", ".join(tracking)}
            FROM reference.nba_tracking GROUP BY ALL),
        h AS (
            SELECT CAST(substr(season, 1, 4) AS INTEGER) + 1 AS season_end_year, season_type,
                   PLAYER_ID AS player_id, TEAM_ID AS team_id, G AS hustle_gp,
                   {", ".join(f"{c.upper()} AS {c}" for _, m, c, _ in columns() if m == "hustle")}
            FROM reference.nba_hustle WHERE request_param_1 = 'player')
        SELECT s.season_end_year, s.season_type, s.player_id, s.team_id, t.gp, t.min, h.hustle_gp,
               t.avg_speed > {float(max_avg_speed)} AND t.min >= {float(min_minutes)} AS movement_suspect, {select}
        FROM spine s
        LEFT JOIN t USING (season_end_year, season_type, player_id, team_id)
        LEFT JOIN h USING (season_end_year, season_type, player_id, team_id)"""


def build(con, rules: dict | None = None) -> dict:
    """Rebuild marts.player_tracking_season in one transaction. Returns row counts."""
    from nba_platform.rules import load_rules

    cfg = (rules or load_rules())["dashboard"]
    max_speed, min_minutes = float(cfg["tracking_max_plausible_avg_speed_mph"]), float(cfg.get("tracking_suspect_min_minutes", 100))
    _check_source_columns(con)
    unknown = con.execute("""
        SELECT count(DISTINCT PLAYER_ID) FROM (SELECT PLAYER_ID FROM reference.nba_tracking
                                               UNION ALL SELECT PLAYER_ID FROM reference.nba_hustle WHERE request_param_1 = 'player')
        WHERE PLAYER_ID NOT IN (SELECT player_id FROM core.players)""").fetchone()[0]
    if unknown:
        raise TrackingMartError(f"{unknown} tracking / hustle players are not in core.players")
    con.execute("CREATE SCHEMA IF NOT EXISTS marts")
    # The wide INSERT (about 50 aggregates) overflowed a DuckDB worker thread's stack on Windows
    # (stack overflow in 5 of 6 test runs, 2026-10-21); one thread for this small table avoids it.
    threads = con.execute("SELECT current_setting('threads')").fetchone()[0]
    con.execute("SET threads = 1")
    try:
        return _build_in_transaction(con, max_speed, min_minutes)
    finally:
        con.execute(f"SET threads = {int(threads)}")


def _build_in_transaction(con, max_speed: float, min_minutes: float) -> dict:
    con.execute("BEGIN")
    try:
        con.execute("DROP TABLE IF EXISTS marts.player_tracking_season")
        con.execute(f"CREATE TABLE marts.player_tracking_season {ddl()}")
        con.execute(f"INSERT INTO marts.player_tracking_season {insert_sql(max_speed, min_minutes)}")
        out = {"rows": con.execute("SELECT count(*) FROM marts.player_tracking_season").fetchone()[0],
               "with_tracking": con.execute("SELECT count(*) FROM marts.player_tracking_season WHERE gp IS NOT NULL").fetchone()[0],
               "with_hustle": con.execute("SELECT count(*) FROM marts.player_tracking_season WHERE hustle_gp IS NOT NULL").fetchone()[0],
               "movement_suspect": con.execute("SELECT count(*) FROM marts.player_tracking_season WHERE movement_suspect").fetchone()[0]}
        lost = con.execute("""
            SELECT (SELECT count(*) FROM (SELECT DISTINCT season, season_type, PLAYER_ID, TEAM_ID FROM reference.nba_hustle
                                          WHERE request_param_1 = 'player')) - count(hustle_gp) FROM marts.player_tracking_season""").fetchone()[0]
        if lost:
            raise TrackingMartError(f"{lost} hustle rows did not reach the mart")
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
