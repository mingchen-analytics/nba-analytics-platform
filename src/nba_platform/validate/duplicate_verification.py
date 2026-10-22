"""Verify duplicated ramirobentes events against the official PBP (plan 2026-10-18, step 1).

A duplicated event is corrected (one copy dropped, reason "source duplicate verified
against official PBP") only if BOTH hold:
  (a) the copies differ only in ramirobentes-derived columns (RB_DERIVED_COLUMNS); every NBA
      original field (event_num, msg/act type, period, clock, description, players,
      lineups, ...) is identical;
  (b) in shufinskiy `nbastats_*` (stats.nba.com play-by-play) the same game has that
      event_num exactly once.
Everything else is listed, not corrected. Report: docs/validation/duplicate_verification.md
(IDs, codes and column names only).

Usage:
    python -m nba_platform.validate.duplicate_verification
"""

from __future__ import annotations

import sys
from datetime import date

import pandas as pd

from nba_platform.db import PROJECT_ROOT
from nba_platform.ingest.download import RAW_DIR
from nba_platform.staging import ramirobentes as rb
from nba_platform.staging import shufinskiy as sh
from nba_platform.staging.corrections_format import CORRECTION_COLUMNS
from nba_platform.validate import duplicates
from nba_platform.validate.conditional_corrections import _append_corrections

REPORT = PROJECT_ROOT / "docs" / "validation" / "duplicate_verification.md"
REASON = "source duplicate verified against official PBP"


def official_count(game_id: str, event_num: int, season_end_year: int, season_type: str) -> int | None:
    """How often (game_id, event_num) appears in the official PBP; None if no file."""
    key = f"nbastats{'_po' if season_type == 'playoffs' else ''}_{season_end_year - 1}"
    path = RAW_DIR / "shufinskiy" / f"{key}.tar.xz"
    if not path.exists():
        return None
    df = sh.read_tar_csv(path, dtype={"GAME_ID": str}, usecols=["GAME_ID", "EVENTNUM"])
    df["GAME_ID"] = df["GAME_ID"].str.zfill(10)
    return int(((df["GAME_ID"] == game_id) & (df["EVENTNUM"] == event_num)).sum())


def verify(scan: pd.DataFrame) -> pd.DataFrame:
    rows = []
    cache: dict[tuple, int | None] = {}
    for r in scan.itertuples(index=False):
        stem = r.file.removesuffix(".parquet").split("_")
        y, t = int(stem[-1]), ("playoffs" if stem[1] == "playoffs" else "regular")
        differing = set(r.differing_columns.split()) if r.differing_columns else set()
        cond_a = bool(differing) and differing <= rb.RB_DERIVED_COLUMNS
        nba_fields_differing = sorted(differing - rb.RB_DERIVED_COLUMNS)
        k = (r.game_id, r.event_num, y, t)
        if k not in cache:
            cache[k] = official_count(r.game_id, r.event_num, y, t)
        n_official = cache[k]
        cond_b = n_official == 1
        rows.append({"file": r.file, "game_id": r.game_id, "event_num": r.event_num, "msg_type": r.msg_type,
                     "act_type": r.act_type, "differing_columns": r.differing_columns,
                     "nba_fields_differing": " ".join(nba_fields_differing) or "—",
                     "cond_a": cond_a, "official_count": n_official, "cond_b": cond_b,
                     "apply": cond_a and cond_b})
    return pd.DataFrame(rows)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    result = verify(duplicates.scan_all())
    ok = result[result["apply"]]
    corr = pd.DataFrame([{"game_id": r.game_id, "source_event_num": int(r.event_num), "field": rb.DROP_DUPLICATE_FIELD,
                          "old_value": "derived_only_duplicate", "new_value": "drop_one", "reason": REASON,
                          "added_on": date.today().isoformat()} for r in ok.itertuples(index=False)],
                        columns=CORRECTION_COLUMNS)
    n_new = _append_corrections(corr) if not corr.empty else 0
    lines = ["# Duplicated source events verified against the official PBP", "",
             f"Run {date.today().isoformat()}. IDs, codes and column names only.", "",
             "(a) copies differ only in ramirobentes-derived columns; (b) the official PBP",
             "(shufinskiy `nbastats_*`) has that game's event number exactly once.", "",
             f"**{len(ok)} of {len(result)}** events meet both conditions → {n_new} new `{REASON}` corrections "
             "(one copy dropped; the copies differ only in derived columns we do not load).", "",
             "| file | game_id | event_num | msg | act | differing columns | NBA fields differing | (a) | official count | (b) | applied |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in result.itertuples(index=False):
        lines.append(f"| {r.file} | {r.game_id} | {r.event_num} | {r.msg_type} | {r.act_type} | {r.differing_columns} | "
                     f"{r.nba_fields_differing} | {'yes' if r.cond_a else 'no'} | "
                     f"{'no file' if r.official_count is None else r.official_count} | {'yes' if r.cond_b else 'no'} | "
                     f"{'**yes**' if r.apply else 'no'} |")
    blocked = result[~result["apply"]]
    lines += ["", f"Not corrected: {len(blocked)}" + (" (listed above with the failing condition)." if len(blocked) else ".")]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
