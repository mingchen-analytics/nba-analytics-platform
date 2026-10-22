"""Build the core logic tables for one season and write them to DuckDB (the only writer).

Runs the pure functions in `nba_platform.core` on a season that is already loaded
(core.events, staging.event_lineups) and writes the results in one transaction:

- `--step stints`: core.stints (rows of that season replaced) and core.events.stint_id.
- `--step possessions`: core.possessions, core.possession_stint_segments and, on core.events,
  possession_id, chance_id, is_between_possessions_ft, foul_event_seq, is_technical_ft; then the
  possession checks (validate/possession_checks.py: 111 points conserved (hard), 7, 8) and the
  report docs/validation/possession_check_{season}.md. Uses the rule profile `--profile`.

Checks after building (hard: the transaction is rolled back): every event has a stint_id;
every team-game's 5 x seconds on court equals the game length. A reload of the season's
events (pipeline) clears events.stint_id, so this must run again afterwards.

Usage:
    python -m nba_platform.build_core --season-end-year 2005 --season-type regular --step stints
"""

from __future__ import annotations

import argparse
import sys
import time

import pandas as pd

from nba_platform import db
from nba_platform.core.free_throws import link_free_throws
from nba_platform.core.possessions import POSSESSION_COLUMNS, SEGMENT_COLUMNS, build_possessions
from nba_platform.core.rebounds import classify_rebounds
from nba_platform.core.stints import STINT_COLUMNS, build_stints, player_seconds
from nba_platform.rules import load_rules

PROFILE = "pbpstats_compat"   # copy first, then deviate (CLAUDE.md)
EVENT_COLUMNS = ("game_id, event_seq, source_event_num, period, clock, secs_elapsed_game, team_id, event_type, "
                 "event_subtype, source_msg_type, player1_id, player2_id, player3_id, points, home_score, away_score")


class BuildCoreError(RuntimeError):
    """A core table failed its checks. Nothing was written."""


def season_inputs(con, y: int, t: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    games = con.execute("""SELECT game_id, num_periods FROM core.games
                           WHERE season_end_year = ? AND season_type = ? AND NOT coalesce(pbp_missing, FALSE)""", [y, t]).df()
    events = con.execute("""SELECT e.game_id, e.event_seq, e.period, e.secs_elapsed_game, e.event_type FROM core.events e
                            JOIN core.games g USING (game_id) WHERE g.season_end_year = ? AND g.season_type = ?
                            ORDER BY 1, 2""", [y, t]).df()
    lineups = con.execute("""SELECT l.game_id, l.event_seq, l.home_player_ids, l.away_player_ids FROM staging.event_lineups l
                             JOIN core.games g USING (game_id) WHERE g.season_end_year = ? AND g.season_type = ?
                             ORDER BY 1, 2""", [y, t]).df()
    return games, events, lineups


def build_season_stints(events: pd.DataFrame, lineups: pd.DataFrame, rules: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(stints, event_stint) for a season; event_stint = (game_id, event_seq, stint_id)."""
    by_game = dict(tuple(lineups.groupby("game_id")))
    stints, links = [], []
    for gid, ev in events.groupby("game_id"):
        st, sid = build_stints(ev, by_game[gid], rules)
        stints.append(st)
        links.append(pd.DataFrame({"game_id": gid, "event_seq": ev["event_seq"].values, "stint_id": sid.values}))
    return pd.concat(stints, ignore_index=True), pd.concat(links, ignore_index=True)


def check_stints(stints: pd.DataFrame, links: pd.DataFrame, games: pd.DataFrame) -> dict:
    missing = int(links["stint_id"].isna().sum())
    ps = player_seconds(stints)
    length = games.set_index("game_id")["num_periods"].map(lambda n: 2880 + 300 * (int(n) - 4))
    team = ps.groupby(["game_id", "side"], as_index=False)["secs"].sum()
    bad_time = int((team["secs"] != 5 * team["game_id"].map(length)).sum())
    out = {"games": int(stints["game_id"].nunique()), "stints": len(stints), "events": len(links),
           "events_without_stint": missing, "team_games_time_mismatch": bad_time,
           "zero_length_stints": int((stints["end_secs"] == stints["start_secs"]).sum()),
           "lineup_change_without_sub": int((stints["start_reason"] == "lineup_change").sum())}
    if missing or bad_time or out["games"] != len(games):
        raise BuildCoreError(f"stint checks failed: {out}")
    return out


def write_stints(con, y: int, t: str, stints: pd.DataFrame, links: pd.DataFrame, rules_version: str) -> None:
    st = stints[STINT_COLUMNS].assign(rules_version=rules_version)
    con.register("st_df", st)
    con.register("link_df", links)
    con.execute("BEGIN")
    try:
        season = "SELECT game_id FROM core.games WHERE season_end_year = ? AND season_type = ?"
        con.execute(f"DELETE FROM core.stints WHERE game_id IN ({season})", [y, t])
        con.execute("INSERT INTO core.stints SELECT * FROM st_df")
        con.execute(f"UPDATE core.events SET stint_id = NULL WHERE game_id IN ({season})", [y, t])
        con.execute("""UPDATE core.events e SET stint_id = l.stint_id FROM link_df l
                       WHERE e.game_id = l.game_id AND e.event_seq = l.event_seq""")
        n = con.execute(f"SELECT count(*) FILTER (stint_id IS NULL), count(*) FROM core.events WHERE game_id IN ({season})",
                        [y, t]).fetchone()
        if n[0]:
            raise BuildCoreError(f"{n[0]} of {n[1]} events have no stint_id after the update")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.unregister("st_df")
        con.unregister("link_df")


def build_season_possessions(con, y: int, t: str, rules: dict):
    """(possessions, segments, event_links, free_throw_links, diagnostics, stints, stint_links) for a loaded season.

    The stints are built on the way (the possession code needs them), so one pass fills both tables.
    """
    games = con.execute("""SELECT * FROM core.games WHERE season_end_year = ? AND season_type = ?
                           AND NOT coalesce(pbp_missing, FALSE)""", [y, t]).df().set_index("game_id")
    events = con.execute(f"""SELECT {EVENT_COLUMNS} FROM core.events WHERE game_id IN
                             (SELECT game_id FROM core.games WHERE season_end_year = ? AND season_type = ?)
                             ORDER BY game_id, event_seq""", [y, t]).df()
    lineups = con.execute("""SELECT l.game_id, l.event_seq, l.home_player_ids, l.away_player_ids FROM staging.event_lineups l
                             JOIN core.games g USING (game_id) WHERE g.season_end_year = ? AND g.season_type = ?
                             ORDER BY 1, 2""", [y, t]).df()
    by_game = dict(tuple(lineups.groupby("game_id")))
    pos_all, seg_all, links_all, ft_all, st_all, stl_all = [], [], [], [], [], []
    diag: dict = {}
    for gid, ev in events.groupby("game_id"):
        game = games.loc[gid].copy()
        game["game_id"] = gid
        st, sid = build_stints(ev, by_game[gid], rules)
        st_all.append(st)
        stl_all.append(pd.DataFrame({"game_id": gid, "event_seq": ev["event_seq"].values, "stint_id": sid.values}))
        ft = link_free_throws(ev)
        rb = classify_rebounds(ev, ft, rules)
        pos, links, seg, d = build_possessions(ev, ft, rb, st, sid, game, rules)
        pos_all.append(pos)
        seg_all.append(seg)
        links_all.append(links.assign(game_id=gid))
        ft_all.append(ft[["event_seq", "foul_event_seq", "is_technical_ft"]].assign(game_id=gid))
        for k, v in d.items():
            diag[k] = diag.get(k, 0) + v
    return (pd.concat(pos_all, ignore_index=True), pd.concat(seg_all, ignore_index=True),
            pd.concat(links_all, ignore_index=True), pd.concat(ft_all, ignore_index=True), diag,
            pd.concat(st_all, ignore_index=True), pd.concat(stl_all, ignore_index=True))


def write_possessions(con, y: int, t: str, pos, seg, links, ft, rules: dict, profile: str) -> None:
    pos = pos[POSSESSION_COLUMNS].assign(rules_profile=profile)
    seg = seg[SEGMENT_COLUMNS]
    ev_links = links[["game_id", "event_seq", "possession_id", "chance_id", "is_between_possessions_ft"]]
    for name, df in (("pos_df", pos), ("seg_df", seg), ("ev_links", ev_links), ("ft_df", ft)):
        con.register(name, df)
    season = "SELECT game_id FROM core.games WHERE season_end_year = ? AND season_type = ?"
    con.execute("BEGIN")
    try:
        con.execute(f"DELETE FROM core.possession_stint_segments WHERE game_id IN ({season})", [y, t])
        con.execute(f"DELETE FROM core.possessions WHERE game_id IN ({season})", [y, t])
        con.execute("INSERT INTO core.possessions SELECT * FROM pos_df")
        con.execute("INSERT INTO core.possession_stint_segments SELECT * FROM seg_df")
        con.execute(f"""UPDATE core.events SET possession_id = NULL, chance_id = NULL, is_between_possessions_ft = NULL,
                        foul_event_seq = NULL, is_technical_ft = NULL WHERE game_id IN ({season})""", [y, t])
        con.execute("""UPDATE core.events e SET possession_id = l.possession_id, chance_id = l.chance_id,
                              is_between_possessions_ft = l.is_between_possessions_ft
                       FROM ev_links l WHERE e.game_id = l.game_id AND e.event_seq = l.event_seq""")
        con.execute("""UPDATE core.events e SET foul_event_seq = f.foul_event_seq, is_technical_ft = f.is_technical_ft
                       FROM ft_df f WHERE e.game_id = f.game_id AND e.event_seq = f.event_seq""")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        for name in ("pos_df", "seg_df", "ev_links", "ft_df"):
            con.unregister(name)


def run_possessions(con, y: int, t: str, profile: str = PROFILE) -> dict:
    from nba_platform.db import PROJECT_ROOT
    from nba_platform.validate import possession_checks

    rules = load_rules(profile=profile)
    t0 = time.time()
    pos, seg, links, ft, diag, stints, stint_links = build_season_possessions(con, y, t, rules)
    games = con.execute("SELECT game_id, num_periods FROM core.games WHERE season_end_year = ? AND season_type = ? "
                        "AND NOT coalesce(pbp_missing, FALSE)", [y, t]).df()
    check_stints(stints, stint_links, games)
    write_stints(con, y, t, stints, stint_links, rules["rules_version"])
    write_possessions(con, y, t, pos, seg, links, ft, rules, profile)
    results = possession_checks.run(con, y, t)
    possession_checks.write_report(con, y, t, results, PROJECT_ROOT / "docs" / "validation" / f"possession_check_{y}_{t}.md")
    hard = [r for r in results if r.level == "hard" and r.status == "fail"]
    out = {"stints": len(stints), "possessions": len(pos), "segments": len(seg), "diagnostics": diag,
           "checks": {r.check_id: (r.status, r.n_failed) for r in results}, "secs": round(time.time() - t0, 1)}
    if hard:
        raise BuildCoreError(f"hard possession check failed: {out}")
    return out


def run(con, y: int, t: str, step: str, profile: str = PROFILE) -> dict:
    if step == "possessions":
        return run_possessions(con, y, t, profile)
    rules = load_rules(profile=PROFILE)
    if step != "stints":
        raise ValueError(f"unknown step {step!r}")
    t0 = time.time()
    games, events, lineups = season_inputs(con, y, t)
    stints, links = build_season_stints(events, lineups, rules)
    out = check_stints(stints, links, games)
    write_stints(con, y, t, stints, links, rules["rules_version"])
    out["secs"] = round(time.time() - t0, 1)
    return out


def loaded_seasons(con) -> list[tuple[int, str]]:
    """Every season with play-by-play in the database, oldest first (regular season before playoffs)."""
    return con.execute("""SELECT DISTINCT g.season_end_year, g.season_type FROM core.games g
                          WHERE NOT coalesce(g.pbp_missing, FALSE) ORDER BY 1, 2 DESC""").fetchall()


def run_all(con, step: str, profile: str, seasons: list[tuple[int, str]] | None = None) -> list[dict]:
    """Every season independently; an error in one season is recorded and printed, never hidden."""
    out = []
    for y, t in seasons or loaded_seasons(con):
        try:
            res = run(con, y, t, step, profile)
            line = {"season_end_year": y, "season_type": t, "status": "ok", **res}
        except Exception as exc:
            line = {"season_end_year": y, "season_type": t, "status": "error", "error": f"{type(exc).__name__}: {exc}"[:300]}
        print(line, flush=True)
        out.append(line)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--season-end-year", type=int)
    ap.add_argument("--season-type", choices=["regular", "playoffs"], default="regular")
    ap.add_argument("--all", action="store_true", help="every loaded season (check 8 is skipped where pbpstats has no reference)")
    ap.add_argument("--step", choices=["stints", "possessions"], required=True)
    ap.add_argument("--profile", choices=["pbpstats_compat", "custom"], default=PROFILE)
    args = ap.parse_args()
    if not args.all and args.season_end_year is None:
        ap.error("--season-end-year or --all is required")
    sys.stdout.reconfigure(encoding="utf-8")
    con = db.connect()
    try:
        if args.all:
            res = run_all(con, args.step, args.profile)
            sys.exit(0 if all(r["status"] == "ok" for r in res) else 1)
        print(run(con, args.season_end_year, args.season_type, args.step, args.profile))
    finally:
        con.close()


if __name__ == "__main__":
    main()
