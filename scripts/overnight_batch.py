"""Overnight batch (2026-10-18). One process, tasks run in order; only this process writes
DuckDB while it runs.

Rules
- every task is isolated: an error is logged and the next task runs;
- re-runnable: finished downloads / computations are skipped, an interrupted run resumes
  (task state in logs/overnight_2026-10-18_state.json; downloads skip existing files);
- NBA.com: serial, 4-5 s apart plus jitter, 30 s timeout, raw JSON cached in
  data/raw/nba_api/{category}/{season}/ and recorded in the manifest; 5 consecutive
  failures stop all NBA.com requests for the rest of the run (other tasks continue);
- existing files in data/raw/ are never modified;
- detailed log logs/overnight_2026-10-18.log, short progress on the terminal, summary
  logs/overnight_2026-10-18_summary.md (< 100 lines).

Tasks: A reproducibility, B nbastats PBP, C matchups, D possession benchmark vs pbpstats,
E BigDataBall, F NBA.com season-level data, G possession benchmark vs NBA official,
H single-game box scores until the deadline (raw JSON only).

Usage
    python scripts/overnight_batch.py                 # full run
    python scripts/overnight_batch.py --trial         # tiny run of every task (A without rebuild)
    python scripts/overnight_batch.py --only D,G      # selected tasks
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import random
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nba_platform import db, pipeline  # noqa: E402
from nba_platform.ingest.download import RAW_DIR, download, fetch_shufinskiy_index, record_in_manifest  # noqa: E402
from nba_platform.load import STAGING_DIR  # noqa: E402
from nba_platform.rules import load_rules  # noqa: E402
from nba_platform.seasons import season_label  # noqa: E402
from nba_platform.staging import shufinskiy as sh  # noqa: E402

LOGS = ROOT / "logs"
NBA_DIR = RAW_DIR / "nba_api"
TASKS = "ABCDEFGH"
CORE_TABLES = ["core.games", "core.events", "core.shots", "core.teams", "core.team_xref", "core.players",
               "core.player_xref", "core.known_gaps", "core.shot_quality_flags", "staging.event_lineups",
               "staging.player_names"]
SEASON_TYPES = {"regular": "Regular Season", "playoffs": "Playoffs"}
TRACKING = ["SpeedDistance", "Possessions", "Passing", "Drives", "CatchShoot", "PullUpShot", "Rebounding",
            "Defense", "ElbowTouch", "PostTouch", "PaintTouch", "Efficiency"]
SHOT_CONTEXT = {
    "close_def_dist_range_nullable": ["0-2 Feet - Very Tight", "2-4 Feet - Tight", "4-6 Feet - Open", "6+ Feet - Wide Open"],
    "touch_time_range_nullable": ["Touch < 2 Seconds", "Touch 2-6 Seconds", "Touch 6+ Seconds"],
    "dribble_range_nullable": ["0 Dribbles", "1 Dribble", "2 Dribbles", "3-6 Dribbles", "7+ Dribbles"],
    "shot_clock_range_nullable": ["24-22", "22-18 Very Early", "18-15 Early", "15-7 Average", "7-4 Late",
                                  "4-0 Very Late", "ShotClock Off"],
}
PLAY_TYPES = ["Isolation", "Transition", "PRBallHandler", "PRRollman", "Postup", "Spotup", "Handoff", "Cut",
              "OffScreen", "OffRebound", "Misc"]
FIRST_SEASON = {"tracking": 2014, "hustle": 2016, "shot_context": 2014, "play_type": 2015, "team_possessions": 1997}
LAST_SEASON = 2026

log = logging.getLogger("overnight")


def progress(msg: str) -> None:
    """Short line on the terminal (and in the log)."""
    log.info(msg)
    print(f"{datetime.now():%H:%M:%S} {msg}", flush=True)


# --------------------------------------------------------------------------- NBA.com client


class NbaStopped(RuntimeError):
    pass


def _sleep_until(t_end: float) -> None:
    while time.time() < t_end:
        time.sleep(min(60, max(0.0, t_end - time.time())))


class Nba:
    COOLDOWN_MIN = (45, 90, 90)  # owner 2026-10-18: 45 min, then 90 min; at most 3 per night
    REST_EVERY, REST_MIN = 600, 30  # proactive rest: 30 min after every 600 requests sent

    def _rest(self) -> None:
        self.rested = self.requests
        until = datetime.now() + timedelta(minutes=self.REST_MIN)
        if self.deadline and until >= self.deadline:
            self.stopped = True
            progress(f"NBA.com: planned rest after {self.requests} requests would pass the deadline -> stopped")
            raise NbaStopped("deadline")
        self.rests.append(f"{datetime.now():%H:%M} +{self.REST_MIN} min")
        progress(f"NBA.com: planned rest after {self.requests} requests: {self.REST_MIN} min (until {until:%H:%M})")
        _sleep_until(until.timestamp())
        progress("NBA.com: rest over, resuming")

    def __init__(self, max_fail: int = 5, deadline: datetime | None = None):
        self.max_fail, self.streak, self.stopped, self.last = max_fail, 0, False, 0.0
        self.requests = self.cached = self.failures = 0
        self.cooldowns: list[str] = []
        self.rests: list[str] = []
        self.rested = 0
        self.deadline = deadline

    def get(self, category: str, season_dir: str, name: str, cls, **params) -> dict | None:
        path = NBA_DIR / category / season_dir / f"{name}.json"
        if path.exists():
            self.cached += 1
            return json.loads(path.read_text(encoding="utf-8"))
        if self.stopped:
            raise NbaStopped("NBA.com requests stopped after repeated failures")
        if self.requests and self.requests % self.REST_EVERY == 0 and self.rested < self.requests:
            self._rest()  # owner 2026-10-19: rest proactively instead of waiting to be throttled
        wait = 7 + random.random() - (time.time() - self.last)  # 7-8 s apart, random jitter
        if wait > 0:
            time.sleep(wait)
        self.last = time.time()
        self.requests += 1
        try:
            data = cls(timeout=30, **params).get_dict()
        except Exception as exc:  # 429 / 403 / timeout / anything
            self.failures += 1
            self.streak += 1
            log.warning("NBA.com failure %d/%d %s %s %s: %s", self.streak, self.max_fail, category, season_dir, name, exc)
            if self.streak >= self.max_fail:
                self._cool_down_or_stop()
            return None
        self.streak = 0
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".part")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.rename(path)
        record_in_manifest(path, f"stats.nba.com {cls.__name__} {params}", datetime.now(timezone.utc).isoformat(timespec="seconds"))
        return data

    def _cool_down_or_stop(self) -> None:
        n = len(self.cooldowns)
        if n >= len(self.COOLDOWN_MIN):
            self.stopped = True
            progress(f"NBA.com: {self.max_fail} consecutive failures after {n} cooldowns -> all NBA.com requests stopped")
            return
        minutes = self.COOLDOWN_MIN[n]
        until = datetime.now() + timedelta(minutes=minutes)
        if self.deadline and until >= self.deadline:
            self.stopped = True
            progress(f"NBA.com: cooldown {n + 1} ({minutes} min) would pass the deadline -> stopped")
            return
        self.cooldowns.append(f"{datetime.now():%H:%M} +{minutes} min")
        progress(f"NBA.com: {self.max_fail} consecutive failures -> cooldown {n + 1}/{len(self.COOLDOWN_MIN)}: "
                 f"{minutes} min (until {until:%H:%M})")
        _sleep_until(until.timestamp())
        self.streak = 0
        progress(f"NBA.com: cooldown {n + 1} over, resuming")


# --------------------------------------------------------------------------- helpers


def rows_of(data: dict) -> pd.DataFrame:
    sets = data.get("resultSets") or data.get("resultSet") or []
    if isinstance(sets, dict):
        sets = [sets]
    if not sets:
        return pd.DataFrame()
    s = sets[0]
    return pd.DataFrame(s.get("rowSet", []), columns=s.get("headers", []))


def season_list(first_end: int, last_end: int = LAST_SEASON) -> list[int]:
    return list(range(first_end, last_end + 1))


def table_snapshot(con) -> dict[str, dict]:
    out = {}
    for t in CORE_TABLES:
        try:
            n, h = con.execute(f"SELECT count(*), coalesce(sum(hash(x))::HUGEINT, 0) FROM {t} x").fetchone()
            out[t] = {"rows": int(n), "hash": str(h)}
        except duckdb.Error as exc:
            out[t] = {"rows": None, "hash": f"error: {exc}"}
    return out


# --------------------------------------------------------------------------- tasks


def task_a(con, ctx) -> dict:
    """Reproducibility: snapshot, rebuild from zero into a fresh database, compare."""
    before = table_snapshot(con)
    if ctx.trial:
        again = table_snapshot(con)
        same = before == again
        return {"status": "success", "numbers": {"tables": len(before), "snapshot_repeatable": same,
                                                 "rows_events": before["core.events"]["rows"]},
                "note": "trial: snapshot only, no rebuild"}
    rebuild = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "nba_platform" / "rebuild_check.duckdb"
    for f in (rebuild, rebuild.with_name(rebuild.name + ".wal")):
        if f.exists():
            f.unlink()  # derived database from a previous check
    con2 = db.connect(rebuild)
    try:
        with open(ctx.log_path, "a", encoding="utf-8") as fh, contextlib.redirect_stdout(fh):
            pipeline.run_all(con2, range(1997, LAST_SEASON + 1))
        after = table_snapshot(con2)
    finally:
        con2.close()
    diffs = [f"{t}: rows {before[t]['rows']} -> {after[t]['rows']}, hash {'same' if before[t]['hash'] == after[t]['hash'] else 'DIFFERENT'}"
             for t in CORE_TABLES if before[t] != after[t]]
    for d in diffs:
        log.info("A difference: %s", d)
    return {"status": "success", "numbers": {"tables_compared": len(CORE_TABLES), "tables_identical": len(CORE_TABLES) - len(diffs),
                                             "differences": diffs[:8], "rebuild_db": str(rebuild)}}


def task_b(con, ctx) -> dict:
    idx = fetch_shufinskiy_index()
    keys = sorted(k for k in idx if k.startswith("nbastats_") and not k.startswith("nbastatsv3"))
    if ctx.trial:
        keys = [k for k in keys if not (RAW_DIR / "shufinskiy" / f"{k}.tar.xz").exists()][:1] or keys[:1]
    got = skipped = 0
    for k in keys:
        st = download(idx[k], RAW_DIR / "shufinskiy" / f"{k}.tar.xz")
        got += st == "downloaded"
        skipped += st == "skipped"
        log.info("B %s %s", k, st)
    return {"status": "success", "numbers": {"files": len(keys), "downloaded": got, "already_present": skipped}}


def task_c(con, ctx) -> dict:
    idx = fetch_shufinskiy_index()
    years = [2024] if ctx.trial else list(range(2017, 2025))
    out_dir = STAGING_DIR / "reference" / "matchups"
    out_dir.mkdir(parents=True, exist_ok=True)
    for y in years:
        # regular season and playoffs (playoffs added 2026-10-19); file season = start year
        for key, stype in ((f"matchups_{y}", "regular"), (f"matchups_po_{y}", "playoffs")):
            if key not in idx:
                log.warning("C: %s not in shufinskiy list", key)
                continue
            dest = RAW_DIR / "shufinskiy" / f"{key}.tar.xz"
            download(idx[key], dest)
            pq = out_dir / f"{key}.parquet"
            if not pq.exists():
                df = sh.read_tar_csv(dest, dtype=str)
                df["season_end_year"] = y + 1
                df["season_type"] = stype
                df.to_parquet(pq, index=False)
    files = sorted(str(p).replace("\\", "/") for p in out_dir.glob("matchups_*.parquet"))
    con.execute("CREATE SCHEMA IF NOT EXISTS reference")
    con.execute(f"CREATE OR REPLACE TABLE reference.matchups AS SELECT * FROM read_parquet({files}, union_by_name = true)")
    cols = [r[0] for r in con.execute("DESCRIBE reference.matchups").fetchall()]
    n = con.execute("SELECT count(*) FROM reference.matchups").fetchone()[0]
    gcol = next((c for c in cols if c.upper() in ("GAME_ID", "GAMEID")), None)
    per = con.execute(f"""SELECT season_type, season_end_year, count(*), count(DISTINCT {gcol or "season_end_year"})
                          FROM reference.matchups GROUP BY 1, 2 ORDER BY 1, 2""").fetchall()
    games = con.execute(f"SELECT count(DISTINCT {gcol}) FROM reference.matchups").fetchone()[0] if gcol else None
    if gcol:  # share of matchup games that exist in core.games
        in_core = con.execute(f"""SELECT avg((lpad(CAST(m.g AS VARCHAR), 10, '0') IN (SELECT game_id FROM core.games))::INT)
                                  FROM (SELECT DISTINCT {gcol} AS g FROM reference.matchups) m""").fetchone()[0]
    else:
        in_core = None
    nulls = {}
    for c in cols[:6]:
        nulls[c] = round(con.execute(f'SELECT avg(("{c}" IS NULL)::INT) FROM reference.matchups').fetchone()[0], 4)
    return {"status": "success", "numbers": {"rows": n, "games": games, "games_in_core": round(in_core or 0, 4),
                                             "columns": len(cols),
                                             "per_season_type_rows_games": per, "null_share_first_cols": nulls}}


def task_d(con, ctx) -> dict:
    """ramirobentes reference possessions (minus <= 2 s / 0-point starts) vs pbpstats, per team-game."""
    from nba_platform.reference.pbpstats import available_files
    from nba_platform.validate import phase3_prep as prep

    con.execute("CREATE SCHEMA IF NOT EXISTS reference")
    con.execute("""CREATE TABLE IF NOT EXISTS reference.possession_count_benchmark (
        season_end_year INTEGER, season_type TEXT, game_id TEXT, team_abbr TEXT,
        rb_poss_all INTEGER, rb_poss_excl_eop INTEGER, pbpstats_poss INTEGER, diff INTEGER)""")
    done = set(con.execute("SELECT DISTINCT season_end_year, season_type FROM reference.possession_count_benchmark").fetchall())
    files = [(y, t) for y, t, _ in available_files()]
    if ctx.trial:
        files = [f for f in files if f not in done][:1] or files[:1]
    rules, t0 = load_rules(), load_rules()["end_of_period"]["end_of_period_threshold_secs"]
    n_new = 0
    for y, t in files:
        if (y, t) in done and not ctx.trial:
            continue
        mem = duckdb.connect()
        prep.build(mem, y, rules, season_type=t)
        df = mem.execute(f"""
            WITH r AS (
                SELECT game_id, offense AS team_abbr, count(*) AS rb_all,
                       count(*) FILTER (NOT (start_remaining <= {t0} AND offense_points = 0)) AS rb_excl
                FROM rbp4 GROUP BY ALL),
            teams AS (SELECT DISTINCT game_id, team_home, team_away FROM rbe),
            p AS (SELECT p.game_id, CASE WHEN p.defense = t.team_home THEN t.team_away ELSE t.team_home END AS team_abbr,
                         count(*) AS ps
                  FROM psp p JOIN teams t USING (game_id) GROUP BY ALL)
            SELECT {y} AS season_end_year, '{t}' AS season_type, r.game_id, r.team_abbr,
                   r.rb_all AS rb_poss_all, r.rb_excl AS rb_poss_excl_eop, p.ps AS pbpstats_poss,
                   r.rb_excl - p.ps AS diff
            FROM r JOIN p USING (game_id, team_abbr)""").df()
        mem.close()
        con.execute("DELETE FROM reference.possession_count_benchmark WHERE season_end_year = ? AND season_type = ?", [y, t])
        con.register("bench", df)
        con.execute("INSERT INTO reference.possession_count_benchmark SELECT * FROM bench")
        con.unregister("bench")
        n_new += 1
        log.info("D %s %s: %d team-games", y, t, len(df))
    dist = con.execute("""
        SELECT season_end_year, season_type, count(*),
               avg((abs(diff) = 0)::INT), avg((abs(diff) = 1)::INT), avg((abs(diff) = 2)::INT), avg((abs(diff) >= 3)::INT)
        FROM reference.possession_count_benchmark GROUP BY 1, 2 ORDER BY 2, 1""").fetchall()
    tot = con.execute("SELECT count(*), avg((diff = 0)::INT), avg((abs(diff) <= 1)::INT) FROM reference.possession_count_benchmark").fetchone()
    ctx.d_dist = dist
    return {"status": "success", "numbers": {"seasons_computed_now": n_new, "season_files": len(dist), "team_games": tot[0],
                                             "share_diff_0": round(tot[1] or 0, 4), "share_diff_le1": round(tot[2] or 0, 4)}}


def task_e(con, ctx) -> dict:
    from nba_platform.validate import bdb_crosscheck

    seasons = ["2014-15"] if ctx.trial else None
    with open(ctx.log_path, "a", encoding="utf-8") as fh, contextlib.redirect_stdout(fh):
        summ = bdb_crosscheck.run(con, seasons=seasons)
    ctx.e_rows = summ
    return {"status": "success", "numbers": {"seasons": len(summ)}}


def _f_jobs(ctx) -> list[tuple]:
    """(category, season_end_year, season_type, file name, endpoint class, params)."""
    from nba_api.stats import endpoints as ep

    jobs = []
    years = lambda cat: [LAST_SEASON] if ctx.trial else season_list(FIRST_SEASON[cat])  # noqa: E731
    for y in years("team_possessions"):
        jobs.append(("team_possessions", y, "all", "advanced_all_types", ep.TeamGameLogs,
                     {"season_nullable": season_label(y), "measure_type_player_game_logs_nullable": "Advanced"}))
    for y in years("hustle"):
        for t, st in SEASON_TYPES.items():
            jobs.append(("hustle", y, t, f"{t}__player", ep.LeagueHustleStatsPlayer, {"season": season_label(y), "season_type_all_star": st}))
            jobs.append(("hustle", y, t, f"{t}__team", ep.LeagueHustleStatsTeam, {"season": season_label(y), "season_type_all_star": st}))
    for y in years("tracking"):
        for t, st in SEASON_TYPES.items():
            for m in TRACKING:
                jobs.append(("tracking", y, t, f"{t}__{m}", ep.LeagueDashPtStats,
                             {"season": season_label(y), "season_type_all_star": st, "pt_measure_type": m, "player_or_team": "Player"}))
    for y in years("shot_context"):
        for t, st in SEASON_TYPES.items():
            for par, values in SHOT_CONTEXT.items():
                for v in values:
                    jobs.append(("shot_context", y, t, f"{t}__{par.replace('_nullable', '')}__{v}".replace(" ", "_").replace("<", "lt").replace("+", "plus"),
                                 ep.LeagueDashPlayerPtShot, {"season": season_label(y), "season_type_all_star": st, par: v}))
    for y in years("play_type"):
        for t, st in SEASON_TYPES.items():
            for grp in ("offensive", "defensive"):
                for pt in ("P", "T"):
                    for play in PLAY_TYPES:
                        jobs.append(("play_type", y, t, f"{t}__{grp}__{pt}__{play}", ep.SynergyPlayTypes,
                                     {"season": season_label(y), "season_type_all_star": st, "play_type_nullable": play,
                                      "type_grouping_nullable": grp, "player_or_team_abbreviation": pt}))
    if ctx.trial:  # one request per category
        seen, keep = set(), []
        for j in jobs:
            if j[0] not in seen:
                seen.add(j[0])
                keep.append(j)
        jobs = keep
    return jobs


def load_f_tables(con) -> dict[str, int]:
    """Rebuild one reference table per category from every cached JSON (season + season_type added)."""
    out = {}
    con.execute("CREATE SCHEMA IF NOT EXISTS reference")
    for cat in FIRST_SEASON:
        frames = []
        for path in sorted((NBA_DIR / cat).glob("*/*.json")):
            df = rows_of(json.loads(path.read_text(encoding="utf-8")))
            if df.empty:
                continue
            season, parts = path.parent.name, path.stem.split("__")
            # DuckDB column names are case-insensitive: keep a source column named like ours apart
            df = df.rename(columns={c: f"{c}_source" for c in df.columns if c.lower() in ("season", "season_type")})
            df.insert(0, "season", season)
            df.insert(1, "season_type", parts[0])
            for i, p in enumerate(parts[1:]):
                df.insert(2 + i, f"request_param_{i + 1}", p)
            frames.append(df)
        if not frames:
            continue
        all_df = pd.concat(frames, ignore_index=True, sort=False)
        if cat == "team_possessions":  # one request holds every game type: label by game-ID prefix
            prefix = all_df["GAME_ID"].astype(str).str.zfill(10).str[:3]
            all_df["season_type"] = prefix.map({"002": "regular", "004": "playoffs", "001": "preseason",
                                                "005": "play_in", "003": "all_star", "006": "cup_final"}).fillna("other")
        con.register("f_df", all_df)
        con.execute(f"CREATE OR REPLACE TABLE reference.nba_{cat} AS SELECT * FROM f_df")
        con.unregister("f_df")
        out[cat] = len(all_df)
    return out


def task_f(con, ctx) -> dict:
    jobs = _f_jobs(ctx)
    done = failed = 0
    stopped = False
    for cat, y, t, name, cls, params in jobs:
        try:
            data = ctx.nba.get(cat, season_label(y), name, cls, **params)
        except NbaStopped:
            stopped = True
            break
        if data is None:
            failed += 1
        else:
            done += 1
        if (done + failed) % 100 == 0:
            progress(f"F {done + failed}/{len(jobs)} ({cat} {season_label(y)})")
    tables = load_f_tables(con)
    status = "incomplete" if stopped or failed else "success"
    return {"status": status, "numbers": {"jobs": len(jobs), "ok_or_cached": done, "failed": failed,
                                          "stopped_by_failures": stopped, "tables": tables}}


def task_g(con, ctx) -> dict:
    """ramirobentes reference possessions (all) vs NBA official POSS per team-game."""
    if not con.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'reference' "
                       "AND table_name = 'nba_team_possessions'").fetchone()[0]:
        return {"status": "skipped", "note": "no official possessions loaded (task F)"}
    rb_files = sorted((RAW_DIR / "ramirobentes").glob("pbp_*.parquet"))
    if ctx.trial:
        rb_files = [p for p in rb_files if p.name == f"pbp_regular_{LAST_SEASON}.parquet"]
    globs = [str(p).replace("\\", "/") for p in rb_files]
    con.execute(f"""
        CREATE OR REPLACE TABLE reference.possession_count_benchmark_official AS
        WITH rb AS (
            SELECT season AS season_end_year, CASE WHEN season_type = 'playoffs' THEN 'playoffs' ELSE 'regular' END AS season_type,
                   game_id, any_value(team_home) AS home, any_value(team_away) AS away,
                   sum(poss_home)::INT AS rb_home, sum(poss_away)::INT AS rb_away
            FROM read_parquet({globs}, union_by_name = true) GROUP BY ALL),
        x AS (  -- team IDs from core.games (home / away), not from the abbreviation
            SELECT rb.season_end_year, rb.season_type, rb.game_id, rb.home AS team_abbr, g.home_team_id AS team_id,
                   rb.rb_home AS rb_poss FROM rb JOIN core.games g USING (game_id)
            UNION ALL
            SELECT rb.season_end_year, rb.season_type, rb.game_id, rb.away, g.away_team_id, rb.rb_away
            FROM rb JOIN core.games g USING (game_id)),
        nba AS (
            SELECT lpad(CAST(GAME_ID AS VARCHAR), 10, '0') AS game_id, CAST(TEAM_ID AS INTEGER) AS team_id,
                   CAST(POSS AS DOUBLE) AS nba_poss FROM reference.nba_team_possessions)
        SELECT x.season_end_year, x.season_type, x.game_id, x.team_abbr, x.team_id, x.rb_poss, nba.nba_poss,
               x.rb_poss - nba.nba_poss AS diff
        FROM x JOIN nba USING (game_id, team_id)""")
    dist = con.execute("""
        SELECT season_end_year, season_type, count(*),
               avg((abs(diff) < 0.5)::INT), avg((abs(diff) >= 0.5 AND abs(diff) < 1.5)::INT),
               avg((abs(diff) >= 1.5 AND abs(diff) < 2.5)::INT), avg((abs(diff) >= 2.5)::INT)
        FROM reference.possession_count_benchmark_official GROUP BY 1, 2 ORDER BY 2, 1""").fetchall()
    tot = con.execute("SELECT count(*), avg((abs(diff) < 0.5)::INT), avg((abs(diff) < 1.5)::INT) "
                      "FROM reference.possession_count_benchmark_official").fetchone()
    ctx.g_dist = dist
    return {"status": "success", "numbers": {"season_files": len(dist), "team_games": tot[0],
                                             "share_diff_0": round(tot[1] or 0, 4), "share_diff_le1": round(tot[2] or 0, 4)}}


def n_players(obj) -> int:
    """Players listed anywhere in a box-score response (0 = empty shell)."""
    if isinstance(obj, dict):
        return sum(len(v) if k == "players" and isinstance(v, list) else n_players(v) for k, v in obj.items())
    if isinstance(obj, list):
        return sum(n_players(v) for v in obj)
    return 0


def task_h(con, ctx) -> dict:
    """Single-game tracking and hustle box scores, newest season first, until the deadline."""
    from nba_api.stats import endpoints as ep

    endpoints = [("box_tracking", ep.BoxScorePlayerTrackV3, 2014), ("box_hustle", ep.BoxScoreHustleV2, 2016)]
    # owner priority 2026-10-18: every season's playoffs (newest first), then 2025-26 and
    # 2024-25 regular season; no other regular seasons
    first = min(e[2] for e in endpoints)
    years = [y for (y,) in con.execute("SELECT DISTINCT season_end_year FROM core.games ORDER BY 1 DESC").fetchall() if y >= first]
    plan = [(y, "playoffs") for y in years] + [(y, "regular") for y in ctx.regular_years]
    fetched = cached = empty = failed = 0
    last_pos, stop, done_parts = None, None, []
    for y, stype in plan:
        games = [g for (g,) in con.execute("""SELECT game_id FROM core.games WHERE season_end_year = ? AND season_type = ?
                                              AND NOT coalesce(pbp_missing, FALSE) ORDER BY game_id""", [y, stype]).fetchall()]
        if ctx.trial:
            games = games[:2]
        for gid in games:
            if datetime.now() >= ctx.deadline:
                stop = f"deadline {ctx.deadline:%H:%M}"
                break
            for cat, cls, first in endpoints:
                if y < first:
                    continue
                before = ctx.nba.requests
                try:
                    data = ctx.nba.get(cat, season_label(y), gid, cls, game_id=gid)
                except NbaStopped:
                    stop = "NBA.com stopped after repeated failures"
                    break
                if data is None:
                    failed += 1
                    continue
                if ctx.nba.requests == before:
                    cached += 1
                else:
                    fetched += 1
                if n_players(data) == 0:
                    empty += 1
            if stop:
                break
            last_pos = f"{season_label(y)} {stype} {gid}"
            if fetched and fetched % 200 == 0:
                progress(f"H at {last_pos} (fetched {fetched})")
        if stop or ctx.trial:
            break
        done_parts.append(f"{season_label(y)} {stype}")
    # load everything cached so far into reference tables (also when H stopped early)
    from nba_platform.reference import boxscores
    loaded = boxscores.load_all(con)
    boxscores.write_report(con, loaded, ROOT / "docs" / "validation" / "boxscore_reference.md")
    status = "incomplete" if stop else "success"
    return {"status": status, "numbers": {"fetched": fetched, "cached": cached, "empty_shells": empty, "failed": failed,
                                          "season_parts_completed": f"{len(done_parts)} of {len(plan)}",
                                          "loaded_games": {t: s["games"] for t, s in loaded.items()},
                                          "last_game": last_pos, "stopped_because": stop or "all games done"}}


# --------------------------------------------------------------------------- runner


class Ctx:
    pass


def write_benchmark_report(con) -> None:
    """Per-season possession benchmark tables (D and G) -> docs/validation/possession_benchmark.md."""
    out = ROOT / "docs" / "validation" / "possession_benchmark.md"
    lines = ["# Possession-count benchmarks (per team-game)", "",
             "Share of team-games by |ramirobentes - reference|. ramirobentes counts are its own possession",
             "columns (reference only, inconsistent across eras - see decisions.md 2026-10-18).", ""]
    specs = (
        ("vs pbpstats (ramirobentes minus possessions starting <= 2 s left with 0 points)",
         "reference.possession_count_benchmark", "abs(diff) = 0", ("abs(diff) = 1", "abs(diff) = 2", "abs(diff) >= 3")),
        ("vs NBA official POSS (all ramirobentes possessions)", "reference.possession_count_benchmark_official",
         "abs(diff) < 0.5", ("abs(diff) >= 0.5 AND abs(diff) < 1.5", "abs(diff) >= 1.5 AND abs(diff) < 2.5", "abs(diff) >= 2.5")),
    )
    for title, table, exact, cuts in specs:
        try:
            rows = con.execute(f"""SELECT season_end_year, season_type, count(*), avg(({exact})::INT),
                                          avg(({cuts[0]})::INT), avg(({cuts[1]})::INT), avg(({cuts[2]})::INT)
                                   FROM {table} GROUP BY 1, 2 ORDER BY 2 DESC, 1""").fetchall()
        except duckdb.Error:
            continue
        lines += [f"## {title}", "", "| season | type | team-games | 0 | 1 | 2 | 3+ |", "|---|---|---|---|---|---|---|"]
        lines += [f"| {season_label(y)} | {st} | {n:,} | {a:.1%} | {b:.1%} | {c:.1%} | {d:.1%} |" for y, st, n, a, b, c, d in rows]
        lines.append("")
    out.write_text(chr(10).join(lines) + chr(10), encoding="utf-8")


def write_summary(path: Path, state: dict, ctx) -> None:
    """At most 10 lines per task; per-season tables live in the validation reports (links)."""
    names = {"A": "reproducibility", "B": "nbastats PBP", "C": "matchups", "D": "possessions vs pbpstats",
             "E": "BigDataBall", "F": "NBA.com season data", "G": "possessions vs NBA official", "H": "single-game boxes"}
    links = {"D": "docs/validation/possession_benchmark.md", "G": "docs/validation/possession_benchmark.md",
             "E": "docs/validation/bigdataball_crosscheck.md"}
    lines = [f"# Overnight batch {ctx.tag}{' (TRIAL)' if ctx.trial else ''}", "",
             f"Run {ctx.started:%Y-%m-%d %H:%M} -> {datetime.now():%H:%M}. NBA.com: {ctx.nba.requests} requests, "
             f"{ctx.nba.cached} cached, {ctx.nba.failures} failures, planned rests {len(ctx.nba.rests)}, cooldowns {len(ctx.nba.cooldowns)} "
             f"({', '.join(ctx.nba.cooldowns) or 'none'}){' - STOPPED' if ctx.nba.stopped else ''}.", ""]
    for k in TASKS:
        s = state.get(k, {"status": "not run"})
        block = [f"## {k} {names[k]} - {s['status']} ({s.get('minutes', '-')} min)"]
        for key, val in list(s.get("numbers", {}).items())[:7]:
            block.append(f"- {key}: {json.dumps(val, default=str, ensure_ascii=False)[:160]}")
        if s.get("error") or s.get("note"):
            block.append(f"- {'error' if s.get('error') else 'note'}: {(s.get('error') or s.get('note'))[:160]}")
        if k in links:
            block.append(f"- details: `{links[k]}`")
        lines += block[:10]
    path.write_text(chr(10).join(lines) + chr(10), encoding="utf-8")


def keep_awake() -> bool:
    """Ask Windows not to sleep while this process runs (reset automatically when it exits).

    Two long runs stalled for about an hour when the laptop went to sleep. Does not change any
    power setting; closing the lid can still suspend the machine. Returns False off Windows.
    """
    if os.name != "nt":
        return False
    import ctypes

    ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
    return bool(ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--trial", action="store_true")
    ap.add_argument("--only", default=TASKS)
    ap.add_argument("--deadline", default="08:00", help="local time to stop task H")
    ap.add_argument("--force", action="store_true", help="re-run tasks already marked done")
    ap.add_argument("--regular-years", default="2026,2025",
                    help="season end years whose regular season task H also fetches, newest first (owner priority 2026-10-18: 2026,2025)")
    ap.add_argument("--tag", default="overnight_2026-10-19", help="name of log / state / summary files")
    ap.add_argument("--seed-state", default="overnight_2026-10-18", help="earlier run whose finished tasks are reused")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    LOGS.mkdir(exist_ok=True)
    suffix = "_trial" if args.trial else ""
    ctx = Ctx()
    ctx.trial, ctx.started, ctx.tag = args.trial, datetime.now(), args.tag
    ctx.regular_years = [int(y) for y in args.regular_years.split(",")]
    ctx.log_path = LOGS / f"{args.tag}{suffix}.log"
    hh, mm = map(int, args.deadline.split(":"))
    dl = datetime.now().replace(hour=hh, minute=mm, second=0, microsecond=0)
    ctx.deadline = dl if dl > datetime.now() else dl + timedelta(days=1)
    ctx.nba = Nba(deadline=ctx.deadline)
    logging.basicConfig(filename=ctx.log_path, level=logging.INFO, encoding="utf-8",
                        format="%(asctime)s %(levelname)s %(message)s")
    state_path, summary_path = LOGS / f"{args.tag}{suffix}_state.json", LOGS / f"{args.tag}{suffix}_summary.md"
    seed = LOGS / f"{args.seed_state}_state.json"
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
    elif seed.exists() and not args.trial:  # reuse tasks finished on an earlier night
        state = {k: v for k, v in json.loads(seed.read_text(encoding="utf-8")).items() if v.get("status") == "success"
                 and k != "G"}  # G is cheap and rebuilds its table (a trial run leaves it partial)
    else:
        state = {}
    progress(f"keep-awake: {keep_awake()}")
    progress(f"start {'TRIAL ' if args.trial else ''}tasks {args.only}; deadline for H {ctx.deadline:%Y-%m-%d %H:%M}")
    con = db.connect()
    funcs = {"A": task_a, "B": task_b, "C": task_c, "D": task_d, "E": task_e, "F": task_f, "G": task_g, "H": task_h}
    try:
        for k in TASKS:
            if k not in args.only:
                continue
            if state.get(k, {}).get("status") == "success" and not args.force and not args.trial:
                progress(f"{k}: already done, skipped")
                state[k]["note"] = "done in an earlier run"
                continue
            progress(f"{k}: start")
            t0 = time.time()
            try:
                res = funcs[k](con, ctx)
            except Exception as exc:
                log.error("task %s failed:\n%s", k, traceback.format_exc())
                res = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
            res["minutes"] = round((time.time() - t0) / 60, 1)
            state[k] = res
            state_path.write_text(json.dumps(state, indent=1, default=str), encoding="utf-8")
            progress(f"{k}: {res['status']} in {res['minutes']} min")
    finally:
        try:
            write_benchmark_report(con)
        except Exception:
            log.error("benchmark report failed: %s", traceback.format_exc())
        con.close()
        write_summary(summary_path, state, ctx)
        progress(f"done; summary {summary_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
