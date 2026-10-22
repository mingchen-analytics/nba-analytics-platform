"""Staging adapter for BigDataBall play-by-play CSVs (purchased, local only).

**Validation only** — never loaded into core tables (CLAUDE.md data sources).

Quirks (CLAUDE.md): `game_id` stored as an Excel formula `="0020400027"`; players by
name only (lineups `a1-a5` away, `h1-h5` home); stray whitespace in text fields.
`play_id` is the NBA event number (checked against ramirobentes `event_num` together with
period and clock before it is used for alignment).

Files: data/raw/bigdataball/{season}/[date]-{game_id}-{AWAY}@{HOME}.csv (one game each)
plus one combined season file, which is not needed (the per-game files carry the same rows).
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd

from nba_platform.ingest.download import RAW_DIR

SOURCE = "bigdataball"
BDB_DIR = RAW_DIR / SOURCE
GAME_FILE_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2})\]-(\d{10})-([A-Z]{2,3})@([A-Z]{2,3})\.csv$")
AWAY_COLS = [f"a{i}" for i in range(1, 6)]
HOME_COLS = [f"h{i}" for i in range(1, 6)]


def normalize_name(name: str) -> str:
    """Accent-, case-, punctuation-insensitive name key used to compare sources."""
    s = unicodedata.normalize("NFKD", str(name))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[.'’`]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def game_files(season_dir: Path) -> dict[str, Path]:
    """game_id -> per-game file. Files whose name does not match are ignored (combined file)."""
    out = {}
    for p in sorted(season_dir.glob("*.csv")):
        m = GAME_FILE_RE.match(p.name)
        if m:
            if m.group(2) in out:
                raise ValueError(f"two BigDataBall files for game {m.group(2)}")
            out[m.group(2)] = p
    return out


def _clock_mmss(remaining: pd.Series) -> pd.Series:
    """'00:11:41' -> '11:41' (ramirobentes clock format for older seasons)."""
    return remaining.astype(str).str.strip().str.replace(r"^00:", "", regex=True)


def read_game(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
    for c in df.columns:
        df[c] = df[c].str.strip()
    df["game_id"] = df["game_id"].str.replace(r'^="?|"$', "", regex=True).str.zfill(10)
    df["play_id"] = pd.to_numeric(df["play_id"]).astype("int64")
    df["period"] = pd.to_numeric(df["period"]).astype("int64")
    df["clock"] = _clock_mmss(df["remaining_time"])
    for c in ("away_score", "home_score"):
        df[c] = pd.to_numeric(df[c])
    df["away_names"] = df[AWAY_COLS].values.tolist()
    df["home_names"] = df[HOME_COLS].values.tolist()
    df["source"] = SOURCE
    return df
