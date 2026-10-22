"""Checks on our own possessions (CLAUDE.md validation checklist 7 and 8, plus points conservation).

Run after `build_core --step possessions`. Check ids:
- 111 (hard): in every game, each team's possession points + technical FTs + between-possessions FTs
  = its final score (events are the single source of points), and every event outside a possession is
  one of those free throws.
- 7 (warning): the two teams' possession counts in a game differ by at most 2.
- 8 (warning): our per-team possession counts vs the pbpstats reference (reference.pbpstats_possessions),
  excluding possessions flagged `is_end_of_period_heave` (pbpstats' approach); differences are
  reported per game, never fixed (working agreement 11).

All numbers only; the per-game list is written to docs/validation/possession_check_{season}.md.
"""

from __future__ import annotations

from pathlib import Path

from nba_platform.seasons import season_label
from nba_platform.validate.checks import CheckResult, save_check_results


def _scalar(con, sql, params):
    return con.execute(sql, params).fetchone()[0]


def check_points_conserved(con, y: int, t: str) -> CheckResult:
    """Hard check. Games registered in core.known_gaps as source score conflicts are reported, not failed."""
    rows = con.execute("""
        WITH g AS (SELECT * FROM core.games WHERE season_end_year = ? AND season_type = ? AND NOT coalesce(pbp_missing, FALSE)),
        side AS (SELECT game_id, home_team_id AS team_id, home_score AS final FROM g
                 UNION ALL SELECT game_id, away_team_id, away_score FROM g),
        p AS (SELECT game_id, offense_team_id AS team_id, sum(points) AS pts FROM core.possessions GROUP BY ALL),
        o AS (SELECT e.game_id, e.team_id, sum(e.points) AS pts FROM core.events e
              WHERE e.game_id IN (SELECT game_id FROM g) AND e.possession_id IS NULL AND e.points > 0 GROUP BY ALL)
        SELECT side.game_id, side.team_id, side.final, coalesce(p.pts, 0) + coalesce(o.pts, 0) AS got,
               side.game_id IN (SELECT game_id FROM core.known_gaps WHERE issue = 'source_score_conflict') AS known
        FROM side LEFT JOIN p USING (game_id, team_id) LEFT JOIN o USING (game_id, team_id)
        WHERE side.final IS NOT NULL AND side.final <> coalesce(p.pts, 0) + coalesce(o.pts, 0)""", [y, t]).fetchall()
    bad = [r for r in rows if not r[4]]
    known = [r for r in rows if r[4]]
    n = _scalar(con, "SELECT 2 * count(*) FROM core.games WHERE season_end_year = ? AND season_type = ? AND NOT coalesce(pbp_missing, FALSE)", [y, t])
    return CheckResult(111, "possession points + FTs outside possessions = final score", "fail" if bad else "pass", n, len(bad),
                       {"examples": [list(b[:4]) for b in bad[:10]], "known_source_score_conflicts": [list(k[:4]) for k in known]},
                       level="hard")


def check_7(con, y: int, t: str) -> CheckResult:
    rows = con.execute("""
        WITH c AS (SELECT p.game_id, p.offense_team_id, count(*) AS n FROM core.possessions p
                   JOIN core.games g USING (game_id) WHERE g.season_end_year = ? AND g.season_type = ?
                     AND NOT p.is_end_of_period_heave AND p.offense_team_id IS NOT NULL GROUP BY ALL),
        d AS (SELECT game_id, max(n) - min(n) AS diff, count(*) AS teams FROM c GROUP BY game_id)
        SELECT game_id, diff FROM d WHERE diff > 2 OR teams < 2""", [y, t]).fetchall()
    n = _scalar(con, "SELECT count(DISTINCT game_id) FROM core.possessions p JOIN core.games g USING (game_id) WHERE g.season_end_year = ? AND g.season_type = ?", [y, t])
    return CheckResult(7, "team possession counts in a game differ by <= 2", "fail" if rows else "pass", n, len(rows),
                       {"examples": [list(r) for r in rows[:10]]})


def per_game_vs_pbpstats(con, y: int, t: str):
    """(game_id, team_abbr, ours, pbpstats, diff) rows for every game that has pbpstats data."""
    return con.execute("""
        WITH abbr AS (SELECT team_id, source_team_key AS abbr FROM core.team_xref WHERE source = 'ramirobentes' AND season_end_year = ?),
        o AS (SELECT p.game_id, a.abbr, count(*) AS ours FROM core.possessions p
              JOIN core.games g USING (game_id) JOIN abbr a ON a.team_id = p.defense_team_id
              WHERE g.season_end_year = ? AND g.season_type = ? AND NOT p.is_end_of_period_heave GROUP BY ALL),
        r AS (SELECT game_id, defense_team_abbr AS abbr, count(*) AS ref FROM reference.pbpstats_possessions
              WHERE season_end_year = ? AND season_type = ? GROUP BY ALL)
        SELECT coalesce(o.game_id, r.game_id), coalesce(o.abbr, r.abbr), coalesce(o.ours, 0), coalesce(r.ref, 0),
               coalesce(o.ours, 0) - coalesce(r.ref, 0)
        FROM o FULL JOIN r USING (game_id, abbr)
        -- only games that both sides have; games missing on one side are counted separately
        WHERE game_id IN (SELECT game_id FROM r) AND game_id IN (SELECT game_id FROM o)
        ORDER BY 1, 2""", [y, y, t, y, t]).fetchall()


def games_missing_in_pbpstats(con, y: int, t: str) -> list[str]:
    return [g for (g,) in con.execute("""
        SELECT DISTINCT p.game_id FROM core.possessions p JOIN core.games g USING (game_id)
        WHERE g.season_end_year = ? AND g.season_type = ?
          AND p.game_id NOT IN (SELECT game_id FROM reference.pbpstats_possessions WHERE season_end_year = ? AND season_type = ?)
        ORDER BY 1""", [y, t, y, t]).fetchall()]


def check_8(con, y: int, t: str) -> CheckResult:
    has_ref = _scalar(con, "SELECT count(*) FROM reference.pbpstats_possessions WHERE season_end_year = ? AND season_type = ?", [y, t])
    rows = per_game_vs_pbpstats(con, y, t) if has_ref else []
    if not rows:
        return CheckResult(8, "our possession counts vs pbpstats", "skip", detail={"reason": "no pbpstats reference for this season"})
    diffs = [r[4] for r in rows]
    n_diff = sum(1 for d in diffs if d != 0)
    dist = {str(k): diffs.count(k) for k in sorted(set(diffs))}
    return CheckResult(8, "our possession counts vs pbpstats (per team-game)", "pass" if n_diff == 0 else "fail", len(rows), n_diff,
                       {"share_identical": round(1 - n_diff / len(rows), 4), "within_1": round(sum(abs(d) <= 1 for d in diffs) / len(rows), 4),
                        "difference_distribution": dist, "games_missing_in_pbpstats": games_missing_in_pbpstats(con, y, t)})


def run(con, y: int, t: str) -> list[CheckResult]:
    results = [check_points_conserved(con, y, t), check_7(con, y, t), check_8(con, y, t)]
    save_check_results(con, y, t, results)
    return results


def write_report(con, y: int, t: str, results: list[CheckResult], path: Path) -> None:
    has_ref = _scalar(con, "SELECT count(*) FROM reference.pbpstats_possessions WHERE season_end_year = ? AND season_type = ?", [y, t])
    rows = [r for r in per_game_vs_pbpstats(con, y, t) if r[4] != 0] if has_ref else []
    lines = [f"# Possession checks: {season_label(y)} {t}", "",
             "Our possessions (`core.possessions`, profile and rules version recorded per row) against the sources. Numbers and IDs only.", "",
             "| check | what | level | status | checked | failed |", "|---|---|---|---|---|---|"]
    lines += [f"| {r.check_id} | {r.check_name} | {r.level} | {r.status} | {r.n_checked} | {r.n_failed} |" for r in results]
    c8 = next((r for r in results if r.check_id == 8), None)
    if c8 and c8.detail.get("share_identical") is not None:
        lines += ["", f"Check 8: {c8.detail['share_identical']:.2%} of team-games identical to pbpstats, "
                      f"{c8.detail['within_1']:.2%} within 1. Distribution of (ours - pbpstats): {c8.detail['difference_distribution']}.", ""]
    if c8 is None or c8.status == "skip":
        lines += ["", "No pbpstats reference exists for this season, so check 8 is skipped."]
    else:
        lines += ["## Team-games that differ from pbpstats", "",
                  "Reported, never fixed to match (working agreement 11).", "",
                  "| game_id | team (defense) | ours | pbpstats | ours - pbpstats |", "|---|---|---|---|---|"]
        lines += [f"| `{g}` | {a} | {o} | {r} | {d:+d} |" for g, a, o, r, d in rows]
    known = next((r.detail.get("known_source_score_conflicts") for r in results if r.check_id == 111), None)
    if known:
        lines += ["", f"Check 111, known source score conflicts (registered in `core.known_gaps`, not failed): {known}."]
    path.write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
