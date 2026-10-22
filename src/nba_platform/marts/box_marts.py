"""Layer-1 marts for the dashboard: player and team box scores per game and per season.

Built from the official box score (reference.nba_player_box) plus a few things of our own:
seconds on court from the play-by-play (marts.player_game_pbp) and the game context from
core.games. Every table has a real PRIMARY KEY and is rebuilt from scratch.

- marts.player_game  (game_id, player_id)
- marts.player_season (season_end_year, season_type, player_id, team_id)   a traded player has one row per team
- marts.team_game    (game_id, team_id)
- marts.team_season  (season_end_year, season_type, team_id)

Provenance (CLAUDE.md working agreement 12): box stats, minutes and the `*_official` columns
are NBA.com values; `pbp_secs_played` is counted from our play-by-play. Nothing here is a
possession of ours: `poss_official` is NBA.com's POSS and is named that way. Ratings built on
it are `ortg_official_poss` / `drtg_official_poss`, to be replaced once our possessions exist.

Usage:
    python -m nba_platform.marts.box_marts
"""

from __future__ import annotations

import sys
from pathlib import Path

from nba_platform import db

COUNTING = ["fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "oreb", "dreb", "reb", "ast", "stl", "blk", "tov", "pf", "pts"]


def _sum(alias: str = "") -> str:
    a = f"{alias}." if alias else ""
    return ", ".join(f"sum({a}{c}) AS {c}" for c in COUNTING)


def _rates(prefix: str = "") -> str:
    """Shooting percentages from totals (NULL when there are no attempts)."""
    p = prefix
    return f"""
        {p}fgm / nullif({p}fga, 0) AS fg_pct,
        {p}fg3m / nullif({p}fg3a, 0) AS fg3_pct,
        {p}ftm / nullif({p}fta, 0) AS ft_pct,
        ({p}fgm + 0.5 * {p}fg3m) / nullif({p}fga, 0) AS efg_pct,
        {p}pts / nullif(2 * ({p}fga + 0.44 * {p}fta), 0) AS ts_pct"""


DDL = {
    "marts.player_game": """(
        game_id TEXT NOT NULL, player_id INTEGER NOT NULL, team_id INTEGER NOT NULL,
        opponent_team_id INTEGER NOT NULL, season_end_year INTEGER NOT NULL, season_type TEXT NOT NULL,
        game_date DATE, is_home BOOLEAN NOT NULL, won BOOLEAN,
        min DOUBLE, pbp_secs_played DOUBLE,
        fgm DOUBLE, fga DOUBLE, fg3m DOUBLE, fg3a DOUBLE, ftm DOUBLE, fta DOUBLE, oreb DOUBLE, dreb DOUBLE,
        reb DOUBLE, ast DOUBLE, stl DOUBLE, blk DOUBLE, tov DOUBLE, pf DOUBLE, pts DOUBLE, plus_minus DOUBLE,
        PRIMARY KEY (game_id, player_id))""",
    "marts.player_season": """(
        season_end_year INTEGER NOT NULL, season_type TEXT NOT NULL, player_id INTEGER NOT NULL, team_id INTEGER NOT NULL,
        games INTEGER NOT NULL, min DOUBLE,
        fgm DOUBLE, fga DOUBLE, fg3m DOUBLE, fg3a DOUBLE, ftm DOUBLE, fta DOUBLE, oreb DOUBLE, dreb DOUBLE,
        reb DOUBLE, ast DOUBLE, stl DOUBLE, blk DOUBLE, tov DOUBLE, pf DOUBLE, pts DOUBLE, plus_minus DOUBLE,
        fg_pct DOUBLE, fg3_pct DOUBLE, ft_pct DOUBLE, efg_pct DOUBLE, ts_pct DOUBLE,
        mpg DOUBLE, ppg DOUBLE, rpg DOUBLE, apg DOUBLE, spg DOUBLE, bpg DOUBLE, tpg DOUBLE,
        pts_per36 DOUBLE, reb_per36 DOUBLE, ast_per36 DOUBLE,
        PRIMARY KEY (season_end_year, season_type, player_id, team_id))""",
    "marts.team_game": """(
        game_id TEXT NOT NULL, team_id INTEGER NOT NULL, opponent_team_id INTEGER NOT NULL,
        season_end_year INTEGER NOT NULL, season_type TEXT NOT NULL, game_date DATE, is_home BOOLEAN NOT NULL,
        won BOOLEAN, opponent_pts DOUBLE,
        fgm DOUBLE, fga DOUBLE, fg3m DOUBLE, fg3a DOUBLE, ftm DOUBLE, fta DOUBLE, oreb DOUBLE, dreb DOUBLE,
        reb DOUBLE, ast DOUBLE, stl DOUBLE, blk DOUBLE, tov DOUBLE, pf DOUBLE, pts DOUBLE,
        poss_official DOUBLE, pace_official DOUBLE,
        PRIMARY KEY (game_id, team_id))""",
    "marts.team_season": """(
        season_end_year INTEGER NOT NULL, season_type TEXT NOT NULL, team_id INTEGER NOT NULL,
        games INTEGER NOT NULL, wins INTEGER, losses INTEGER,
        fgm DOUBLE, fga DOUBLE, fg3m DOUBLE, fg3a DOUBLE, ftm DOUBLE, fta DOUBLE, oreb DOUBLE, dreb DOUBLE,
        reb DOUBLE, ast DOUBLE, stl DOUBLE, blk DOUBLE, tov DOUBLE, pf DOUBLE, pts DOUBLE, opponent_pts DOUBLE,
        poss_official DOUBLE, games_with_poss_official INTEGER,
        fg_pct DOUBLE, fg3_pct DOUBLE, ft_pct DOUBLE, efg_pct DOUBLE, ts_pct DOUBLE,
        ortg_official_poss DOUBLE, drtg_official_poss DOUBLE, pace_official_poss DOUBLE,
        PRIMARY KEY (season_end_year, season_type, team_id))""",
}

INSERTS = {
    "marts.player_game": f"""
        SELECT b.game_id, b.player_id, b.team_id,
               CASE WHEN b.team_id = g.home_team_id THEN g.away_team_id ELSE g.home_team_id END,
               g.season_end_year, g.season_type, g.game_date, b.team_id = g.home_team_id,
               CASE WHEN g.home_score IS NULL OR g.away_score IS NULL THEN NULL
                    WHEN b.team_id = g.home_team_id THEN g.home_score > g.away_score
                    ELSE g.away_score > g.home_score END,
               b.min, p.secs_played,
               {", ".join(f"b.{c}" for c in COUNTING[:-1])}, b.pts, b.plus_minus
        FROM reference.nba_player_box b
        JOIN core.games g USING (game_id)
        LEFT JOIN marts.player_game_pbp p USING (game_id, player_id)""",
    "marts.player_season": f"""
        WITH t AS (SELECT season_end_year, season_type, player_id, team_id, count(*) AS games, sum(min) AS min,
                          {_sum()}, sum(plus_minus) AS plus_minus
                   FROM marts.player_game GROUP BY ALL)
        SELECT season_end_year, season_type, player_id, team_id, games, min,
               {", ".join(COUNTING[:-1])}, pts, plus_minus, {_rates()},
               min / games, pts / games, reb / games, ast / games, stl / games, blk / games, tov / games,
               36 * pts / nullif(min, 0), 36 * reb / nullif(min, 0), 36 * ast / nullif(min, 0)
        FROM t""",
    "marts.team_game": f"""
        WITH t AS (SELECT game_id, team_id, any_value(opponent_team_id) AS opponent_team_id, any_value(season_end_year) AS season_end_year,
                          any_value(season_type) AS season_type, any_value(game_date) AS game_date, any_value(is_home) AS is_home,
                          any_value(won) AS won, {_sum()}
                   FROM marts.player_game GROUP BY game_id, team_id)
        SELECT t.game_id, t.team_id, t.opponent_team_id, t.season_end_year, t.season_type, t.game_date, t.is_home, t.won,
               o.pts, t.fgm, t.fga, t.fg3m, t.fg3a, t.ftm, t.fta, t.oreb, t.dreb, t.reb, t.ast, t.stl, t.blk, t.tov, t.pf, t.pts,
               op.POSS, op.PACE
        FROM t LEFT JOIN t o ON o.game_id = t.game_id AND o.team_id = t.opponent_team_id
        LEFT JOIN reference.nba_team_possessions op ON op.GAME_ID = t.game_id AND op.TEAM_ID = t.team_id""",
    "marts.team_season": f"""
        WITH t AS (SELECT season_end_year, season_type, team_id, count(*) AS games, count(*) FILTER (won) AS wins,
                          count(*) FILTER (NOT won) AS losses, {_sum()}, sum(opponent_pts) AS opponent_pts,
                          sum(poss_official) AS poss_official, count(poss_official) AS games_with_poss_official,
                          sum(CASE WHEN poss_official IS NOT NULL THEN pts END) AS pts_with_poss,
                          sum(CASE WHEN poss_official IS NOT NULL THEN opponent_pts END) AS opp_pts_with_poss
                   FROM marts.team_game GROUP BY ALL)
        SELECT season_end_year, season_type, team_id, games, wins, losses,
               {", ".join(COUNTING[:-1])}, pts, opponent_pts, poss_official, games_with_poss_official, {_rates()},
               100 * pts_with_poss / nullif(poss_official, 0), 100 * opp_pts_with_poss / nullif(poss_official, 0),
               poss_official / nullif(games_with_poss_official, 0)
        FROM t""",
}
ORDER = ["marts.player_game", "marts.player_season", "marts.team_game", "marts.team_season"]


class BoxMartError(RuntimeError):
    """A mart does not add up. The rebuild is rolled back."""


def check_team_points(con) -> int:
    """Games whose player box points differ from the final score in core.games (reported)."""
    return con.execute("""
        SELECT count(*) FROM (
            SELECT t.game_id FROM marts.team_game t JOIN core.games g USING (game_id)
            WHERE t.pts <> CASE WHEN t.is_home THEN g.home_score ELSE g.away_score END)""").fetchone()[0]


def build(con) -> dict:
    """Rebuild the four marts in one transaction. Returns row counts and the points check."""
    con.execute("CREATE SCHEMA IF NOT EXISTS marts")
    con.execute("BEGIN")
    try:
        for name in reversed(ORDER):
            con.execute(f"DROP TABLE IF EXISTS {name}")
        for name in ORDER:
            con.execute(f"CREATE TABLE {name} {DDL[name]}")
            con.execute(f"INSERT INTO {name} {INSERTS[name]}")
        out = {n: con.execute(f"SELECT count(*) FROM {n}").fetchone()[0] for n in ORDER}
        out["games_points_differ_from_score"] = check_team_points(con)
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return out


def write_report(con, counts: dict, path: Path) -> None:
    """docs/validation/box_marts.md: row counts and the games whose box points differ from the score."""
    rows = con.execute("""
        WITH ev AS (SELECT game_id, team_id, sum(points) AS ev_pts FROM core.events GROUP BY ALL)
        SELECT t.game_id, t.is_home, t.pts, ev.ev_pts,
               CASE WHEN t.is_home THEN g.home_score ELSE g.away_score END AS score
        FROM marts.team_game t JOIN core.games g USING (game_id) LEFT JOIN ev USING (game_id, team_id)
        WHERE t.pts <> CASE WHEN t.is_home THEN g.home_score ELSE g.away_score END
        ORDER BY 1, 2""").fetchall()
    lines = ["# Box marts (layer 1): row counts and consistency", "",
             "Built by `nba_platform.marts.box_marts` from the official box score. Numbers and IDs only.", "",
             "| table | rows |", "|---|---|"]
    lines += [f"| `{t}` | {n:,} |" for t, n in counts.items() if t.startswith("marts.")]
    lines += ["", "## Team points: official box vs final score in `core.games`", "",
              f"Team-games where the player box points do not add up to the final score: {len(rows)} "
              f"(in {len({r[0] for r in rows})} games). Reported, not corrected. A box that agrees with the "
              "event points (EV) but not the score is a score conflict in the source; a box that disagrees "
              "with both is an inconsistency in the official box.", "",
              "| game_id | home | box points | event points (EV) | score |", "|---|---|---|---|---|"]
    lines += [f"| `{g}` | {'home' if h else 'away'} | {b:.0f} | {e} | {sc} |" for g, h, b, e, sc in rows]
    path.write_text(chr(10).join(lines) + chr(10), encoding="utf-8")


def main() -> None:
    from nba_platform.db import PROJECT_ROOT

    sys.stdout.reconfigure(encoding="utf-8")
    con = db.connect()
    try:
        counts = build(con)
        write_report(con, counts, PROJECT_ROOT / "docs" / "validation" / "box_marts.md")
        print(counts)
    finally:
        con.close()


if __name__ == "__main__":
    main()
