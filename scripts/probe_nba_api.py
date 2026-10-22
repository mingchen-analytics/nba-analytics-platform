"""Probe NBA.com (nba_api) endpoints once per data class and write
docs/nba_api_endpoint_inventory.md. At most MAX_REQUESTS requests, >= 4 s apart, serial.

Filter support (DateFrom/DateTo, Period) is read from each endpoint's parameters, not
requested. Raw responses are cached in data/raw/nba_api/probe/ and recorded in the manifest.

Usage:
    python scripts/probe_nba_api.py
"""

from __future__ import annotations

import inspect
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from nba_api.stats import endpoints as ep

from nba_platform.db import PROJECT_ROOT
from nba_platform.ingest.download import RAW_DIR, record_in_manifest

OUT = RAW_DIR / "nba_api" / "probe"
DOC = PROJECT_ROOT / "docs" / "nba_api_endpoint_inventory.md"
MAX_REQUESTS = 40
RECENT = "2025-26"
TRACKING = ["SpeedDistance", "Possessions", "Passing", "Drives", "CatchShoot", "PullUpShot", "Rebounding",
            "Defense", "ElbowTouch", "PostTouch", "PaintTouch", "Efficiency"]

n_requests = 0
last = 0.0


def call(label: str, cls, **kw) -> dict:
    """One request (serial, 4-5 s + jitter apart, 30 s timeout); never raises."""
    global n_requests, last
    if n_requests >= MAX_REQUESTS:
        return {"label": label, "ok": False, "error": "request budget reached"}
    wait = 4 + random.random() - (time.time() - last)
    if wait > 0:
        time.sleep(wait)
    last = time.time()
    n_requests += 1
    rec = {"label": label, "endpoint": cls.__name__, "params": kw}
    try:
        data = cls(timeout=30, **kw).get_dict()
        raw = json.dumps(data)
        path = OUT / f"{label}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(raw, encoding="utf-8")
            record_in_manifest(path, f"stats.nba.com {cls.__name__} {kw}", datetime.now(timezone.utc).isoformat(timespec="seconds"))
        sets = data.get("resultSets") or data.get("resultSet") or []
        if isinstance(sets, dict):
            sets = [sets]
        rows = sum(len(s.get("rowSet", [])) for s in sets) if sets else None
        headers = sets[0].get("headers", []) if sets else list(data)[:10]
        if rows is None and "boxScore" in str(list(data)[:3]):
            rows = -1
        rec.update(ok=True, bytes=len(raw), rows=rows, headers=headers)
    except Exception as exc:
        rec.update(ok=False, error=f"{type(exc).__name__}: {str(exc)[:150]}")
    print(f"[{n_requests:2d}] {label}: {'ok' if rec['ok'] else rec['error']} "
          f"{rec.get('bytes', '')} bytes, rows={rec.get('rows')}", flush=True)
    return rec


def filters(cls) -> str:
    params = set(inspect.signature(cls.__init__).parameters)
    has = lambda *names: any(n in params for n in names)  # noqa: E731
    return (f"DateFrom/To: {'yes' if has('date_from_nullable', 'date_from') else 'no'}; "
            f"Period: {'yes' if has('period_nullable', 'period', 'start_period') else 'no'}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    recs = []
    # player tracking: every measure type, recent season
    for m in TRACKING:
        recs.append(call(f"tracking_{m}_{RECENT}", ep.LeagueDashPtStats, season=RECENT,
                         pt_measure_type=m, player_or_team="Player"))
    recs.append(call("tracking_SpeedDistance_2013-14", ep.LeagueDashPtStats, season="2013-14",
                     pt_measure_type="SpeedDistance", player_or_team="Player"))
    recs.append(call("tracking_SpeedDistance_2012-13", ep.LeagueDashPtStats, season="2012-13",
                     pt_measure_type="SpeedDistance", player_or_team="Player"))
    # hustle
    recs.append(call(f"hustle_player_{RECENT}", ep.LeagueHustleStatsPlayer, season=RECENT))
    recs.append(call(f"hustle_team_{RECENT}", ep.LeagueHustleStatsTeam, season=RECENT))
    recs.append(call("hustle_player_2015-16", ep.LeagueHustleStatsPlayer, season="2015-16"))
    recs.append(call("hustle_player_2014-15", ep.LeagueHustleStatsPlayer, season="2014-15"))
    # single-game boxes (a 2025-26 game and old games for the earliest season)
    recs.append(call("box_hustle_0022500001", ep.BoxScoreHustleV2, game_id="0022500001"))
    recs.append(call("box_hustle_0021500001", ep.BoxScoreHustleV2, game_id="0021500001"))
    recs.append(call("box_track_0022500001", ep.BoxScorePlayerTrackV3, game_id="0022500001"))
    recs.append(call("box_track_0021300001", ep.BoxScorePlayerTrackV3, game_id="0021300001"))
    # shot context: one request per context family
    for label, kw in [("close_def", {"close_def_dist_range_nullable": "0-2 Feet - Very Tight"}),
                      ("touch_time", {"touch_time_range_nullable": "Touch < 2 Seconds"}),
                      ("dribbles", {"dribble_range_nullable": "0 Dribbles"}),
                      ("shot_clock", {"shot_clock_range_nullable": "24-22"})]:
        recs.append(call(f"shotctx_{label}_{RECENT}", ep.LeagueDashPlayerPtShot, season=RECENT, **kw))
    recs.append(call("shotctx_close_def_2013-14", ep.LeagueDashPlayerPtShot, season="2013-14",
                     close_def_dist_range_nullable="0-2 Feet - Very Tight"))
    # play types (Synergy)
    for grp in ("offensive", "defensive"):
        recs.append(call(f"playtype_Isolation_{grp}_P_{RECENT}", ep.SynergyPlayTypes, season=RECENT,
                         play_type_nullable="Isolation", type_grouping_nullable=grp,
                         player_or_team_abbreviation="P"))
    recs.append(call(f"playtype_Isolation_offensive_T_{RECENT}", ep.SynergyPlayTypes, season=RECENT,
                     play_type_nullable="Isolation", type_grouping_nullable="offensive",
                     player_or_team_abbreviation="T"))
    recs.append(call("playtype_Isolation_offensive_P_2015-16", ep.SynergyPlayTypes, season="2015-16",
                     play_type_nullable="Isolation", type_grouping_nullable="offensive",
                     player_or_team_abbreviation="P"))
    recs.append(call("playtype_Isolation_offensive_P_2014-15", ep.SynergyPlayTypes, season="2014-15",
                     play_type_nullable="Isolation", type_grouping_nullable="offensive",
                     player_or_team_abbreviation="P"))
    # official possessions per team-game, whole season in one request
    recs.append(call(f"teamgamelogs_advanced_{RECENT}", ep.TeamGameLogs, season_nullable=RECENT,
                     measure_type_player_game_logs_nullable="Advanced"))
    recs.append(call("teamgamelogs_advanced_1996-97", ep.TeamGameLogs, season_nullable="1996-97",
                     measure_type_player_game_logs_nullable="Advanced"))
    (OUT / "_probe_results.json").write_text(json.dumps(recs, indent=1, default=str), encoding="utf-8")
    write_doc(recs)
    print(f"requests used: {n_requests}")


def write_doc(recs: list[dict]) -> None:
    by = {r["label"]: r for r in recs}

    def st(label):
        r = by.get(label, {})
        if not r.get("ok"):
            return f"failed ({r.get('error', 'not run')[:60]})"
        return f"ok, {r['rows']:,} rows, {r['bytes'] / 1024:,.0f} KB" if r.get("rows", -1) >= 0 else f"ok, {r['bytes'] / 1024:,.0f} KB"

    def earliest(old_ok, old_label, older_label, fallback):
        o, oo = by.get(old_label, {}), by.get(older_label, {})
        rows_o = o.get("rows") or 0
        rows_oo = oo.get("rows") or 0
        if o.get("ok") and rows_o > 0 and (not oo.get("ok") or rows_oo == 0):
            return old_ok
        return f"{fallback} (probe: {old_label} → {st(old_label)}; {older_label} → {st(older_label)})"

    poss_cols = [h for h in by.get(f"teamgamelogs_advanced_{RECENT}", {}).get("headers", []) if "POSS" in h.upper()]
    lines = ["# NBA.com (nba_api) endpoint inventory", "",
             f"Probed {datetime.now().strftime('%Y-%m-%d %H:%M')} with nba_api, {n_requests} requests (≥ 4 s apart, serial).",
             "Filter support is read from each endpoint's parameters (nba_api); responses cached in",
             "`data/raw/nba_api/probe/`. Sizes are for one request of the most recent season.", "",
             "| data class | endpoint | key parameters | filters | earliest season | probe result / notes |",
             "|---|---|---|---|---|---|"]
    trk = earliest("2013-14", "tracking_SpeedDistance_2013-14", "tracking_SpeedDistance_2012-13", "2013-14?")
    for m in TRACKING:
        lines.append(f"| player tracking: {m} | LeagueDashPtStats | season, season_type_all_star, pt_measure_type={m}, "
                     f"player_or_team=Player/Team | {filters(ep.LeagueDashPtStats)} | {trk} | {st(f'tracking_{m}_{RECENT}')} |")
    hus = earliest("2015-16", "hustle_player_2015-16", "hustle_player_2014-15", "2015-16?")
    lines += [
        f"| hustle (season) | LeagueHustleStatsPlayer / LeagueHustleStatsTeam | season, season_type_all_star | "
        f"{filters(ep.LeagueHustleStatsPlayer)} | {hus} | player {st(f'hustle_player_{RECENT}')}; team {st(f'hustle_team_{RECENT}')} |",
        f"| hustle (single game) | BoxScoreHustleV2 | game_id | {filters(ep.BoxScoreHustleV2)} | see note | "
        f"2025-26 game {st('box_hustle_0022500001')}; 2015-16 game {st('box_hustle_0021500001')} |",
        f"| tracking box score (single game) | BoxScorePlayerTrackV3 | game_id | {filters(ep.BoxScorePlayerTrackV3)} | see note | "
        f"2025-26 game {st('box_track_0022500001')}; 2013-14 game {st('box_track_0021300001')} |",
    ]
    shot = earliest("2013-14", "shotctx_close_def_2013-14", "shotctx_close_def_2013-14", "2013-14?")
    for fam, par in [("closest defender distance", "close_def_dist_range_nullable"), ("touch time", "touch_time_range_nullable"),
                     ("dribbles", "dribble_range_nullable"), ("shot clock", "shot_clock_range_nullable")]:
        key = {"closest defender distance": "close_def", "touch time": "touch_time", "dribbles": "dribbles", "shot clock": "shot_clock"}[fam]
        lines.append(f"| shot context: {fam} | LeagueDashPlayerPtShot (team: LeagueDashTeamPtShot) | season, {par} (one range per request) | "
                     f"{filters(ep.LeagueDashPlayerPtShot)} | {shot} | {st(f'shotctx_{key}_{RECENT}')} |")
    syn = earliest("2015-16", "playtype_Isolation_offensive_P_2015-16", "playtype_Isolation_offensive_P_2014-15", "2015-16?")
    lines += [
        f"| play type (Synergy) | SynergyPlayTypes | season, play_type_nullable (one of ~11), type_grouping_nullable=offensive/defensive, "
        f"player_or_team_abbreviation=P/T | {filters(ep.SynergyPlayTypes)} | {syn} | offense P {st(f'playtype_Isolation_offensive_P_{RECENT}')}; "
        f"defense P {st(f'playtype_Isolation_defensive_P_{RECENT}')}; offense T {st(f'playtype_Isolation_offensive_T_{RECENT}')} |",
        f"| official possessions per team-game | TeamGameLogs (measure_type=Advanced) | season_nullable, season_type_nullable, "
        f"measure_type_player_game_logs_nullable=Advanced — **whole season in one request** | {filters(ep.TeamGameLogs)} | "
        f"{'1996-97' if (by.get('teamgamelogs_advanced_1996-97', {}).get('rows') or 0) > 0 else 'see probe'} | "
        f"{st(f'teamgamelogs_advanced_{RECENT}')}; 1996-97 {st('teamgamelogs_advanced_1996-97')}; possession columns: "
        f"{', '.join(poss_cols) or 'none found'} |",
        "", "Notes:",
        "- \"earliest season\" for season-level endpoints comes from probing two early seasons; a value with `?`",
        "  means the probe was not conclusive.",
        "- Single-game box scores: availability is per game; the probe tested one modern and one early game.",
        "- Per-period data is available on several endpoints (Period filter) but is not downloaded (owner).",
    ]
    DOC.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
