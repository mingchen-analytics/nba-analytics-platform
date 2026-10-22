"""Staging adapter for shufinskiy/nba_data files (.tar.xz containing one CSV).

Quirks (CLAUDE.md): file season = START year; GAME_ID loses leading zeros -> zfill(10).
The archive is read as a stream; nothing is extracted into data/raw/.
"""

from __future__ import annotations

import tarfile
from pathlib import Path

import pandas as pd

from nba_platform.ingest.download import RAW_DIR, shufinskiy_key


def raw_path(dataset: str, season_end_year: int, season_type: str) -> Path:
    return RAW_DIR / "shufinskiy" / f"{shufinskiy_key(dataset, season_end_year, season_type)}.tar.xz"


def read_tar_csv(path: Path, **read_csv_kwargs) -> pd.DataFrame:
    """Read the single CSV inside a shufinskiy .tar.xz archive."""
    with tarfile.open(path, "r:xz") as tar:
        members = [m for m in tar.getmembers() if m.isfile() and m.name.endswith(".csv")]
        if len(members) != 1:
            raise ValueError(f"{path.name}: expected exactly 1 CSV, found {[m.name for m in members]}")
        return pd.read_csv(tar.extractfile(members[0]), low_memory=False, **read_csv_kwargs)


def read_shotdetail(path: Path) -> pd.DataFrame:
    """Raw shotdetail rows with GAME_ID restored to 10 characters. Columns unchanged."""
    df = read_tar_csv(path, dtype={"GAME_ID": str})
    df["GAME_ID"] = df["GAME_ID"].str.zfill(10)
    return df


class ShotStagingError(RuntimeError):
    """A shotdetail row could not be mapped. The pipeline must stop."""


SHOT_COLUMNS = [
    "GAME_ID", "GAME_EVENT_ID", "PLAYER_ID", "TEAM_ID", "SHOT_TYPE", "ACTION_TYPE",
    "SHOT_ZONE_BASIC", "SHOT_ZONE_AREA", "SHOT_ZONE_RANGE", "SHOT_DISTANCE", "LOC_X", "LOC_Y",
    "SHOT_MADE_FLAG",
]


def stage_shots(shotdetail: pd.DataFrame) -> pd.DataFrame:
    """shotdetail -> core.shots layout. LOC_X/LOC_Y are tenths of feet from the hoop."""
    missing = [c for c in SHOT_COLUMNS if c not in shotdetail.columns]
    if missing:
        raise ShotStagingError(f"shotdetail missing columns {missing}")
    for col in ("GAME_EVENT_ID", "PLAYER_ID", "TEAM_ID", "SHOT_MADE_FLAG"):
        if shotdetail[col].isna().any():
            raise ShotStagingError(f"shotdetail: {int(shotdetail[col].isna().sum())} NULL {col}")
    if not shotdetail["SHOT_MADE_FLAG"].isin([0, 1]).all():
        raise ShotStagingError("shotdetail: SHOT_MADE_FLAG not in {0, 1}")
    return pd.DataFrame({
        "game_id": shotdetail["GAME_ID"],
        "source_event_num": shotdetail["GAME_EVENT_ID"].astype("int64"),
        "player_id": shotdetail["PLAYER_ID"].astype("int64"),
        "team_id": shotdetail["TEAM_ID"].astype("int64"),
        "shot_type": shotdetail["SHOT_TYPE"],
        "action_type": shotdetail["ACTION_TYPE"],
        "shot_zone_basic": shotdetail["SHOT_ZONE_BASIC"],
        "shot_zone_area": shotdetail["SHOT_ZONE_AREA"],
        "shot_zone_range": shotdetail["SHOT_ZONE_RANGE"],
        "distance_ft": shotdetail["SHOT_DISTANCE"].astype("float64"),
        "loc_x": shotdetail["LOC_X"].astype("float64"),
        "loc_y": shotdetail["LOC_Y"].astype("float64"),
        "made": shotdetail["SHOT_MADE_FLAG"].astype(bool),
        "source": "shufinskiy",
    })
