"""On/off, lineup and pair marts: team results with a player, a five-man lineup or two teammates on the floor.

Built from core.stints, core.possessions, core.possession_stint_segments and core.events; nothing
comes from the NBA.com box score. One row per (season, type, team, player) in
marts.player_onoff_season, per (season, type, team, lineup) in marts.lineup_stats and per
(season, type, team, two players) in marts.pair_stats and per (season, type, team, three or four players) in
marts.combo_stats. marts.possession_noise holds each season's standard deviation of points per possession, so pages can show approximate
confidence intervals on the ratings (1.96 x 100 x sd / sqrt(possessions); a statistical approximation, not a model).

Crediting (CLAUDE.md "Substitution during a possession", decided by the owner 2026-10-22): the
marts use the pbpstats hybrid, recorded in `credit_method` = 'pbpstats_hybrid':
- a possession (and its heave / garbage flags) is credited to the stint that is on the floor
  when it ends (the last of its stint segments), for the offense lineup and the defense lineup;
- the points of a field goal are credited with the possession; the points of a free throw go to the
  stint on the floor at the foul (`foul_event_seq`); a non-technical free throw without a linked foul
  (`ft_without_foul`, counted in the report) goes to the stint of the free throw itself;
- technical free throws and free throws between possessions belong to no possession and are not
  counted anywhere in these tables (CLAUDE.md "Lineup efficiency").
Four factors (lineup, pair and combo tables): shot counts (FGA, FGM, 3PM) go to the stint of the shot event; made free
throws to the stint at the foul (the hybrid); turnovers and defensive rebounds that end a possession to the stint on the
floor when it ends; offensive rebounds (a rebound followed by a higher chance id: 1,094,018 against 1,094,077 in
`num_chances - 1`) to the stint of the rebound. All possessions count, heaves and garbage time included. Rates: eFG%, TOV% (per
possession), ORB% (own offensive rebounds / (own + the possessions the opponent's defensive rebound ended)), FT rate (made free
throws per FGA); `d_` columns are the opponents' numbers while the lineup defends.
Option A ('end_lineup': every point of a possession, free throws included, goes to the stint on the
floor when it ends) is computed only for `compare_credit_methods`, which writes
docs/validation/onoff_credit_methods.md; option C (chance split) is not implemented.
Possessions flagged `is_end_of_period_heave` or `is_garbage_time` are all counted; their counts are
stored (`*_heave_poss`, `*_garbage_poss`) so a page can exclude them. Nothing is excluded here.

Names: `o` = the team on offense, `d` = on defense; `on` = player on the floor, `off` = not (the
team's total minus `on`, same team and season; a traded player has one row per team).

Hard fails (the build is rolled back): a possession without a stint segment, an offense team that is
neither home nor away, points not conserved, a team-season where the players' possessions, points or
seconds are not 5 times the lineups' (10 times for pairs), or more than one rules version / profile
in core.possessions.

Usage:
    python -m nba_platform.marts.onoff             # build the marts and docs/validation/onoff_checks.md
    python -m nba_platform.marts.onoff --compare   # also docs/validation/onoff_credit_methods.md
"""

from __future__ import annotations

import argparse
import sys
from itertools import combinations
from pathlib import Path

from nba_platform import db
from nba_platform.seasons import season_label

CREDIT_METHOD = "pbpstats_hybrid"
CREDIT_METHODS = ("pbpstats_hybrid", "end_lineup")
TEMP_TABLES = ("poss_end", "orb_events", "credit_points", "credits", "stint_team")


class OnOffMartError(RuntimeError):
    """The on/off marts cannot be built as is. The build is rolled back."""


STAT_COLS = ["o_poss", "o_pts", "o_heave_poss", "o_garbage_poss", "d_poss", "d_pts", "d_heave_poss", "d_garbage_poss"]
FACTOR_COLS = ["fga", "fgm", "fg3m", "ftm", "tov", "orb", "drb_end"]       # four-factor counts of one offense
FACTOR_STAT_COLS = [f"{side}_{c}" for side in ("o", "d") for c in FACTOR_COLS]
ALL_COLS = STAT_COLS + FACTOR_STAT_COLS
FACTOR_RATE_COLS = [f"{side}_{r}" for side in ("o", "d") for r in ("efg", "tov_pct", "orb_pct", "ft_rate")]
TAIL = "credit_method TEXT NOT NULL, rules_version TEXT NOT NULL, rules_profile TEXT NOT NULL"
RATE_DDL = ", ".join(f"{c} DOUBLE" for c in FACTOR_RATE_COLS)

DDL_PLAYER = f"""(
    season_end_year INTEGER NOT NULL, season_type TEXT NOT NULL, team_id INTEGER NOT NULL, player_id INTEGER NOT NULL,
    games INTEGER NOT NULL, on_secs DOUBLE NOT NULL, off_secs DOUBLE NOT NULL,
    {", ".join(f"on_{c} BIGINT NOT NULL" for c in STAT_COLS)},
    {", ".join(f"off_{c} BIGINT NOT NULL" for c in STAT_COLS)},
    on_ortg DOUBLE, on_drtg DOUBLE, on_net DOUBLE, off_ortg DOUBLE, off_drtg DOUBLE, off_net DOUBLE, net_on_minus_off DOUBLE,
    {TAIL},
    PRIMARY KEY (season_end_year, season_type, team_id, player_id))"""

DDL_LINEUP = f"""(
    season_end_year INTEGER NOT NULL, season_type TEXT NOT NULL, team_id INTEGER NOT NULL, lineup_key TEXT NOT NULL,
    p1 INTEGER NOT NULL, p2 INTEGER NOT NULL, p3 INTEGER NOT NULL, p4 INTEGER NOT NULL, p5 INTEGER NOT NULL,
    games INTEGER NOT NULL, stints INTEGER NOT NULL, secs DOUBLE NOT NULL,
    {", ".join(f"{c} BIGINT NOT NULL" for c in ALL_COLS)},
    ortg DOUBLE, drtg DOUBLE, net DOUBLE, {RATE_DDL},
    {TAIL},
    PRIMARY KEY (season_end_year, season_type, team_id, lineup_key))"""

DDL_PAIR = f"""(
    season_end_year INTEGER NOT NULL, season_type TEXT NOT NULL, team_id INTEGER NOT NULL,
    player_a INTEGER NOT NULL, player_b INTEGER NOT NULL,
    games INTEGER NOT NULL, stints INTEGER NOT NULL, secs DOUBLE NOT NULL,
    {", ".join(f"{c} BIGINT NOT NULL" for c in ALL_COLS)},
    ortg DOUBLE, drtg DOUBLE, net DOUBLE, {RATE_DDL},
    {TAIL},
    PRIMARY KEY (season_end_year, season_type, team_id, player_a, player_b))"""

DDL_COMBO = f"""(
    season_end_year INTEGER NOT NULL, season_type TEXT NOT NULL, team_id INTEGER NOT NULL, size INTEGER NOT NULL, combo_key TEXT NOT NULL,
    p1 INTEGER NOT NULL, p2 INTEGER NOT NULL, p3 INTEGER NOT NULL, p4 INTEGER,
    games INTEGER NOT NULL, stints INTEGER NOT NULL, secs DOUBLE NOT NULL,
    {", ".join(f"{c} BIGINT NOT NULL" for c in ALL_COLS)},
    ortg DOUBLE, drtg DOUBLE, net DOUBLE, {RATE_DDL},
    {TAIL},
    PRIMARY KEY (season_end_year, season_type, team_id, size, combo_key))"""

DDL_NOISE = """(
    season_end_year INTEGER NOT NULL, season_type TEXT NOT NULL, possessions BIGINT NOT NULL, mean_pts DOUBLE NOT NULL, sd_pts DOUBLE NOT NULL,
    rules_version TEXT NOT NULL, rules_profile TEXT NOT NULL,
    PRIMARY KEY (season_end_year, season_type))"""

# possession -> the stint on the floor when it ends
POSS_END = """
    CREATE TEMP TABLE poss_end AS
    SELECT p.game_id, p.possession_id, p.offense_team_id, p.is_end_of_period_heave AS heave, p.is_garbage_time AS garbage,
           p.end_type, s.end_stint_id
    FROM core.possessions p
    LEFT JOIN (SELECT game_id, possession_id, arg_max(stint_id, segment_seq) AS end_stint_id
               FROM core.possession_stint_segments GROUP BY ALL) s USING (game_id, possession_id)"""

# scoring events inside possessions -> the stint that is credited with the points
FT_STINT = {"pbpstats_hybrid": "coalesce(f.stint_id, e.stint_id)", "end_lineup": "pe.end_stint_id"}
CREDIT_POINTS = """
    CREATE TEMP TABLE credit_points AS
    SELECT e.game_id, e.team_id AS scoring_team_id, e.points,
           CASE WHEN e.event_type = 'free_throw' THEN {ft_stint} ELSE pe.end_stint_id END AS stint_id,
           e.event_type = 'free_throw' AND f.stint_id IS NULL AS ft_without_foul, e.event_type = 'free_throw' AS is_ft
    FROM core.events e
    JOIN poss_end pe ON pe.game_id = e.game_id AND pe.possession_id = e.possession_id
    LEFT JOIN core.events f ON f.game_id = e.game_id AND f.event_seq = e.foul_event_seq
    WHERE e.points > 0 AND NOT coalesce(e.is_technical_ft, FALSE) AND NOT coalesce(e.is_between_possessions_ft, FALSE)"""

# offensive rebounds: a rebound inside a possession that is followed by a higher chance id (the possession goes on)
ORB_EVENTS = """
    CREATE TEMP TABLE orb_events AS
    SELECT r.game_id, r.stint_id, r.team_id, pe.offense_team_id
    FROM (SELECT e.game_id, e.possession_id, e.stint_id, e.team_id, e.event_type, e.chance_id,
                 lead(e.chance_id) OVER (PARTITION BY e.game_id, e.possession_id ORDER BY e.event_seq) AS next_chance
          FROM core.events e WHERE e.possession_id IS NOT NULL) r
    JOIN poss_end pe ON pe.game_id = r.game_id AND pe.possession_id = r.possession_id
    WHERE r.event_type = 'rebound' AND r.next_chance > r.chance_id"""

def _zeros(**kw):
    vals = {c: "0" for c in FACTOR_COLS}
    vals.update(kw)
    return ", ".join(f"{vals[c]} AS {c}" for c in FACTOR_COLS)


# what each team's offense got in each stint (long format: possessions, points and each factor event are separate rows)
CREDITS = f"""
    CREATE TEMP TABLE credits AS
    SELECT game_id, stint_id, off_team_id, sum(poss) AS poss, sum(pts) AS pts, sum(heave) AS heave, sum(garbage) AS garbage,
           {", ".join(f"sum({c}) AS {c}" for c in FACTOR_COLS)}
    FROM (SELECT game_id, end_stint_id AS stint_id, offense_team_id AS off_team_id, 1 AS poss, 0 AS pts,
                 CAST(heave AS INTEGER) AS heave, CAST(garbage AS INTEGER) AS garbage,
                 {_zeros(tov="CAST(end_type = 'turnover' AS INTEGER)", drb_end="CAST(end_type = 'defensive_rebound' AS INTEGER)")}
          FROM poss_end
          UNION ALL
          SELECT game_id, stint_id, scoring_team_id, 0, points, 0, 0, {_zeros(ftm="CAST(is_ft AS INTEGER)")} FROM credit_points
          UNION ALL
          SELECT game_id, stint_id, team_id, 0, 0, 0, 0,
                 {_zeros(fga="1", fgm="CAST(event_type = 'shot_made' AS INTEGER)", fg3m="CAST(event_type = 'shot_made' AND points = 3 AS INTEGER)")}
          FROM core.events WHERE event_type IN ('shot_made', 'shot_missed') AND team_id IS NOT NULL
          UNION ALL
          SELECT game_id, stint_id, offense_team_id, 0, 0, 0, 0, {_zeros(orb="1")} FROM orb_events)
    GROUP BY ALL"""

# one row per (stint, team on the floor): seconds, the five players (sorted), and the team's offense / defense credit
STINT_TEAM = """
    CREATE TEMP TABLE stint_team AS
    WITH sides AS (
        SELECT s.game_id, s.stint_id, g.season_end_year, g.season_type, g.home_team_id AS team_id, g.away_team_id AS opp_team_id,
               s.end_secs - s.start_secs AS secs, list_sort([s.home_p1, s.home_p2, s.home_p3, s.home_p4, s.home_p5]) AS players
        FROM core.stints s JOIN core.games g USING (game_id)
        UNION ALL
        SELECT s.game_id, s.stint_id, g.season_end_year, g.season_type, g.away_team_id, g.home_team_id,
               s.end_secs - s.start_secs, list_sort([s.away_p1, s.away_p2, s.away_p3, s.away_p4, s.away_p5])
        FROM core.stints s JOIN core.games g USING (game_id))
    SELECT x.game_id, x.stint_id, x.season_end_year, x.season_type, x.team_id, x.secs, x.players,
           coalesce(o.poss, 0) AS o_poss, coalesce(o.pts, 0) AS o_pts, coalesce(o.heave, 0) AS o_heave_poss, coalesce(o.garbage, 0) AS o_garbage_poss,
           coalesce(d.poss, 0) AS d_poss, coalesce(d.pts, 0) AS d_pts, coalesce(d.heave, 0) AS d_heave_poss, coalesce(d.garbage, 0) AS d_garbage_poss,
           {factors}
    FROM sides x
    LEFT JOIN credits o ON o.game_id = x.game_id AND o.stint_id = x.stint_id AND o.off_team_id = x.team_id
    LEFT JOIN credits d ON d.game_id = x.game_id AND d.stint_id = x.stint_id AND d.off_team_id = x.opp_team_id"""

STINT_TEAM = STINT_TEAM.replace("{factors}", ", ".join(f"coalesce(o.{c}, 0) AS o_{c}" for c in FACTOR_COLS) + ", "
                                + ", ".join(f"coalesce(d.{c}, 0) AS d_{c}" for c in FACTOR_COLS))

SUMS = ", ".join(f"CAST(sum({c}) AS BIGINT) AS {c}" for c in STAT_COLS)
SUMS_ALL = ", ".join(f"CAST(sum({c}) AS BIGINT) AS {c}" for c in ALL_COLS)


def _tuples(k: int) -> str:
    return "[" + ", ".join("[" + ", ".join(f"players[{i}]" for i in idx) + "]" for idx in combinations(range(1, 6), k)) + "]"


PAIRS, TRIOS, QUARTETS = _tuples(2), _tuples(3), _tuples(4)


def _rate(pts: str, poss: str) -> str:
    return f"CASE WHEN {poss} > 0 THEN 100.0 * {pts} / {poss} END"


def _ratings(prefix: str = "") -> str:
    o = _rate(f"{prefix}o_pts", f"{prefix}o_poss")
    d = _rate(f"{prefix}d_pts", f"{prefix}d_poss")
    return f"{o} AS {prefix}ortg, {d} AS {prefix}drtg, {o} - {d} AS {prefix}net"


def _rates_all() -> str:
    """Ratings and the four factors of one offense and of its opponents, from the summed count columns."""
    out = [_ratings()]
    for s in ("o", "d"):
        out += [f"CASE WHEN {s}_fga > 0 THEN ({s}_fgm + 0.5 * {s}_fg3m) / {s}_fga END AS {s}_efg",
                f"CASE WHEN {s}_poss > 0 THEN CAST({s}_tov AS DOUBLE) / {s}_poss END AS {s}_tov_pct",
                f"CASE WHEN {s}_orb + {s}_drb_end > 0 THEN CAST({s}_orb AS DOUBLE) / ({s}_orb + {s}_drb_end) END AS {s}_orb_pct",
                f"CASE WHEN {s}_fga > 0 THEN CAST({s}_ftm AS DOUBLE) / {s}_fga END AS {s}_ft_rate"]
    return ", ".join(out)


def _tail(method: str, version: tuple[str, str]) -> str:
    return f"'{method}' AS credit_method, '{version[0]}' AS rules_version, '{version[1]}' AS rules_profile"


def _player_select(method: str, version: tuple[str, str]) -> str:
    on_net = f"{_rate('on_o_pts', 'on_o_poss')} - {_rate('on_d_pts', 'on_d_poss')}"
    off_net = f"{_rate('off_o_pts', 'off_o_poss')} - {_rate('off_d_pts', 'off_d_poss')}"
    return f"""
        WITH p AS (
            SELECT season_end_year, season_type, team_id, player_id, count(DISTINCT game_id) AS games, sum(secs) AS on_secs,
                   {", ".join(f"CAST(sum({c}) AS BIGINT) AS on_{c}" for c in STAT_COLS)}
            FROM (SELECT season_end_year, season_type, team_id, game_id, secs, {", ".join(STAT_COLS)}, unnest(players) AS player_id
                  FROM stint_team)
            GROUP BY season_end_year, season_type, team_id, player_id),
        t AS (SELECT season_end_year, season_type, team_id, sum(secs) AS secs, {SUMS} FROM stint_team GROUP BY ALL),
        r AS (SELECT p.season_end_year, p.season_type, p.team_id, p.player_id, p.games, p.on_secs, t.secs - p.on_secs AS off_secs,
                     {", ".join(f"p.on_{c}" for c in STAT_COLS)}, {", ".join(f"t.{c} - p.on_{c} AS off_{c}" for c in STAT_COLS)}
              FROM p JOIN t USING (season_end_year, season_type, team_id))
        SELECT season_end_year, season_type, team_id, player_id, games, on_secs, off_secs,
               {", ".join(f"on_{c}" for c in STAT_COLS)}, {", ".join(f"off_{c}" for c in STAT_COLS)},
               {_ratings("on_")}, {_ratings("off_")}, ({on_net}) - ({off_net}) AS net_on_minus_off, {_tail(method, version)}
        FROM r"""


def _lineup_select(method: str, version: tuple[str, str]) -> str:
    return f"""
        WITH l AS (SELECT season_end_year, season_type, team_id, players, count(DISTINCT game_id) AS games, count(*) AS stints,
                          sum(secs) AS secs, {SUMS_ALL}
                   FROM stint_team GROUP BY season_end_year, season_type, team_id, players)
        SELECT season_end_year, season_type, team_id, array_to_string(players, '-'),
               players[1], players[2], players[3], players[4], players[5], games, stints, secs, {", ".join(ALL_COLS)},
               {_rates_all()}, {_tail(method, version)}
        FROM l"""


def _only(season: tuple[int, str] | None) -> str:
    """Optional filter on one season: the pair and combo tables are written season by season (a single statement over all
    stints expands 23 million rows of 22 columns and ran out of memory)."""
    return "" if season is None else f"WHERE season_end_year = {int(season[0])} AND season_type = '{season[1]}'"


def _pair_select(method: str, version: tuple[str, str], season: tuple[int, str] | None = None) -> str:
    return f"""
        WITH x AS (SELECT season_end_year, season_type, team_id, game_id, secs, {", ".join(ALL_COLS)}, unnest({PAIRS}) AS pr
                   FROM stint_team {_only(season)}),
        a AS (SELECT season_end_year, season_type, team_id, pr[1] AS player_a, pr[2] AS player_b, count(DISTINCT game_id) AS games,
                     count(*) AS stints, sum(secs) AS secs, {SUMS_ALL}
              FROM x GROUP BY season_end_year, season_type, team_id, pr[1], pr[2])
        SELECT season_end_year, season_type, team_id, player_a, player_b, games, stints, secs, {", ".join(ALL_COLS)},
               {_rates_all()}, {_tail(method, version)}
        FROM a"""


def _combo_select(method: str, version: tuple[str, str], season: tuple[int, str] | None = None) -> str:
    """Three- and four-man combinations of every stint-team row (10 and 5 per row)."""
    def part(size: int, expr: str) -> str:
        p4 = "cb[4]" if size == 4 else "CAST(NULL AS INTEGER)"
        return f"""
        SELECT season_end_year, season_type, team_id, {size} AS size, array_to_string(cb, '-') AS combo_key, cb[1] AS p1, cb[2] AS p2,
               cb[3] AS p3, {p4} AS p4, games, stints, secs, {", ".join(ALL_COLS)}, {_rates_all()}, {_tail(method, version)}
        FROM (SELECT season_end_year, season_type, team_id, cb, count(DISTINCT game_id) AS games, count(*) AS stints, sum(secs) AS secs, {SUMS_ALL}
              FROM (SELECT season_end_year, season_type, team_id, game_id, secs, {", ".join(ALL_COLS)}, unnest({expr}) AS cb FROM stint_team {_only(season)})
              GROUP BY season_end_year, season_type, team_id, cb)"""
    return part(3, TRIOS) + " UNION ALL " + part(4, QUARTETS)


def _noise_select(version: tuple[str, str]) -> str:
    return f"""
        SELECT g.season_end_year, g.season_type, count(*), avg(p.points), stddev_samp(p.points), '{version[0]}', '{version[1]}'
        FROM core.possessions p JOIN core.games g USING (game_id) GROUP BY g.season_end_year, g.season_type"""


def _one(con, sql: str):
    return con.execute(sql).fetchone()[0]


def _version(con) -> tuple[str, str]:
    versions = con.execute("SELECT DISTINCT rules_version, rules_profile FROM core.possessions").fetchall()
    if len(versions) != 1:
        raise OnOffMartError(f"core.possessions holds {len(versions)} rules versions / profiles; expected exactly one: {versions}")
    return versions[0]


def _prepare(con, method: str) -> None:
    """(Re)create the temp tables for one credit method."""
    if method not in CREDIT_METHODS:
        raise ValueError(f"unknown credit method {method!r}; known: {CREDIT_METHODS}")
    for t in TEMP_TABLES:
        con.execute(f"DROP TABLE IF EXISTS {t}")
    con.execute(POSS_END)
    con.execute(ORB_EVENTS)
    con.execute(CREDIT_POINTS.format(ft_stint=FT_STINT[method]))
    con.execute(CREDITS)
    con.execute(STINT_TEAM)


def _drop_temp(con) -> None:
    for t in TEMP_TABLES:
        con.execute(f"DROP TABLE IF EXISTS {t}")


def _hard_checks(con, suffix: str = "") -> None:
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
    plain = ("o_poss", "d_poss", "o_pts", "secs")
    for table, where, factor, cols in ((f"marts.player_onoff_season{suffix}", "TRUE", 5, ("on_o_poss", "on_d_poss", "on_o_pts", "on_secs")),
                                       (f"marts.pair_stats{suffix}", "TRUE", 10, plain), (f"marts.combo_stats{suffix}", "size = 3", 10, plain),
                                       (f"marts.combo_stats{suffix}", "size = 4", 5, plain)):
        off = con.execute(f"""
            WITH p AS (SELECT season_end_year, season_type, team_id, sum({cols[0]}) AS po, sum({cols[1]}) AS pd, sum({cols[2]}) AS pp,
                              sum({cols[3]}) AS ps FROM {table} WHERE {where} GROUP BY ALL),
                 l AS (SELECT season_end_year, season_type, team_id, sum(o_poss) AS lo, sum(d_poss) AS ld, sum(o_pts) AS lp, sum(secs) AS ls
                       FROM marts.lineup_stats{suffix} GROUP BY ALL)
            SELECT count(*) FROM l LEFT JOIN p USING (season_end_year, season_type, team_id)
            WHERE p.po IS DISTINCT FROM {factor} * l.lo OR p.pd IS DISTINCT FROM {factor} * l.ld
               OR p.pp IS DISTINCT FROM {factor} * l.lp OR abs(p.ps - {factor} * l.ls) > 1e-6 OR p.ps IS NULL""").fetchone()[0]
        if off:
            raise OnOffMartError(f"{off} team-seasons: {table} ({where}) possessions, points or seconds are not {factor} times the lineups'")
    bad = _one(con, "SELECT count(*) FROM orb_events WHERE team_id IS DISTINCT FROM offense_team_id")
    if bad:
        raise OnOffMartError(f"{bad} offensive rebounds are not by the possession's offense team")
    sums = ", ".join(f"coalesce(sum({s}_{c}), 0) AS {s}_{c}" for s in ("o", "d") for c in FACTOR_COLS)
    mismatch = con.execute(f"""
        WITH g AS (SELECT game_id, season_end_year AS y, season_type AS t FROM core.games),
             sh AS (SELECT g.y, g.t, count(*) AS fga, count(*) FILTER (event_type = 'shot_made') AS fgm,
                           count(*) FILTER (event_type = 'shot_made' AND points = 3) AS fg3m
                    FROM core.events e JOIN g USING (game_id) WHERE event_type IN ('shot_made', 'shot_missed') AND team_id IS NOT NULL GROUP BY 1, 2),
             ft AS (SELECT g.y, g.t, count(*) AS ftm FROM credit_points c JOIN g USING (game_id) WHERE c.is_ft GROUP BY 1, 2),
             po AS (SELECT g.y, g.t, count(*) FILTER (end_type = 'turnover') AS tov, count(*) FILTER (end_type = 'defensive_rebound') AS drb_end
                    FROM poss_end p JOIN g USING (game_id) GROUP BY 1, 2),
             ob AS (SELECT g.y, g.t, count(*) AS orb FROM orb_events o JOIN g USING (game_id) GROUP BY 1, 2),
             l AS (SELECT season_end_year AS y, season_type AS t, {sums} FROM marts.lineup_stats{suffix} GROUP BY 1, 2)
        SELECT count(*) FROM l LEFT JOIN sh USING (y, t) LEFT JOIN ft USING (y, t) LEFT JOIN po USING (y, t) LEFT JOIN ob USING (y, t)
        WHERE l.o_fga <> coalesce(sh.fga, 0) OR l.o_fgm <> coalesce(sh.fgm, 0) OR l.o_fg3m <> coalesce(sh.fg3m, 0) OR l.o_ftm <> coalesce(ft.ftm, 0)
           OR l.o_tov <> coalesce(po.tov, 0) OR l.o_drb_end <> coalesce(po.drb_end, 0) OR l.o_orb <> coalesce(ob.orb, 0)
           OR {" OR ".join(f"l.d_{c} <> l.o_{c}" for c in FACTOR_COLS)}""").fetchone()[0]
    if mismatch:
        raise OnOffMartError(f"{mismatch} seasons: the lineups' four-factor counts differ from the shot events / possessions / rebounds (or offense and defense totals differ)")


def build(con) -> dict:
    """Rebuild the on/off, lineup, pair, combo and noise marts.

    The new tables are written next to the old ones (`*_new`, season by season: one big transaction held every new row in memory
    and ran out of it), checked, and only then swapped in by one small transaction; if a check fails the new tables are dropped and
    the old marts stay as they were.
    """
    version = _version(con)
    con.execute("CREATE SCHEMA IF NOT EXISTS marts")
    names = ("player_onoff_season", "lineup_stats", "pair_stats", "combo_stats", "possession_noise")
    try:
        _prepare(con, CREDIT_METHOD)
        seasons = con.execute("SELECT DISTINCT season_end_year, season_type FROM stint_team ORDER BY 1, 2").fetchall()
        for name, ddl, select, by_season in (("player_onoff_season", DDL_PLAYER, _player_select, False),
                                             ("lineup_stats", DDL_LINEUP, _lineup_select, False),
                                             ("pair_stats", DDL_PAIR, _pair_select, True), ("combo_stats", DDL_COMBO, _combo_select, True)):
            con.execute(f"DROP TABLE IF EXISTS marts.{name}_new")
            con.execute(f"CREATE TABLE marts.{name}_new {ddl}")
            for season in (seasons if by_season else [None]):
                con.execute(f"INSERT INTO marts.{name}_new {select(CREDIT_METHOD, version, season) if by_season else select(CREDIT_METHOD, version)}")
        con.execute("DROP TABLE IF EXISTS marts.possession_noise_new")
        con.execute(f"CREATE TABLE marts.possession_noise_new {DDL_NOISE}")
        con.execute(f"INSERT INTO marts.possession_noise_new {_noise_select(version)}")
        _hard_checks(con, "_new")
        out = {"player_rows": _one(con, "SELECT count(*) FROM marts.player_onoff_season_new"),
               "lineup_rows": _one(con, "SELECT count(*) FROM marts.lineup_stats_new"),
               "pair_rows": _one(con, "SELECT count(*) FROM marts.pair_stats_new"),
               "combo_rows": _one(con, "SELECT count(*) FROM marts.combo_stats_new"),
               "ft_without_foul": _one(con, "SELECT count(*) FROM credit_points WHERE ft_without_foul"),
               "rules_version": version[0], "rules_profile": version[1]}
        con.execute("BEGIN")
        for name in names:
            con.execute(f"DROP TABLE IF EXISTS marts.{name}")
            con.execute(f"ALTER TABLE marts.{name}_new RENAME TO {name}")
        con.execute("COMMIT")
        _drop_temp(con)
    except Exception:
        try:
            con.execute("ROLLBACK")
        except Exception:
            pass
        for name in names:
            con.execute(f"DROP TABLE IF EXISTS marts.{name}_new")
        raise
    return out


def player_rows(con, method: str):
    """Player on/off rows for one credit method, as a DataFrame (nothing is written)."""
    version = _version(con)
    _prepare(con, method)
    try:
        return con.execute(_player_select(method, version)).df()
    finally:
        _drop_temp(con)


def write_report(con, path: Path) -> None:
    """Per-season numbers of the marts (docs/validation/onoff_checks.md). Numbers only."""
    rows = con.execute("""
        WITH p AS (SELECT season_end_year, season_type, count(*) AS players, count(DISTINCT team_id) AS teams,
                          sum(on_o_poss) / 5 AS poss, sum(on_o_pts) / 5 AS pts FROM marts.player_onoff_season GROUP BY ALL),
             l AS (SELECT season_end_year, season_type, count(*) AS lineups FROM marts.lineup_stats GROUP BY ALL),
             q AS (SELECT season_end_year, season_type, count(*) AS pairs FROM marts.pair_stats GROUP BY ALL),
             c AS (SELECT season_end_year, season_type, count(*) AS combos FROM marts.combo_stats GROUP BY ALL)
        SELECT season_end_year, season_type, teams, players, lineups, pairs, combos, poss, pts, 100.0 * pts / poss
        FROM p JOIN l USING (season_end_year, season_type) JOIN q USING (season_end_year, season_type) JOIN c USING (season_end_year, season_type)
        ORDER BY season_type DESC, season_end_year""").fetchall()
    ft = con.execute("""SELECT count(*) FROM core.events WHERE event_type = 'free_throw' AND points > 0 AND foul_event_seq IS NULL
                        AND NOT coalesce(is_technical_ft, FALSE) AND NOT coalesce(is_between_possessions_ft, FALSE)
                        AND possession_id IS NOT NULL""").fetchone()[0]
    meta = con.execute("SELECT any_value(credit_method), any_value(rules_version), any_value(rules_profile) FROM marts.player_onoff_season").fetchone()
    lines = ["# On/off, lineup and pair marts: checks", "",
             f"Credit method `{meta[0]}`, rules version `{meta[1]}`, profile `{meta[2]}` (see `marts/onoff.py`). Numbers only.", "",
             "The build is rolled back unless all of these hold: every possession has an end stint; its offense team is the home or the away",
             "team; credited points = possession points; stint possessions = core.possessions; per team-season the players' possessions, points and",
             "seconds are exactly 5 times the lineups', the pairs' and three-man combinations' exactly 10 times, the four-man combinations' 5 times; "
             "and per season the lineups' shots, made free throws, turnovers, offensive and defensive rebounds equal the counts from the events and "
             "possessions (offense totals = defense totals). They held for every season below.", "",
             "| season | type | teams | player rows | lineups | pairs | 3-4 man combos | possessions (all teams) | points | points per 100 possessions |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    lines += [f"| {season_label(y)} | {t} | {n} | {pl:,} | {li:,} | {pa:,} | {cb:,} | {int(po):,} | {int(pt):,} | {r:.1f} |"
              for y, t, n, pl, li, pa, cb, po, pt, r in rows]
    lines += ["", f"Free throws that count but have no linked foul (credited to the stint of the free throw itself): **{ft}**.", ""]
    path.write_text(chr(10).join(lines), encoding="utf-8")


def compare_credit_methods(con, path: Path, min_poss: int = 1000) -> dict:
    """Option A ('end_lineup') against the hybrid, per player (docs/validation/onoff_credit_methods.md).

    Only free-throw points can move between the two methods, so the report shows how many points move,
    and how much on/off changes for players with at least `min_poss` offensive possessions on the floor.
    """
    import pandas as pd

    keys = ["season_end_year", "season_type", "team_id", "player_id"]
    h, a = player_rows(con, "pbpstats_hybrid"), player_rows(con, "end_lineup")
    m = h.merge(a, on=keys, suffixes=("_h", "_a"))
    if len(m) != len(h) or len(m) != len(a):
        raise OnOffMartError("the two credit methods produced different player rows")
    m = m[m["on_o_poss_h"] >= min_poss].copy()
    m["moved_pts"] = (m["on_o_pts_a"] - m["on_o_pts_h"]).abs() + (m["on_d_pts_a"] - m["on_d_pts_h"]).abs()
    m["d_diff"] = m["net_on_minus_off_a"] - m["net_on_minus_off_h"]
    m["abs_d"] = m["d_diff"].abs()
    moved = con.execute("""
        WITH pe AS (SELECT game_id, possession_id, arg_max(stint_id, segment_seq) AS end_stint FROM core.possession_stint_segments GROUP BY ALL)
        SELECT g.season_end_year, g.season_type, count(*) AS fts, sum(e.points) FILTER (f.stint_id <> pe.end_stint) AS moved
        FROM core.events e JOIN core.games g USING (game_id)
        JOIN pe ON pe.game_id = e.game_id AND pe.possession_id = e.possession_id
        JOIN core.events f ON f.game_id = e.game_id AND f.event_seq = e.foul_event_seq
        WHERE e.event_type = 'free_throw' AND e.points > 0 AND NOT coalesce(e.is_technical_ft, FALSE)
          AND NOT coalesce(e.is_between_possessions_ft, FALSE)
        GROUP BY ALL ORDER BY 2 DESC, 1""").df()
    total = con.execute("SELECT sum(points) FROM core.possessions").fetchone()[0]
    per = (m.groupby(["season_end_year", "season_type"])
             .agg(players=("player_id", "size"), mean_abs=("abs_d", "mean"), p95=("abs_d", lambda s: s.quantile(0.95)),
                  max_abs=("abs_d", "max"), over_1=("abs_d", lambda s: int((s > 1).sum())))
             .reset_index().sort_values(["season_type", "season_end_year"], ascending=[False, True]))
    names = dict(con.execute("SELECT player_id, name FROM core.players").fetchall())
    teams = dict(con.execute("SELECT team_id, abbreviation FROM core.teams").fetchall())
    top = m.sort_values("abs_d", ascending=False).head(15)
    lines = ["# On/off under two ways to credit a substitution during a possession", "",
             "**B = `pbpstats_hybrid`** (what the marts use): free-throw points go to the lineup on the floor at the foul.",
             "**A = `end_lineup`**: every point of a possession goes to the lineup on the floor when it ends.",
             "Possession counts are the same under both (a possession always goes to the lineup at its end); only free-throw points",
             "whose foul and possession end fall in different stints move. Option C (chance split) is not computed. Numbers only.", "",
             f"Free-throw points that move between lineups: **{int(moved['moved'].fillna(0).sum()):,}** of {int(total):,} possession points "
             f"({100 * moved['moved'].fillna(0).sum() / total:.2f} %).", "",
             "Reading: substitutions are usually made in the dead ball after a foul, before the free throws, so under A the players who",
             "enter are credited with free throws earned while the players they replaced were on the floor; under B they are not.", "",
             f"## Change in a player's net on-off (A minus B), players with at least {min_poss:,} offensive possessions on the floor", "",
             "| season | type | players | mean abs change | 95th percentile | max | players changing by more than 1 point |",
             "|---|---|---|---|---|---|---|"]
    for r in per.itertuples():
        lines.append(f"| {season_label(r.season_end_year)} | {r.season_type} | {r.players} | {r.mean_abs:.3f} | {r.p95:.3f} | {r.max_abs:.2f} | {r.over_1} |")
    lines += ["", "## Largest changes", "", "Playoff rows have small off-the-floor samples, which magnifies any change.", "",
              "| season | type | team | player | on-off under B | under A | change | free-throw points moved (on floor) |",
              "|---|---|---|---|---|---|---|---|"]
    for r in top.itertuples():
        lines.append(f"| {season_label(r.season_end_year)} | {r.season_type} | {teams.get(r.team_id, r.team_id)} | {names.get(r.player_id, r.player_id)} | "
                     f"{r.net_on_minus_off_h:+.2f} | {r.net_on_minus_off_a:+.2f} | {r.d_diff:+.2f} | {int(r.moved_pts)} |")
    lines += ["", "## Free-throw points moved per season", "", "| season | type | free throws made in possessions | points moved |", "|---|---|---|---|"]
    lines += [f"| {season_label(y)} | {t} | {int(n):,} | {int(0 if pd.isna(mvd) else mvd):,} |" for y, t, n, mvd in moved.itertuples(index=False)]
    path.write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
    return {"players_compared": len(m), "mean_abs_change": round(float(m["abs_d"].mean()), 4), "max_abs_change": round(float(m["abs_d"].max()), 3),
            "moved_points": int(moved["moved"].fillna(0).sum())}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--compare", action="store_true", help="also write docs/validation/onoff_credit_methods.md")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    con = db.connect()
    try:
        print(build(con))
        write_report(con, db.PROJECT_ROOT / "docs" / "validation" / "onoff_checks.md")
        if args.compare:
            print(compare_credit_methods(con, db.PROJECT_ROOT / "docs" / "validation" / "onoff_credit_methods.md"))
    finally:
        con.close()


if __name__ == "__main__":
    main()
