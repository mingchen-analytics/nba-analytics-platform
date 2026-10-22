"""On/off and lineup marts: team results with a player (or a five-man lineup) on the floor.

Built from core.stints, core.possessions, core.possession_stint_segments and core.events; nothing
comes from the NBA.com box score. One row per (season, type, team, player) in
marts.player_onoff_season and one per (season, type, team, lineup) in marts.lineup_stats.

Crediting (CLAUDE.md "Substitution during a possession": the A/B/C question is still **open**; this
is the `pbpstats_compat` hybrid, recorded in `credit_method` = 'pbpstats_hybrid'):
- a possession (and its heave / garbage flags) is credited to the stint that is on the floor
  when it ends (the last of its stint segments), for the offense lineup and the defense lineup;
- the points of a field goal are credited with the possession; the points of a free throw go to the
  stint on the floor at the foul (`foul_event_seq`); a non-technical free throw without a linked foul
  (`ft_without_foul`, counted in the report) goes to the stint of the free throw itself;
- technical free throws and free throws between possessions belong to no possession and are not
  counted anywhere in these tables (CLAUDE.md "Lineup efficiency").
Possessions flagged `is_end_of_period_heave` or `is_garbage_time` are all counted; their counts are
stored (`*_heave_poss`, `*_garbage_poss`) so a page can exclude them. Nothing is excluded here.

Names: `o` = the team on offense, `d` = on defense; `on` = player on the floor, `off` = not (the
team's total minus `on`, same team and season; a traded player has one row per team).

Hard fails (the build is rolled back): a possession without a stint segment, an offense team that is
neither home nor away, points not conserved, a team-season where the players' possessions are not
5 times the lineups' possessions, or more than one rules version / profile in core.possessions.

Usage:
    python -m nba_platform.marts.onoff
"""

from __future__ import annotations

import sys
from pathlib import Path

from nba_platform import db
from nba_platform.seasons import season_label

CREDIT_METHOD = "pbpstats_hybrid"


class OnOffMartError(RuntimeError):
    """The on/off marts cannot be built as is. The build is rolled back."""


STAT_COLS = ["o_poss", "o_pts", "o_heave_poss", "o_garbage_poss", "d_poss", "d_pts", "d_heave_poss", "d_garbage_poss"]

DDL_PLAYER = f"""(
    season_end_year INTEGER NOT NULL, season_type TEXT NOT NULL, team_id INTEGER NOT NULL, player_id INTEGER NOT NULL,
    games INTEGER NOT NULL, on_secs DOUBLE NOT NULL, off_secs DOUBLE NOT NULL,
    {", ".join(f"on_{c} BIGINT NOT NULL" for c in STAT_COLS)},
    {", ".join(f"off_{c} BIGINT NOT NULL" for c in STAT_COLS)},
    on_ortg DOUBLE, on_drtg DOUBLE, on_net DOUBLE, off_ortg DOUBLE, off_drtg DOUBLE, off_net DOUBLE, net_on_minus_off DOUBLE,
    credit_method TEXT NOT NULL, rules_version TEXT NOT NULL, rules_profile TEXT NOT NULL,
    PRIMARY KEY (season_end_year, season_type, team_id, player_id))"""

DDL_LINEUP = f"""(
    season_end_year INTEGER NOT NULL, season_type TEXT NOT NULL, team_id INTEGER NOT NULL, lineup_key TEXT NOT NULL,
    p1 INTEGER NOT NULL, p2 INTEGER NOT NULL, p3 INTEGER NOT NULL, p4 INTEGER NOT NULL, p5 INTEGER NOT NULL,
    games INTEGER NOT NULL, stints INTEGER NOT NULL, secs DOUBLE NOT NULL,
    {", ".join(f"{c} BIGINT NOT NULL" for c in STAT_COLS)},
    ortg DOUBLE, drtg DOUBLE, net DOUBLE,
    credit_method TEXT NOT NULL, rules_version TEXT NOT NULL, rules_profile TEXT NOT NULL,
    PRIMARY KEY (season_end_year, season_type, team_id, lineup_key))"""

# possession -> the stint on the floor when it ends
POSS_END = """
    CREATE TEMP TABLE poss_end AS
    SELECT p.game_id, p.possession_id, p.offense_team_id, p.is_end_of_period_heave AS heave, p.is_garbage_time AS garbage,
           s.end_stint_id
    FROM core.possessions p
    LEFT JOIN (SELECT game_id, possession_id, arg_max(stint_id, segment_seq) AS end_stint_id
               FROM core.possession_stint_segments GROUP BY ALL) s USING (game_id, possession_id)"""

# scoring events inside possessions -> the stint that is credited with the points
CREDIT_POINTS = """
    CREATE TEMP TABLE credit_points AS
    SELECT e.game_id, e.team_id AS scoring_team_id, e.points,
           CASE WHEN e.event_type = 'free_throw' THEN coalesce(f.stint_id, e.stint_id) ELSE pe.end_stint_id END AS stint_id,
           e.event_type = 'free_throw' AND f.stint_id IS NULL AS ft_without_foul
    FROM core.events e
    JOIN poss_end pe ON pe.game_id = e.game_id AND pe.possession_id = e.possession_id
    LEFT JOIN core.events f ON f.game_id = e.game_id AND f.event_seq = e.foul_event_seq
    WHERE e.points > 0 AND NOT coalesce(e.is_technical_ft, FALSE) AND NOT coalesce(e.is_between_possessions_ft, FALSE)"""

# what each team's offense got in each stint (long format: possessions and points are separate rows)
CREDITS = """
    CREATE TEMP TABLE credits AS
    SELECT game_id, stint_id, off_team_id, sum(poss) AS poss, sum(pts) AS pts, sum(heave) AS heave, sum(garbage) AS garbage
    FROM (SELECT game_id, end_stint_id AS stint_id, offense_team_id AS off_team_id, 1 AS poss, 0 AS pts,
                 CAST(heave AS INTEGER) AS heave, CAST(garbage AS INTEGER) AS garbage FROM poss_end
          UNION ALL
          SELECT game_id, stint_id, scoring_team_id, 0, points, 0, 0 FROM credit_points)
    GROUP BY ALL"""

# one row per (stint, team on the floor): seconds, the five players, and the team's offense / defense credit
STINT_TEAM = """
    CREATE TEMP TABLE stint_team AS
    WITH sides AS (
        SELECT s.game_id, s.stint_id, g.season_end_year, g.season_type, g.home_team_id AS team_id, g.away_team_id AS opp_team_id,
               s.end_secs - s.start_secs AS secs, [s.home_p1, s.home_p2, s.home_p3, s.home_p4, s.home_p5] AS players
        FROM core.stints s JOIN core.games g USING (game_id)
        UNION ALL
        SELECT s.game_id, s.stint_id, g.season_end_year, g.season_type, g.away_team_id, g.home_team_id,
               s.end_secs - s.start_secs, [s.away_p1, s.away_p2, s.away_p3, s.away_p4, s.away_p5]
        FROM core.stints s JOIN core.games g USING (game_id))
    SELECT x.game_id, x.stint_id, x.season_end_year, x.season_type, x.team_id, x.secs, x.players,
           coalesce(o.poss, 0) AS o_poss, coalesce(o.pts, 0) AS o_pts, coalesce(o.heave, 0) AS o_heave_poss, coalesce(o.garbage, 0) AS o_garbage_poss,
           coalesce(d.poss, 0) AS d_poss, coalesce(d.pts, 0) AS d_pts, coalesce(d.heave, 0) AS d_heave_poss, coalesce(d.garbage, 0) AS d_garbage_poss
    FROM sides x
    LEFT JOIN credits o ON o.game_id = x.game_id AND o.stint_id = x.stint_id AND o.off_team_id = x.team_id
    LEFT JOIN credits d ON d.game_id = x.game_id AND d.stint_id = x.stint_id AND d.off_team_id = x.opp_team_id"""

SUMS = ", ".join(f"CAST(sum({c}) AS BIGINT) AS {c}" for c in STAT_COLS)


def _rate(pts: str, poss: str) -> str:
    return f"CASE WHEN {poss} > 0 THEN 100.0 * {pts} / {poss} END"


def _insert_player(version: tuple[str, str]) -> str:
    on_cols = ", ".join(f"on_{c}" for c in STAT_COLS)
    off_cols = ", ".join(f"t.{c} - p.on_{c} AS off_{c}" for c in STAT_COLS)
    return f"""
        INSERT INTO marts.player_onoff_season
        WITH p AS (
            SELECT season_end_year, season_type, team_id, player_id, count(DISTINCT game_id) AS games, sum(secs) AS on_secs,
                   {", ".join(f"CAST(sum({c}) AS BIGINT) AS on_{c}" for c in STAT_COLS)}
            FROM (SELECT season_end_year, season_type, team_id, game_id, secs, {", ".join(STAT_COLS)}, unnest(players) AS player_id
                  FROM stint_team)
            GROUP BY season_end_year, season_type, team_id, player_id),
        t AS (SELECT season_end_year, season_type, team_id, sum(secs) AS secs, {SUMS} FROM stint_team GROUP BY ALL),
        r AS (SELECT p.season_end_year, p.season_type, p.team_id, p.player_id, p.games, p.on_secs, t.secs - p.on_secs AS off_secs,
                     {", ".join(f"p.on_{c}" for c in STAT_COLS)}, {off_cols}
              FROM p JOIN t USING (season_end_year, season_type, team_id))
        SELECT season_end_year, season_type, team_id, player_id, games, on_secs, off_secs, {on_cols},
               {", ".join(f"off_{c}" for c in STAT_COLS)},
               {_rate("on_o_pts", "on_o_poss")}, {_rate("on_d_pts", "on_d_poss")},
               {_rate("on_o_pts", "on_o_poss")} - {_rate("on_d_pts", "on_d_poss")},
               {_rate("off_o_pts", "off_o_poss")}, {_rate("off_d_pts", "off_d_poss")},
               {_rate("off_o_pts", "off_o_poss")} - {_rate("off_d_pts", "off_d_poss")},
               ({_rate("on_o_pts", "on_o_poss")} - {_rate("on_d_pts", "on_d_poss")})
                 - ({_rate("off_o_pts", "off_o_poss")} - {_rate("off_d_pts", "off_d_poss")}),
               '{CREDIT_METHOD}', '{version[0]}', '{version[1]}'
        FROM r"""


def _insert_lineup(version: tuple[str, str]) -> str:
    return f"""
        INSERT INTO marts.lineup_stats
        WITH l AS (SELECT *, list_sort(players) AS lp FROM stint_team)
        SELECT season_end_year, season_type, team_id, array_to_string(lp, '-') AS lineup_key,
               lp[1], lp[2], lp[3], lp[4], lp[5], count(DISTINCT game_id), count(*), sum(secs), {SUMS},
               {_rate("sum(o_pts)", "sum(o_poss)")}, {_rate("sum(d_pts)", "sum(d_poss)")},
               {_rate("sum(o_pts)", "sum(o_poss)")} - {_rate("sum(d_pts)", "sum(d_poss)")},
               '{CREDIT_METHOD}', '{version[0]}', '{version[1]}'
        FROM l GROUP BY season_end_year, season_type, team_id, lp"""


def _one(con, sql: str):
    return con.execute(sql).fetchone()[0]


def _hard_checks(con) -> None:
    n_poss = _one(con, "SELECT count(*) FROM core.possessions")
    if _one(con, "SELECT count(*) FROM poss_end WHERE end_stint_id IS NULL"):
        raise OnOffMartError("a possession has no stint segment")
    if _one(con, "SELECT count(*) FROM poss_end") != n_poss:
        raise OnOffMartError("possessions were duplicated or lost in the stint join")
    bad = _one(con, """SELECT count(*) FROM poss_end pe JOIN core.games g USING (game_id)
                       WHERE pe.offense_team_id NOT IN (g.home_team_id, g.away_team_id)""")
    if bad:
        raise OnOffMartError(f"{bad} possessions have an offense team that is neither home nor away")
    pts_poss, pts_credit = _one(con, "SELECT sum(points) FROM core.possessions"), _one(con, "SELECT sum(points) FROM credit_points")
    if pts_poss != pts_credit:
        raise OnOffMartError(f"points not conserved: possessions {pts_poss}, credited {pts_credit}")
    if _one(con, "SELECT sum(o_poss) FROM stint_team") != n_poss or _one(con, "SELECT sum(d_poss) FROM stint_team") != n_poss:
        raise OnOffMartError("possessions credited to stints differ from core.possessions")
    off = con.execute("""
        WITH p AS (SELECT season_end_year, season_type, team_id, sum(on_o_poss) AS po, sum(on_d_poss) AS pd, sum(on_o_pts) AS pp, sum(on_secs) AS ps
                   FROM marts.player_onoff_season GROUP BY ALL),
             l AS (SELECT season_end_year, season_type, team_id, sum(o_poss) AS lo, sum(d_poss) AS ld, sum(o_pts) AS lp, sum(secs) AS ls
                   FROM marts.lineup_stats GROUP BY ALL)
        SELECT count(*) FROM p JOIN l USING (season_end_year, season_type, team_id)
        WHERE p.po <> 5 * l.lo OR p.pd <> 5 * l.ld OR p.pp <> 5 * l.lp OR abs(p.ps - 5 * l.ls) > 1e-6""").fetchone()[0]
    if off:
        raise OnOffMartError(f"{off} team-seasons: the players' possessions, points or seconds are not 5 times the lineups'")


def build(con) -> dict:
    """Rebuild marts.player_onoff_season and marts.lineup_stats in one transaction. Returns row counts."""
    versions = con.execute("SELECT DISTINCT rules_version, rules_profile FROM core.possessions").fetchall()
    if len(versions) != 1:
        raise OnOffMartError(f"core.possessions holds {len(versions)} rules versions / profiles; expected exactly one: {versions}")
    version = versions[0]
    con.execute("CREATE SCHEMA IF NOT EXISTS marts")
    con.execute("BEGIN")
    try:
        for t in ("poss_end", "credit_points", "credits", "stint_team"):
            con.execute(f"DROP TABLE IF EXISTS {t}")
        con.execute(POSS_END)
        con.execute(CREDIT_POINTS)
        con.execute(CREDITS)
        con.execute(STINT_TEAM)
        con.execute("DROP TABLE IF EXISTS marts.player_onoff_season")
        con.execute("DROP TABLE IF EXISTS marts.lineup_stats")
        con.execute(f"CREATE TABLE marts.player_onoff_season {DDL_PLAYER}")
        con.execute(f"CREATE TABLE marts.lineup_stats {DDL_LINEUP}")
        con.execute(_insert_player(version))
        con.execute(_insert_lineup(version))
        _hard_checks(con)
        out = {"player_rows": _one(con, "SELECT count(*) FROM marts.player_onoff_season"),
               "lineup_rows": _one(con, "SELECT count(*) FROM marts.lineup_stats"),
               "ft_without_foul": _one(con, "SELECT count(*) FROM credit_points WHERE ft_without_foul"),
               "rules_version": version[0], "rules_profile": version[1]}
        for t in ("poss_end", "credit_points", "credits", "stint_team"):
            con.execute(f"DROP TABLE {t}")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return out


def write_report(con, path: Path) -> None:
    """Per-season numbers of the two marts (docs/validation/onoff_checks.md). Numbers only."""
    rows = con.execute("""
        WITH p AS (SELECT season_end_year, season_type, count(*) AS players, count(DISTINCT team_id) AS teams,
                          sum(on_o_poss) / 5 AS poss, sum(on_o_pts) / 5 AS pts FROM marts.player_onoff_season GROUP BY ALL),
             l AS (SELECT season_end_year, season_type, count(*) AS lineups, sum(secs) / 3600 AS hours FROM marts.lineup_stats GROUP BY ALL)
        SELECT season_end_year, season_type, teams, players, lineups, poss, pts, 100.0 * pts / poss
        FROM p JOIN l USING (season_end_year, season_type) ORDER BY season_type DESC, season_end_year""").fetchall()
    ft = con.execute("""SELECT count(*) FROM core.events WHERE event_type = 'free_throw' AND points > 0 AND foul_event_seq IS NULL
                        AND NOT coalesce(is_technical_ft, FALSE) AND NOT coalesce(is_between_possessions_ft, FALSE)
                        AND possession_id IS NOT NULL""").fetchone()[0]
    meta = con.execute("SELECT any_value(credit_method), any_value(rules_version), any_value(rules_profile) FROM marts.player_onoff_season").fetchone()
    lines = ["# On/off and lineup marts: checks", "",
             f"Credit method `{meta[0]}`, rules version `{meta[1]}`, profile `{meta[2]}` (see `marts/onoff.py`). Numbers only.", "",
             "The build is rolled back unless all of these hold: every possession has an end stint; its offense team is the home or the away",
             "team; credited points = possession points; stint possessions = core.possessions; per team-season the players' possessions, points and",
             "seconds are exactly 5 times the lineups'. They held for every season below.", "",
             "| season | type | teams | player rows | lineups | possessions (all teams) | points | points per 100 possessions |",
             "|---|---|---|---|---|---|---|---|"]
    lines += [f"| {season_label(y)} | {t} | {n} | {pl:,} | {li:,} | {int(po):,} | {int(pt):,} | {r:.1f} |" for y, t, n, pl, li, po, pt, r in rows]
    lines += ["", f"Free throws that count but have no linked foul (credited to the stint of the free throw itself): **{ft}**.", ""]
    path.write_text(chr(10).join(lines), encoding="utf-8")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    con = db.connect()
    try:
        print(build(con))
        write_report(con, db.PROJECT_ROOT / "docs" / "validation" / "onoff_checks.md")
    finally:
        con.close()


if __name__ == "__main__":
    main()
