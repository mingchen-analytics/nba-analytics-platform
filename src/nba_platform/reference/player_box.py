"""Load the cached official player box scores (nba_api LeagueGameLog) into DuckDB.

Reads data/raw/nba_api/leaguegamelog_P_{season_end_year}_{season_type}.json — read only;
the same files validation check 5 uses for minutes — and rebuilds
reference.nba_player_box: one row per player and game, every counting stat as NBA.com
publishes it (official stat corrections included). This is the box score the dashboard
shows; our own play-by-play version (marts.player_game_pbp) is only compared against it.

Hard fails (the table is not rebuilt): a duplicate (game_id, player_id), or a game_id that
is not in core.games. Players missing from core.players are counted in the report, not
dropped (players who never appear in the play-by-play, e.g. 0-minute rows).

Usage:
    python -m nba_platform.reference.player_box
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

from nba_platform import db
from nba_platform.ingest.nba_api_gamelog import OUT_DIR

FILE_RE = re.compile(r"leaguegamelog_P_(\d{4})_(regular|playoffs)\.json")
# NBA column -> ours. Percentages, fantasy points and display columns are not copied.
COLUMNS = {
    "GAME_ID": "game_id", "PLAYER_ID": "player_id", "TEAM_ID": "team_id", "MIN": "min",
    "FGM": "fgm", "FGA": "fga", "FG3M": "fg3m", "FG3A": "fg3a", "FTM": "ftm", "FTA": "fta",
    "OREB": "oreb", "DREB": "dreb", "REB": "reb", "AST": "ast", "STL": "stl", "BLK": "blk",
    "TOV": "tov", "PF": "pf", "PTS": "pts", "PLUS_MINUS": "plus_minus",
}
STATS = [c for c in COLUMNS.values() if c not in ("game_id", "player_id", "team_id")]


class PlayerBoxError(RuntimeError):
    """The official box score cannot be loaded as is. The rebuild stops."""


def read_gamelog(path: Path) -> pd.DataFrame:
    """One cached LeagueGameLog response -> our column layout (no rows dropped)."""
    m = FILE_RE.fullmatch(path.name)
    if not m:
        raise PlayerBoxError(f"unexpected file name {path.name}")
    rs = json.loads(path.read_text(encoding="utf-8"))["resultSets"][0]
    raw = pd.DataFrame(rs["rowSet"], columns=rs["headers"])
    missing = [c for c in COLUMNS if c not in raw.columns]
    if missing:
        raise PlayerBoxError(f"{path.name}: missing columns {missing}")
    df = raw[list(COLUMNS)].rename(columns=COLUMNS)
    df["game_id"] = df["game_id"].astype(str).str.zfill(10)
    for c in ("player_id", "team_id"):
        df[c] = df[c].astype("int64")
    for c in STATS:
        df[c] = pd.to_numeric(df[c]).astype("Float64")  # NULL stays NULL (e.g. old 3PA)
    df.insert(1, "season_end_year", int(m.group(1)))
    df.insert(2, "season_type", m.group(2))
    return df


def load_all(con, raw_dir: Path = OUT_DIR) -> dict:
    files = sorted(p for p in raw_dir.glob("leaguegamelog_P_*.json") if FILE_RE.fullmatch(p.name))
    if not files:
        raise PlayerBoxError(f"no LeagueGameLog files in {raw_dir}")
    df = pd.concat([read_gamelog(p) for p in files], ignore_index=True)
    dup = df.duplicated(["game_id", "player_id"], keep=False)
    if dup.any():
        raise PlayerBoxError(f"{int(dup.sum())} rows share a (game_id, player_id)")
    con.register("box_df", df)
    try:
        unknown_games = con.execute("""SELECT count(DISTINCT game_id) FROM box_df
                                       WHERE game_id NOT IN (SELECT game_id FROM core.games)""").fetchone()[0]
        if unknown_games:
            raise PlayerBoxError(f"{unknown_games} box-score games are not in core.games")
        unknown_players = con.execute("""SELECT count(DISTINCT player_id) FROM box_df
                                         WHERE player_id NOT IN (SELECT player_id FROM core.players)""").fetchone()[0]
        con.execute("CREATE SCHEMA IF NOT EXISTS reference")
        con.execute("CREATE OR REPLACE TABLE reference.nba_player_box AS SELECT * FROM box_df")
    finally:
        con.unregister("box_df")
    return {"files": len(files), "rows": len(df), "games": int(df["game_id"].nunique()),
            "players_not_in_core_players": int(unknown_players)}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    con = db.connect()
    try:
        print(load_all(con))
    finally:
        con.close()


if __name__ == "__main__":
    main()
