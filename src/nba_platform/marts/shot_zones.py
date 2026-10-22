"""Shooting marts for the dashboard: shot frequency and accuracy by court zone, with league
percentiles (Cleaning the Glass style layout idea; the numbers are ours).

Built from core.shots (NBA shot chart data, every season). Zone = NBA's `shot_zone_basic`
label; a shot without one is `Unknown`, never guessed. Shots carrying data-quality flags
(core.shot_quality_flags) are counted, not removed; the share flagged is stored so a page
can show it.

- marts.shot_zones_league (season_end_year, season_type, zone)
- marts.shot_zones_team   (season_end_year, season_type, team_id, side, zone)  side = offense | defense
- marts.shot_zones_player (season_end_year, season_type, player_id, zone)      a traded player is combined

Percentiles (0-100, higher = better for the shooter) are computed among players with at least
`dashboard.shot_percentile_min_season_fga` attempts in the season, and for accuracy also at
least `dashboard.shot_percentile_min_zone_fga` in the zone (config/rules.yaml). Otherwise NULL.

Usage:
    python -m nba_platform.marts.shot_zones
"""

from __future__ import annotations

import sys

from nba_platform import db
from nba_platform.rules import load_rules

ZONES = ["Restricted Area", "In The Paint (Non-RA)", "Mid-Range", "Left Corner 3", "Right Corner 3",
         "Above the Break 3", "Backcourt", "Unknown"]

CREATE_SHOTS = """
    CREATE TEMP TABLE shots_z AS
    SELECT g.season_end_year, g.season_type, s.game_id, s.source_event_num, s.player_id, s.team_id,
           CASE WHEN g.home_team_id = s.team_id THEN g.away_team_id ELSE g.home_team_id END AS opponent_team_id,
           coalesce(s.shot_zone_basic, 'Unknown') AS zone, s.made,
           EXISTS (SELECT 1 FROM core.shot_quality_flags f
                   WHERE f.game_id = s.game_id AND f.source_event_num = s.source_event_num) AS flagged
    FROM core.shots s JOIN core.games g USING (game_id)"""

DDL = {
    "marts.shot_zones_league": """(
        season_end_year INTEGER NOT NULL, season_type TEXT NOT NULL, zone TEXT NOT NULL,
        fga BIGINT NOT NULL, fgm BIGINT NOT NULL, fg_pct DOUBLE, freq DOUBLE,
        PRIMARY KEY (season_end_year, season_type, zone))""",
    "marts.shot_zones_team": """(
        season_end_year INTEGER NOT NULL, season_type TEXT NOT NULL, team_id INTEGER NOT NULL,
        side TEXT NOT NULL, zone TEXT NOT NULL, fga BIGINT NOT NULL, fgm BIGINT NOT NULL, fg_pct DOUBLE, freq DOUBLE,
        league_fg_pct DOUBLE, league_freq DOUBLE,
        PRIMARY KEY (season_end_year, season_type, team_id, side, zone))""",
    "marts.shot_zones_player": """(
        season_end_year INTEGER NOT NULL, season_type TEXT NOT NULL, player_id INTEGER NOT NULL, zone TEXT NOT NULL,
        fga BIGINT NOT NULL, fgm BIGINT NOT NULL, fg_pct DOUBLE, freq DOUBLE, flagged_share DOUBLE,
        league_fg_pct DOUBLE, league_freq DOUBLE, fg_pct_percentile DOUBLE, freq_percentile DOUBLE,
        PRIMARY KEY (season_end_year, season_type, player_id, zone))""",
}


def _insert_league() -> str:
    return """
        WITH a AS (SELECT season_end_year, season_type, zone, count(*) AS fga, count(*) FILTER (made) AS fgm
                   FROM shots_z GROUP BY ALL)
        SELECT season_end_year, season_type, zone, fga, fgm, fgm / fga::DOUBLE,
               fga / sum(fga) OVER (PARTITION BY season_end_year, season_type)::DOUBLE
        FROM a"""


def _insert_team() -> str:
    # offense: the team's own shots; defense: shots taken against it
    return """
        WITH t AS (
            SELECT season_end_year, season_type, team_id, 'offense' AS side, zone, made FROM shots_z
            UNION ALL
            SELECT season_end_year, season_type, opponent_team_id, 'defense', zone, made FROM shots_z),
        a AS (SELECT season_end_year, season_type, team_id, side, zone, count(*) AS fga, count(*) FILTER (made) AS fgm
              FROM t GROUP BY ALL)
        SELECT a.season_end_year, a.season_type, a.team_id, a.side, a.zone, a.fga, a.fgm, a.fgm / a.fga::DOUBLE,
               a.fga / sum(a.fga) OVER (PARTITION BY a.season_end_year, a.season_type, a.team_id, a.side)::DOUBLE,
               l.fg_pct, l.freq
        FROM a JOIN marts.shot_zones_league l USING (season_end_year, season_type, zone)"""


def _insert_player(min_season_fga: int, min_zone_fga: int) -> str:
    return f"""
        WITH a AS (
            SELECT season_end_year, season_type, player_id, zone, count(*) AS fga, count(*) FILTER (made) AS fgm,
                   count(*) FILTER (flagged) / count(*)::DOUBLE AS flagged_share
            FROM shots_z GROUP BY ALL),
        b AS (
            SELECT *, fgm / fga::DOUBLE AS fg_pct,
                   fga / sum(fga) OVER (PARTITION BY season_end_year, season_type, player_id)::DOUBLE AS freq,
                   sum(fga) OVER (PARTITION BY season_end_year, season_type, player_id) AS season_fga
            FROM a)
        SELECT b.season_end_year, b.season_type, b.player_id, b.zone, b.fga, b.fgm, b.fg_pct, b.freq, b.flagged_share,
               l.fg_pct, l.freq,
               CASE WHEN b.season_fga >= {min_season_fga} AND b.fga >= {min_zone_fga} THEN
                   100 * percent_rank() OVER (PARTITION BY b.season_end_year, b.season_type, b.zone,
                                                           (b.season_fga >= {min_season_fga} AND b.fga >= {min_zone_fga})
                                              ORDER BY b.fg_pct) END,
               CASE WHEN b.season_fga >= {min_season_fga} THEN
                   100 * percent_rank() OVER (PARTITION BY b.season_end_year, b.season_type, b.zone, (b.season_fga >= {min_season_fga})
                                              ORDER BY b.freq) END
        FROM b JOIN marts.shot_zones_league l USING (season_end_year, season_type, zone)"""


def build(con, rules: dict | None = None) -> dict:
    """Rebuild the three shooting marts in one transaction. Returns row counts."""
    cfg = (rules or load_rules())["dashboard"]
    min_season, min_zone = int(cfg["shot_percentile_min_season_fga"]), int(cfg["shot_percentile_min_zone_fga"])
    inserts = {"marts.shot_zones_league": _insert_league(), "marts.shot_zones_team": _insert_team(),
               "marts.shot_zones_player": _insert_player(min_season, min_zone)}
    con.execute("CREATE SCHEMA IF NOT EXISTS marts")
    con.execute("BEGIN")
    try:
        for name in reversed(list(DDL)):
            con.execute(f"DROP TABLE IF EXISTS {name}")
        con.execute("DROP TABLE IF EXISTS shots_z")
        con.execute(CREATE_SHOTS)
        for name in DDL:
            con.execute(f"CREATE TABLE {name} {DDL[name]}")
            con.execute(f"INSERT INTO {name} {inserts[name]}")
        con.execute("DROP TABLE shots_z")
        out = {n: con.execute(f"SELECT count(*) FROM {n}").fetchone()[0] for n in DDL}
        out["shots_in_player_zones"] = con.execute("SELECT sum(fga) FROM marts.shot_zones_player").fetchone()[0]
        out["shots_in_core"] = con.execute("SELECT count(*) FROM core.shots").fetchone()[0]
        if out["shots_in_player_zones"] != out["shots_in_core"]:
            raise RuntimeError(f"shot zones lose or duplicate shots: {out}")
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
