"""Find NBA events that appear more than once in a ramirobentes file.

For each duplicated (game_id, event_num) it records whether the rows are identical in
**every** column of the raw file (only then may a `source exact duplicate` correction
drop one, plan 2026-10-17) and which columns differ otherwise. The committed summary
holds IDs, codes and column names only (no source text).

Usage:
    python -m nba_platform.validate.duplicates
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from nba_platform.db import PROJECT_ROOT
from nba_platform.ingest.download import RAW_DIR
from nba_platform.staging.ramirobentes import SYNTHETIC_MSG_TYPE

OUT = PROJECT_ROOT / "docs" / "validation" / "duplicate_source_events.csv"


def find_duplicates(df: pd.DataFrame, file_name: str) -> list[dict]:
    real = df[df["msg_type"] != SYNTHETIC_MSG_TYPE]
    dup = real[real.duplicated(["game_id", "event_num"], keep=False)]
    out = []
    for (gid, ev), grp in dup.groupby(["game_id", "event_num"]):
        differing = [c for c in grp.columns if grp[c].astype(str).nunique(dropna=False) > 1]
        out.append({
            "file": file_name, "game_id": gid, "event_num": int(ev), "n_rows": len(grp),
            "msg_type": int(grp["msg_type"].iloc[0]), "act_type": int(grp["act_type"].iloc[0]),
            "all_columns_identical": not differing, "differing_columns": " ".join(differing),
        })
    return out


def scan_all(raw_dir: Path = RAW_DIR / "ramirobentes") -> pd.DataFrame:
    rows = []
    for path in sorted(raw_dir.glob("*.parquet")):
        rows += find_duplicates(pd.read_parquet(path), path.name)
    return pd.DataFrame(rows, columns=["file", "game_id", "event_num", "n_rows", "msg_type", "act_type",
                                       "all_columns_identical", "differing_columns"])


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    out = scan_all()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)
    print(f"wrote {OUT.relative_to(PROJECT_ROOT)}: {len(out)} duplicated events, "
          f"{int(out['all_columns_identical'].sum()) if len(out) else 0} identical in every column")


if __name__ == "__main__":
    main()
