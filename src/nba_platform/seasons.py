"""Season naming helpers shared by every source adapter."""

from __future__ import annotations

SEASON_TYPES = ("regular", "playoffs")


def season_label(season_end_year: int) -> str:
    """2005 -> '2004-05'; 2000 -> '1999-00'."""
    return f"{season_end_year - 1}-{season_end_year % 100:02d}"


def check_season_type(season_type: str) -> str:
    if season_type not in SEASON_TYPES:
        raise ValueError(f"season_type must be one of {SEASON_TYPES}, got {season_type!r}")
    return season_type
