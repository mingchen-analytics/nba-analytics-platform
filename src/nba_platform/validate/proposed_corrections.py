"""Player keys without an ID ('NA Name') in ramirobentes files -> *proposed* corrections.

Nothing is applied here. ``find_missing_ids`` proposes an ID only when exactly one numeric
ID in the same file has the same name after removing accents and case. The committed
summary (docs/validation/proposed_corrections.csv) holds IDs and positions only, no
source text; ``to_corrections`` turns approved proposals into full corrections.csv rows
(old/new values recomputed from the raw file).

Usage:
    python -m nba_platform.validate.proposed_corrections
"""

from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

import pandas as pd

from nba_platform.db import PROJECT_ROOT
from nba_platform.ingest.download import RAW_DIR
from nba_platform.staging.corrections_format import CORRECTION_COLUMNS

OUT = PROJECT_ROOT / "docs" / "validation" / "proposed_corrections.csv"
PLAYER_COLUMNS = ("player1_name", "player2_name", "player3_name", "player_ft")
LINEUP_COLUMNS = ("lineup_home", "lineup_away")
MATCH_RULE = "unique accent/case-insensitive name match in the same source file"


def normalize(name: str) -> str:
    s = unicodedata.normalize("NFKD", name)
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def _known_ids(df: pd.DataFrame) -> dict[str, set[int]]:
    keys = pd.concat([df[c].dropna() for c in PLAYER_COLUMNS]
                     + [df[c].str.split(", ").explode().dropna() for c in LINEUP_COLUMNS])
    parts = keys.drop_duplicates().str.extract(r"^(\d+) (\S.*)$").dropna()
    out: dict[str, set[int]] = {}
    for pid, name in parts.itertuples(index=False):
        out.setdefault(normalize(name), set()).add(int(pid))
    return out


def find_missing_ids(df: pd.DataFrame, file_name: str) -> list[dict]:
    """One dict per 'NA Name' key: where it is and the proposed ID (None = unresolved)."""
    known = _known_ids(df)
    found = []
    for col in PLAYER_COLUMNS + LINEUP_COLUMNS:
        hits = df[df[col].fillna("").str.contains(r"(?:^|, )NA ", regex=True)]
        for row in hits.itertuples(index=False):
            parts = getattr(row, col).split(", ") if col in LINEUP_COLUMNS else [getattr(row, col)]
            for pos, part in enumerate(parts):
                if part.startswith("NA "):
                    ids = known.get(normalize(part[3:]), set())
                    found.append({
                        "file": file_name, "game_id": row.game_id, "source_event_num": int(row.event_num),
                        "field": col, "lineup_position": pos if col in LINEUP_COLUMNS else None,
                        "missing_name": part[3:],
                        "proposed_player_id": next(iter(ids)) if len(ids) == 1 else None,
                        "n_candidates": len(ids),
                    })
    return found


def to_corrections(df: pd.DataFrame, proposals: list[dict], reason: str, added_on: str) -> pd.DataFrame:
    """Full corrections.csv rows for proposals (one row per (game, event, field))."""
    rows = []
    keyed = pd.DataFrame(proposals)
    for (gid, ev, field), grp in keyed.groupby(["game_id", "source_event_num", "field"]):
        src = df[(df["game_id"] == gid) & (df["event_num"] == ev) & (df["msg_type"] != 99)]
        if len(src) != 1:
            raise ValueError(f"{gid} {ev}: expected 1 source row, found {len(src)}")
        old = src[field].iloc[0]
        parts = old.split(", ") if field in LINEUP_COLUMNS else [old]
        for p in grp.itertuples(index=False):
            pos = int(p.lineup_position) if field in LINEUP_COLUMNS else 0
            if not parts[pos].startswith("NA ") or p.proposed_player_id is None:
                raise ValueError(f"{gid} {ev} {field}[{pos}]: nothing to correct")
            parts[pos] = f"{int(p.proposed_player_id)} {parts[pos][3:]}"
        rows.append({"game_id": gid, "source_event_num": int(ev), "field": field, "old_value": old,
                     "new_value": ", ".join(parts), "reason": reason, "added_on": added_on})
    return pd.DataFrame(rows, columns=CORRECTION_COLUMNS)


def scan_all(raw_dir: Path = RAW_DIR / "ramirobentes") -> pd.DataFrame:
    found = []
    for path in sorted(raw_dir.glob("*.parquet")):
        found += find_missing_ids(pd.read_parquet(path), path.name)
    return pd.DataFrame(found)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    found = scan_all()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cols = ["file", "game_id", "source_event_num", "field", "lineup_position", "proposed_player_id", "n_candidates"]
    out = found[cols] if len(found) else pd.DataFrame(columns=cols)
    out.assign(match_rule=MATCH_RULE).to_csv(OUT, index=False)  # IDs only: no names / source text
    n_unres = int(out["proposed_player_id"].isna().sum()) if len(out) else 0
    print(f"wrote {OUT.relative_to(PROJECT_ROOT)} ({len(out)} keys, {n_unres} unresolved)")


if __name__ == "__main__":
    main()
