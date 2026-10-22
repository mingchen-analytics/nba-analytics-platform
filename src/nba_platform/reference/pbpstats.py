"""Load shufinskiy pbpstats_* files into reference.pbpstats_possessions.

Reference data for validating possession counts (CLAUDE.md check 8). It is never used
to build our own possessions.

Usage:
    python -m nba_platform.reference.pbpstats
"""

from __future__ import annotations

import sys

import pandas as pd

from nba_platform import db
from nba_platform.ingest.download import RAW_DIR
from nba_platform.staging import shufinskiy as sh

KEY = ["GAMEID", "OPPONENT", "PERIOD", "STARTTIME", "ENDTIME", "STARTTYPE", "STARTSCOREDIFFERENTIAL", "EVENTS"]
NUM = {"FG2A": "fg2a", "FG2M": "fg2m", "FG3A": "fg3a", "FG3M": "fg3m", "OFFENSIVEREBOUNDS": "offensive_rebounds",
       "TURNOVERS": "turnovers", "SHOOTINGFOULSDRAWN": "shooting_fouls_drawn",
       "NONSHOOTINGFOULSTHATRESULTEDINFTS": "nonshooting_fouls_fts"}


def available_files() -> list[tuple[int, str, object]]:
    out = []
    for p in sorted((RAW_DIR / "shufinskiy").glob("pbpstats_*.tar.xz")):
        stem = p.name.removesuffix(".tar.xz")
        season_type = "playoffs" if "_po_" in stem else "regular"
        out.append((int(stem.split("_")[-1]) + 1, season_type, p))  # file = season start year
    return out


def possessions(raw: pd.DataFrame, season_end_year: int, season_type: str) -> pd.DataFrame:
    df = raw.copy()
    df["GAMEID"] = df["GAMEID"].astype(str).str.zfill(10)
    for c in KEY:
        df[c] = df[c].astype("string").fillna("")  # NULL EVENTS (empty possessions) must group too
    g = df.groupby(KEY, sort=False)
    out = g[list(NUM)].first().rename(columns=NUM)
    out["n_event_rows"] = g.size()
    out = out.reset_index()
    secs = out["STARTTIME"].str.split(":", expand=True).astype(float)
    out["_start_secs"] = secs[0] * 60 + secs[1]
    out["_period"] = pd.to_numeric(out["PERIOD"])
    out = out.sort_values(["GAMEID", "_period", "_start_secs"], ascending=[True, True, False], kind="stable")
    out["possession_seq"] = out.groupby("GAMEID").cumcount() + 1
    return pd.DataFrame({
        "season_end_year": season_end_year, "season_type": season_type,
        "game_id": out["GAMEID"], "possession_seq": out["possession_seq"],
        "defense_team_abbr": out["OPPONENT"], "period": out["_period"].astype("int64"),
        "start_time": out["STARTTIME"], "end_time": out["ENDTIME"], "start_type": out["STARTTYPE"],
        "start_score_diff": pd.to_numeric(out["STARTSCOREDIFFERENTIAL"]).astype("int64"),
        "n_event_rows": out["n_event_rows"].astype("int64"),
        **{v: out[v].astype("int64") for v in NUM.values()},
        "source": "shufinskiy_pbpstats",
    })


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    con = db.connect()
    try:
        for y, t, path in available_files():
            p = possessions(sh.read_tar_csv(path, dtype={"GAMEID": str}), y, t)
            con.register("p", p)
            con.execute("BEGIN TRANSACTION")
            con.execute("DELETE FROM reference.pbpstats_possessions WHERE season_end_year = ? AND season_type = ?", [y, t])
            con.execute("INSERT INTO reference.pbpstats_possessions BY NAME SELECT * FROM p")
            con.execute("COMMIT")
            con.unregister("p")
            print(f"{y} {t}: {len(p):,} possessions, {p['game_id'].nunique():,} games", flush=True)
    finally:
        con.close()


if __name__ == "__main__":
    main()


def write_coverage_report(con, path) -> None:
    """Per-season coverage of reference.pbpstats_possessions vs core.games (numbers only)."""
    from nba_platform.seasons import season_label

    rows = con.execute("""
        WITH r AS (SELECT season_end_year, season_type, game_id, count(*) AS poss
                   FROM reference.pbpstats_possessions GROUP BY ALL),
             s AS (SELECT DISTINCT season_end_year, season_type FROM r)
        SELECT s.season_end_year, s.season_type,
               (SELECT count(*) FROM r WHERE r.season_end_year = s.season_end_year AND r.season_type = s.season_type),
               (SELECT sum(poss) FROM r WHERE r.season_end_year = s.season_end_year AND r.season_type = s.season_type),
               (SELECT count(*) FROM core.games g WHERE g.season_end_year = s.season_end_year AND g.season_type = s.season_type),
               (SELECT count(*) FROM r WHERE r.season_end_year = s.season_end_year AND r.season_type = s.season_type
                  AND r.game_id NOT IN (SELECT game_id FROM core.games)),
               (SELECT count(*) FROM core.games g WHERE g.season_end_year = s.season_end_year AND g.season_type = s.season_type
                  AND g.game_id NOT IN (SELECT game_id FROM r)),
               (SELECT list(r.game_id ORDER BY r.game_id) FROM r WHERE r.season_end_year = s.season_end_year
                  AND r.season_type = s.season_type AND r.game_id NOT IN (SELECT game_id FROM core.games))
        FROM s ORDER BY s.season_type <> 'regular', s.season_end_year""").fetchall()
    lines = ["# Reference: pbpstats possessions (shufinskiy `pbpstats_*`)", "",
             "`reference.pbpstats_possessions`: one row per possession as pbpstats counts it. Reference only —",
             "never used to build our possessions. Available 2000-01 → 2024-25 (no file for 1996-97 →",
             "1999-00 or 2025-26). `core games` = our loaded games (0 = season not loaded, see season report).", "",
             "| season | type | pbpstats games | possessions | core games | in pbpstats, not in core | in core, not in pbpstats |",
             "|---|---|---|---|---|---|---|"]
    for y, t, n_ref, poss, n_core, ref_only, core_only, ref_only_ids in rows:
        extra = f" ({', '.join(ref_only_ids[:3])})" if ref_only and n_core else ""
        lines.append(f"| {season_label(y)} | {t} | {n_ref:,} | {int(poss):,} | {n_core:,} | {ref_only:,}{extra} | {core_only:,} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
