"""Fetch player-level box score minutes (nba_api LeagueGameLog) for validation check 5.

One request per season x season type, at least REQUEST_GAP_SECS apart. The raw JSON
response is cached in data/raw/nba_api/ and recorded in data/raw/manifest.csv; a cached
file is never fetched again. A request that fails MAX_TRIES times is recorded and skipped.
stats.nba.com blocks most cloud IPs: run this locally.

Usage:
    python -m nba_platform.ingest.nba_api_gamelog            # every season 1996-97 -> 2025-26
    python -m nba_platform.ingest.nba_api_gamelog --season-end-year 2005
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from nba_platform.ingest.download import RAW_DIR, record_in_manifest
from nba_platform.seasons import season_label

OUT_DIR = RAW_DIR / "nba_api"
REQUEST_GAP_SECS = 3.0
MAX_TRIES = 3
SEASON_TYPES = {"regular": "Regular Season", "playoffs": "Playoffs"}
ENDPOINT = "https://stats.nba.com/stats/leaguegamelog"


def cache_path(season_end_year: int, season_type: str) -> Path:
    return OUT_DIR / f"leaguegamelog_P_{season_end_year}_{season_type}.json"


def fetch_one(season_end_year: int, season_type: str) -> dict:
    from nba_api.stats.endpoints import leaguegamelog  # imported lazily: optional dependency

    resp = leaguegamelog.LeagueGameLog(
        season=season_label(season_end_year),
        season_type_all_star=SEASON_TYPES[season_type],
        player_or_team_abbreviation="P",
        timeout=60,
    )
    return resp.get_dict()


def fetch_all(years, season_types=("regular", "playoffs"), log=print) -> list[dict]:
    """Fetch every missing cache file. Returns a list of failures (never raises)."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    failures = []
    last_request = 0.0
    for y in years:
        for t in season_types:
            dest = cache_path(y, t)
            if dest.exists():
                continue
            error = None
            for attempt in range(1, MAX_TRIES + 1):
                wait = REQUEST_GAP_SECS - (time.time() - last_request)
                if wait > 0:
                    time.sleep(wait)
                last_request = time.time()
                try:
                    data = fetch_one(y, t)
                    tmp = dest.with_name(dest.name + ".part")
                    tmp.write_text(json.dumps(data), encoding="utf-8")
                    tmp.rename(dest)
                    url = (f"{ENDPOINT}?Season={season_label(y)}&SeasonType={SEASON_TYPES[t].replace(' ', '+')}"
                           f"&PlayerOrTeam=P (nba_api {_nba_api_version()})")
                    record_in_manifest(dest, url, datetime.now(timezone.utc).isoformat(timespec="seconds"))
                    n = len(data["resultSets"][0]["rowSet"])
                    log(f"fetched {y} {t}: {n:,} player-game rows")
                    error = None
                    break
                except Exception as exc:  # recorded, retried, then skipped
                    error = f"{type(exc).__name__}: {exc}"
                    log(f"attempt {attempt}/{MAX_TRIES} failed for {y} {t}: {error[:200]}")
            if error:
                failures.append({"season_end_year": y, "season_type": t, "error": error[:500]})
    return failures


def _nba_api_version() -> str:
    try:
        from importlib.metadata import version
        return version("nba_api")
    except Exception:
        return "unknown"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--season-end-year", type=int)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    years = [args.season_end_year] if args.season_end_year else range(1997, 2027)
    failures = fetch_all(years)
    print(f"failures: {len(failures)}")
    for f in failures:
        print(f)
    sys.exit(0)


if __name__ == "__main__":
    main()
