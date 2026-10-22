"""Apply corrections only when a strict condition holds (plan 2026-10-17, step 2).

1. Duplicated source events: a `source exact duplicate` correction (drop one copy) is
   written only if the copies are identical in **every** raw column, event_num included.
   Otherwise nothing is corrected and the event is listed.
2. Player keys without an ID ('NA Name'): the proposed IDs are written to
   corrections.csv only if, for **every** affected row, the BigDataBall lineup of the same
   event (play_id = event_num, same period and clock) contains exactly the same five
   players, including the proposed player. Any mismatch blocks the whole game.

Writes corrections/corrections.csv (appends, never duplicates a row) and
docs/validation/conditional_corrections.md (IDs and numbers only).

Usage:
    python -m nba_platform.validate.conditional_corrections
"""

from __future__ import annotations

import sys
from datetime import date

import pandas as pd

from nba_platform.db import PROJECT_ROOT
from nba_platform.ingest.download import RAW_DIR
from nba_platform.seasons import season_label
from nba_platform.staging import bigdataball as bdb
from nba_platform.staging import ramirobentes as rb
from nba_platform.staging.corrections_format import CORRECTION_COLUMNS
from nba_platform.validate import duplicates, proposed_corrections as pc

CORRECTIONS_CSV = PROJECT_ROOT / "corrections" / "corrections.csv"
REPORT = PROJECT_ROOT / "docs" / "validation" / "conditional_corrections.md"


def exact_duplicate_corrections(scan: pd.DataFrame, added_on: str) -> pd.DataFrame:
    ok = scan[scan["all_columns_identical"]]
    return pd.DataFrame([{
        "game_id": r.game_id, "source_event_num": int(r.event_num), "field": rb.DROP_DUPLICATE_FIELD,
        "old_value": "exact_duplicate", "new_value": "drop_one", "reason": "source exact duplicate",
        "added_on": added_on} for r in ok.itertuples(index=False)], columns=CORRECTION_COLUMNS)


def _rb_names(lineup: str, proposed: dict[int, int], id_names: dict[int, str]) -> list[str]:
    """Normalized names of a ramirobentes lineup, NA entries resolved to the proposed ID's name."""
    out = []
    for pos, part in enumerate(lineup.split(", ")):
        if part.startswith("NA "):
            pid = proposed.get(pos)
            out.append(bdb.normalize_name(id_names[pid]) if pid is not None else "?")
        else:
            out.append(bdb.normalize_name(part.split(" ", 1)[1]))
    return out


def verify_with_bigdataball(raw: pd.DataFrame, proposals: pd.DataFrame, bdb_game: pd.DataFrame) -> pd.DataFrame:
    """One row per affected (event, field): does BigDataBall show the same five players?"""
    id_names = {}
    for col in pc.PLAYER_COLUMNS + pc.LINEUP_COLUMNS:
        keys = raw[col].dropna()
        if col in pc.LINEUP_COLUMNS:
            keys = keys.str.split(", ").explode()
        for k in keys.drop_duplicates():
            head, _, name = k.partition(" ")
            if head.isdigit():
                id_names.setdefault(int(head), name)
    rows = []
    for (gid, ev, field), grp in proposals.groupby(["game_id", "source_event_num", "field"]):
        src = raw[(raw["game_id"] == gid) & (raw["event_num"] == ev) & (raw["msg_type"] != rb.SYNTHETIC_MSG_TYPE)]
        b = bdb_game[bdb_game["play_id"] == ev]
        result = {"game_id": gid, "source_event_num": int(ev), "field": field, "bdb_rows": len(b)}
        if len(src) != 1 or len(b) != 1 or grp["proposed_player_id"].isna().any():
            result.update(consistent=False, problem="no unique row in one source or unresolved ID")
            rows.append(result)
            continue
        s, brow = src.iloc[0], b.iloc[0]
        proposed = {int(p.lineup_position): int(p.proposed_player_id) for p in grp.itertuples(index=False)}
        rb_set = set(_rb_names(s[field], proposed, id_names))
        bdb_set = {bdb.normalize_name(n) for n in (brow["home_names"] if field == "lineup_home" else brow["away_names"])}
        same_time = int(s["period"]) == int(brow["period"]) and s["clock"][:5] == brow["clock"][:5]
        problems = []
        if not same_time:
            problems.append("period/clock differ")
        if rb_set != bdb_set:
            problems.append(f"{len(rb_set - bdb_set)} player(s) not in the BigDataBall lineup")
        result.update(consistent=not problems, problem="; ".join(problems))
        rows.append(result)
    return pd.DataFrame(rows)


def _append_corrections(new: pd.DataFrame) -> int:
    current = rb.read_corrections(CORRECTIONS_CSV)
    key = ["game_id", "source_event_num", "field"]
    new = new.astype({"source_event_num": str})
    fresh = new.merge(current[key], on=key, how="left", indicator=True)
    fresh = fresh[fresh["_merge"] == "left_only"].drop(columns="_merge")
    if not fresh.empty:
        pd.concat([current, fresh[CORRECTION_COLUMNS]], ignore_index=True).to_csv(CORRECTIONS_CSV, index=False)
    return len(fresh)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    today = date.today().isoformat()
    lines = ["# Conditional corrections (plan 2026-10-17, step 2)", "",
             f"Run {today}. IDs and numbers only.", ""]

    # 1. duplicated source events
    scan = duplicates.scan_all()
    dup_corr = exact_duplicate_corrections(scan, today)
    n_dup = _append_corrections(dup_corr) if not dup_corr.empty else 0
    lines += ["## 1. Duplicated source events", "",
              f"{len(scan)} duplicated events; {int(scan['all_columns_identical'].sum())} identical in every raw "
              f"column → {n_dup} `source exact duplicate` corrections written.", "",
              "Not corrected (some raw column differs):", "",
              "| file | game_id | event_num | msg | act | differing columns |", "|---|---|---|---|---|---|"]
    for r in scan[~scan["all_columns_identical"]].itertuples(index=False):
        lines.append(f"| {r.file} | {r.game_id} | {r.event_num} | {r.msg_type} | {r.act_type} | {r.differing_columns} |")

    # 2. player keys without an ID, verified against BigDataBall
    lines += ["", "## 2. Player keys without an ID (verified against BigDataBall)", ""]
    found = pc.scan_all()
    for file_name, by_file in (found.groupby("file") if len(found) else []):
        end_year = int(file_name.split("_")[-1].split(".")[0])
        raw = pd.read_parquet(RAW_DIR / "ramirobentes" / file_name)
        files = bdb.game_files(bdb.BDB_DIR / season_label(end_year)) if (bdb.BDB_DIR / season_label(end_year)).exists() else {}
        for gid, props in by_file.groupby("game_id"):
            if gid not in files:
                lines.append(f"- `{gid}` ({file_name}): no BigDataBall file → **not applied**")
                continue
            check = verify_with_bigdataball(raw, props, bdb.read_game(files[gid]))
            n_ok = int(check["consistent"].sum())
            if n_ok == len(check) and len(check) == len(props):
                corr = pc.to_corrections(raw, props.to_dict("records"),
                                         "missing player ID; proposed ID confirmed by BigDataBall lineup at the same event",
                                         today)
                n_new = _append_corrections(corr)
                lines.append(f"- `{gid}` ({file_name}): {n_ok}/{len(check)} rows consistent with BigDataBall → "
                             f"**applied** ({n_new} new correction rows; proposed IDs "
                             f"{sorted(props['proposed_player_id'].dropna().astype(int).unique().tolist())})")
            else:
                lines.append(f"- `{gid}` ({file_name}): {n_ok}/{len(check)} rows consistent → **not applied**")
                lines += ["", "| event_num | field | bdb rows | problem |", "|---|---|---|---|"]
                for r in check[~check["consistent"]].itertuples(index=False):
                    lines.append(f"| {r.source_event_num} | {r.field} | {r.bdb_rows} | {r.problem} |")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
