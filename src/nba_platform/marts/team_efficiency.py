"""Team efficiency mart: points per 100 possessions, one row per team and season (our possessions).

Built from core.possessions and core.events; nothing comes from the NBA.com box score.
marts.team_efficiency_season, PRIMARY KEY (season_end_year, season_type, team_id).

Three versions of each rating, so a page can switch without recomputing:
- all possessions (`ortg`, `drtg`, `net`);
- `_ex_heave`: without possessions flagged `is_end_of_period_heave` (they score 0 by definition);
- `_ex_heave_garbage`: also without possessions flagged `is_garbage_time` (Cleaning the Glass definition).
Possession points exclude technical free throws and free throws between possessions (CLAUDE.md); the
team's points from those are stored separately (`pts_outside_possessions`), so
`o_pts + pts_outside_possessions` is the team's total.

Hard fails (rolled back): more than one rules version / profile, a possession whose offense or
defense team is not one of its game's teams, or totals that do not match core.possessions.

Usage:
    python -m nba_platform.marts.team_efficiency
"""

from __future__ import annotations

import sys
from pathlib import Path

from nba_platform import db
from nba_platform.seasons import season_label


class TeamEfficiencyError(RuntimeError):
    """The team efficiency mart cannot be built as is. The build is rolled back."""


VERSIONS = {"": "TRUE", "_ex_heave": "NOT p.is_end_of_period_heave",
            "_ex_heave_garbage": "NOT p.is_end_of_period_heave AND NOT p.is_garbage_time"}

DDL = """(
    season_end_year INTEGER NOT NULL, season_type TEXT NOT NULL, team_id INTEGER NOT NULL, games INTEGER NOT NULL,
    {cols},
    poss_per_game DOUBLE, pts_outside_possessions BIGINT NOT NULL,
    rules_version TEXT NOT NULL, rules_profile TEXT NOT NULL,
    PRIMARY KEY (season_end_year, season_type, team_id))"""


def _cols() -> list[str]:
    out = []
    for v in VERSIONS:
        out += [f"o_poss{v} BIGINT NOT NULL", f"o_pts{v} BIGINT NOT NULL", f"d_poss{v} BIGINT NOT NULL", f"d_pts{v} BIGINT NOT NULL",
                f"ortg{v} DOUBLE", f"drtg{v} DOUBLE", f"net{v} DOUBLE"]
    return out


def _rate(pts: str, poss: str) -> str:
    return f"CASE WHEN {poss} > 0 THEN 100.0 * {pts} / {poss} END"


def insert_sql(version: tuple[str, str]) -> str:
    sums = []
    for v, cond in VERSIONS.items():
        sums += [f"count(*) FILTER (side = 'o' AND {cond}) AS o_poss{v}", f"coalesce(sum(points) FILTER (side = 'o' AND {cond}), 0) AS o_pts{v}",
                 f"count(*) FILTER (side = 'd' AND {cond}) AS d_poss{v}", f"coalesce(sum(points) FILTER (side = 'd' AND {cond}), 0) AS d_pts{v}"]
    rates = []
    for v in VERSIONS:
        o, d = _rate(f"o_pts{v}", f"o_poss{v}"), _rate(f"d_pts{v}", f"d_poss{v}")
        rates += [f"o_poss{v}", f"o_pts{v}", f"d_poss{v}", f"d_pts{v}", o, d, f"{o} - {d}"]
    return f"""
        WITH p AS (
            SELECT g.season_end_year, g.season_type, p.game_id, p.offense_team_id AS team_id, 'o' AS side, p.points,
                   p.is_end_of_period_heave, p.is_garbage_time
            FROM core.possessions p JOIN core.games g USING (game_id)
            UNION ALL
            SELECT g.season_end_year, g.season_type, p.game_id, p.defense_team_id, 'd', p.points, p.is_end_of_period_heave, p.is_garbage_time
            FROM core.possessions p JOIN core.games g USING (game_id)),
        a AS (SELECT season_end_year, season_type, team_id, count(DISTINCT game_id) AS games, {", ".join(sums)}
              FROM p GROUP BY ALL),
        x AS (SELECT g.season_end_year, g.season_type, e.team_id, sum(e.points) AS pts
              FROM core.events e JOIN core.games g USING (game_id)
              WHERE e.points > 0 AND (coalesce(e.is_technical_ft, FALSE) OR coalesce(e.is_between_possessions_ft, FALSE))
              GROUP BY ALL)
        SELECT a.season_end_year, a.season_type, a.team_id, a.games, {", ".join(rates)},
               (a.o_poss + a.d_poss) / 2.0 / a.games, coalesce(x.pts, 0), '{version[0]}', '{version[1]}'
        FROM a LEFT JOIN x USING (season_end_year, season_type, team_id)"""


def build(con) -> dict:
    """Rebuild marts.team_efficiency_season in one transaction. Returns row counts."""
    versions = con.execute("SELECT DISTINCT rules_version, rules_profile FROM core.possessions").fetchall()
    if len(versions) != 1:
        raise TeamEfficiencyError(f"core.possessions holds {len(versions)} rules versions / profiles; expected exactly one: {versions}")
    bad = con.execute("""SELECT count(*) FROM core.possessions p JOIN core.games g USING (game_id)
                         WHERE p.offense_team_id NOT IN (g.home_team_id, g.away_team_id)
                            OR p.defense_team_id NOT IN (g.home_team_id, g.away_team_id)
                            OR p.offense_team_id = p.defense_team_id OR p.defense_team_id IS NULL""").fetchone()[0]
    if bad:
        raise TeamEfficiencyError(f"{bad} possessions have an offense or defense team that is not one of the game's two teams")
    con.execute("CREATE SCHEMA IF NOT EXISTS marts")
    con.execute("BEGIN")
    try:
        con.execute("DROP TABLE IF EXISTS marts.team_efficiency_season")
        con.execute(f"CREATE TABLE marts.team_efficiency_season {DDL.format(cols=', '.join(_cols()))}")
        con.execute(f"INSERT INTO marts.team_efficiency_season {insert_sql(versions[0])}")
        n_poss, pts = con.execute("SELECT count(*), coalesce(sum(points), 0) FROM core.possessions").fetchone()
        got = con.execute("SELECT sum(o_poss), sum(d_poss), sum(o_pts), sum(d_pts) FROM marts.team_efficiency_season").fetchone()
        if tuple(int(x or 0) for x in got) != (n_poss, n_poss, int(pts), int(pts)):
            raise TeamEfficiencyError(f"totals {got} do not match core.possessions ({n_poss} possessions, {pts} points)")
        out = {"rows": con.execute("SELECT count(*) FROM marts.team_efficiency_season").fetchone()[0], "possessions": n_poss}
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return out


def write_report(con, path: Path) -> dict:
    """Our team points (possessions + outside) against the official box score (docs/validation/team_efficiency.md)."""
    rows = con.execute("""
        SELECT e.season_end_year, e.season_type, t.abbreviation, e.o_pts + e.pts_outside_possessions AS ours, ts.pts AS box,
               (SELECT count(*) FROM core.games g WHERE g.season_end_year = e.season_end_year AND g.season_type = e.season_type
                  AND e.team_id IN (g.home_team_id, g.away_team_id) AND coalesce(g.pbp_missing, FALSE)) AS no_pbp
        FROM marts.team_efficiency_season e JOIN core.teams t USING (team_id)
        LEFT JOIN marts.team_season ts USING (season_end_year, season_type, team_id)
        ORDER BY 1, 2, 3""").fetchall()
    compared = [r for r in rows if r[4] is not None]
    diff = [r for r in compared if int(r[3]) != int(r[4])]
    lines = ["# Team efficiency mart: check against the official box score", "",
             "Our team points (possession points + technical and between-possession free throws) against NBA.com's season box",
             "score (`marts.team_season`). Numbers only. Ratings: `marts.team_efficiency_season`.", "",
             f"Team-seasons compared: **{len(compared):,}**; equal: **{len(compared) - len(diff):,}**; different: **{len(diff)}**; "
             f"without a box score: {len(rows) - len(compared)}.", ""]
    if diff:
        lines += ["| season | type | team | ours | official | difference | games without play-by-play |", "|---|---|---|---|---|---|---|"]
        lines += [f"| {season_label(y)} | {t} | {ab} | {int(o):,} | {int(b):,} | {int(o) - int(b):+d} | {n} |" for y, t, ab, o, b, n in diff]
        lines += ["", "Differences come from games whose source score and official box disagree, or incomplete box scores "
                  "(see `docs/validation/box_vs_pbp.md` and check 111 in `docs/validation/possession_summary.md`), or from a game that "
                  "has a box score but no play-by-play (last column; it has no possessions)."]
    path.write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
    return {"compared": len(compared), "different": len(diff)}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    con = db.connect()
    try:
        print(build(con))
        print(write_report(con, db.PROJECT_ROOT / "docs" / "validation" / "team_efficiency.md"))
    finally:
        con.close()


if __name__ == "__main__":
    main()
