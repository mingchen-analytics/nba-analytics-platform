"""Shot data quality per season (plans 2026-10-17 step 6, 2026-10-18 steps 4 and 7).

Profiles every shufinskiy shotdetail file (all seasons, regular + playoffs): coordinate
gaps, shots at (0, 0), shot-distance and shot-type distributions, and what kind of shot
sits at (0, 0). Flags are stored in their own table `core.shot_quality_flags`
(game_id, source_event_num, flag), so a reload of `core.shots` never removes them.
Flags only — no shot is deleted or changed.

In the NBA shot-chart coordinate system (0, 0) is the **rim**. A shot at (0, 0) is an
at-the-rim attempt whose exact spot was not recorded — imprecise, not missing.
- `rim_location_imprecise`: shot at (0, 0) in a season where more than
  `validation.shot_quality.max_share_xy_zero` of shots are at (0, 0) (seasons in which
  rim attempts were not located precisely);
- `rim_location_suspect`: shot at (0, 0) that cannot be at the rim — a jump shot, a
  3-pointer, or a recorded distance > 0 (any season);
- `early_season_location_suspect`: every shot of the seasons in
  `validation.shot_quality.suspect_season_end_years` (Sports Reference warning).

Writes docs/validation/shot_quality.md.

Usage:
    python -m nba_platform.validate.shot_quality
"""

from __future__ import annotations

import sys

import pandas as pd

from nba_platform import db
from nba_platform.db import PROJECT_ROOT
from nba_platform.rules import load_rules
from nba_platform.seasons import season_label
from nba_platform.staging import shufinskiy as sh

REPORT = PROJECT_ROOT / "docs" / "validation" / "shot_quality.md"
DIST_BINS = [-0.1, 0, 3, 10, 16, 23, 30, 1000]
DIST_LABELS = ["0 ft", "1-3", "4-10", "11-16", "17-23", "24-30", "31+"]
TYPE_GROUPS = {"layup": "layup", "dunk": "dunk", "jump": "jump shot", "hook": "hook", "tip": "tip"}
FLAG_IMPRECISE = "rim_location_imprecise"
FLAG_SUSPECT = "rim_location_suspect"
FLAG_EARLY = "early_season_location_suspect"


def _type_group(action: pd.Series) -> pd.Series:
    a = action.fillna("").str.lower()
    out = pd.Series("other", index=a.index)
    for key, label in reversed(list(TYPE_GROUPS.items())):
        out[a.str.contains(key)] = label
    return out


def profile(s: pd.DataFrame) -> dict:
    n = len(s)
    xy0 = (s["LOC_X"] == 0) & (s["LOC_Y"] == 0)
    groups = _type_group(s["ACTION_TYPE"]).value_counts(normalize=True)
    dist = pd.cut(s["SHOT_DISTANCE"], DIST_BINS, labels=DIST_LABELS).value_counts(normalize=True)
    is_jump = s["ACTION_TYPE"].fillna("").str.contains("Jump", case=False)
    is_layup = s["ACTION_TYPE"].fillna("").str.contains("Layup", case=False)
    z = s[xy0]
    zg = _type_group(z["ACTION_TYPE"]).value_counts(normalize=True)
    return {
        "shots": n,
        "xy_missing": float(s["LOC_X"].isna().mean()) if n else 0.0,
        "xy_zero": float(xy0.mean()) if n else 0.0,
        "n_xy_zero": int(xy0.sum()),
        "xy0_jump": int(z["ACTION_TYPE"].fillna("").str.contains("Jump", case=False).sum()),
        "xy0_3pt": int((z["SHOT_TYPE"] == "3PT Field Goal").sum()),
        "xy0_dist_gt0": int((z["SHOT_DISTANCE"] > 0).sum()),
        "xy0_rim_types": float(zg.get("layup", 0) + zg.get("dunk", 0) + zg.get("tip", 0)) if len(z) else float("nan"),
        "n_action_types": int(s["ACTION_TYPE"].nunique()),
        "layup_far_10ft": float((is_layup & (s["SHOT_DISTANCE"] >= 10)).mean()) if n else 0.0,
        "jump_at_0ft": float((is_jump & (s["SHOT_DISTANCE"] == 0)).mean()) if n else 0.0,
        **{f"type_{k.replace(' ', '_')}": float(groups.get(k, 0.0)) for k in ["layup", "dunk", "jump shot", "hook", "tip", "other"]},
        **{f"dist_{k}": float(dist.get(k, 0.0)) for k in DIST_LABELS},
    }


def profile_all() -> pd.DataFrame:
    rows = []
    for t in ("regular", "playoffs"):
        for y in range(1997, 2027):
            path = sh.raw_path("shotdetail", y, t)
            if path.exists():
                rows.append({"season_end_year": y, "season_type": t, **profile(sh.read_shotdetail(path))})
    return pd.DataFrame(rows)


def write_flags(con, prof: pd.DataFrame, max_xy0: float, suspect_years: set[int]) -> dict[str, int]:
    """Rebuild core.shot_quality_flags for every loaded shot. Returns counts per flag."""
    imprecise = prof.loc[prof["xy_zero"] > max_xy0, ["season_end_year", "season_type"]]
    con.register("imprecise_seasons", imprecise)
    con.register("early_seasons", pd.DataFrame({"season_end_year": sorted(suspect_years)}))
    try:
        con.execute("BEGIN TRANSACTION")
        con.execute("DELETE FROM core.shot_quality_flags")
        con.execute(f"""
            INSERT INTO core.shot_quality_flags
            SELECT s.game_id, s.source_event_num, '{FLAG_IMPRECISE}'
            FROM core.shots s JOIN core.games g USING (game_id)
            JOIN imprecise_seasons i USING (season_end_year, season_type)
            WHERE s.loc_x = 0 AND s.loc_y = 0""")
        con.execute(f"""
            INSERT INTO core.shot_quality_flags
            SELECT game_id, source_event_num, '{FLAG_SUSPECT}' FROM core.shots
            WHERE loc_x = 0 AND loc_y = 0
              AND (action_type ILIKE '%jump%' OR shot_type = '3PT Field Goal' OR distance_ft > 0)""")
        con.execute(f"""
            INSERT INTO core.shot_quality_flags
            SELECT s.game_id, s.source_event_num, '{FLAG_EARLY}'
            FROM core.shots s JOIN core.games g USING (game_id)
            WHERE g.season_end_year IN (SELECT season_end_year FROM early_seasons)""")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.unregister("imprecise_seasons")
        con.unregister("early_seasons")
    return dict(con.execute("SELECT flag, count(*) FROM core.shot_quality_flags GROUP BY 1 ORDER BY 1").fetchall())


def run(con=None, log=print) -> dict[str, int]:
    q = load_rules()["validation"]["shot_quality"]
    max_xy0, suspect = float(q["max_share_xy_zero"]), set(q["suspect_season_end_years"])
    prof = profile_all()
    own = con is None
    con = con or db.connect()
    try:
        flagged = write_flags(con, prof, max_xy0, suspect)
        n_shots = con.execute("SELECT count(*) FROM core.shots").fetchone()[0]
        n_flagged_shots = con.execute(
            "SELECT count(*) FROM (SELECT DISTINCT game_id, source_event_num FROM core.shot_quality_flags)").fetchone()[0]
    finally:
        if own:
            con.close()
    write_report(prof, flagged, n_shots, n_flagged_shots, max_xy0, suspect)
    log(f"shot quality flags: {flagged} ({n_flagged_shots:,} of {n_shots:,} shots flagged)")
    return flagged


def write_report(prof, flagged, n_shots, n_flagged_shots, max_xy0, suspect) -> None:
    prof = prof.copy()
    prof["flag_xy_zero"] = prof["xy_zero"] > max_xy0
    prof["flag_early"] = prof["season_end_year"].isin(suspect)
    pct = lambda v: "—" if pd.isna(v) else f"{v:.1%}"  # noqa: E731
    reg = prof[prof["season_type"] == "regular"]
    lines = [
        "# Shot data quality", "",
        "Source: shufinskiy shotdetail (all seasons, regular season + playoffs). Numbers only.",
        "Flags live in `core.shot_quality_flags` (one row per shot and flag, key `game_id` +",
        "`source_event_num`), separate from `core.shots`, so reloads keep them. **No shot is deleted or changed.**", "",
        "## What (0, 0) means", "",
        "In the NBA shot-chart coordinate system (0, 0) is the **rim**. A shot at (0, 0) is an at-the-rim",
        "attempt whose exact spot was not recorded: the location is **imprecise, not missing**. The data",
        "agrees: in every season 96–100 % of the shots at (0, 0) are layups, dunks or tip-ins, and none has",
        "a recorded distance above 0 (table below). Shots at (0, 0) that cannot be at the rim (jump shots,",
        "3-pointers, distance > 0) are flagged separately as suspect.", "",
        "## Flags", "",
        f"- `{FLAG_IMPRECISE}` — shot at (0, 0) in a season where more than {max_xy0:.0%} of shots are at (0, 0)",
        "  (1996-97 → 2009-10: 22–36 % of shots; from 2010-11 on, rim attempts carry real coordinates).",
        f"- `{FLAG_SUSPECT}` — shot at (0, 0) that is a jump shot, a 3-pointer or has distance > 0 (any season).",
        f"- `{FLAG_EARLY}` — every shot of {', '.join(season_label(y) for y in sorted(suspect))}",
        "  (Sports Reference warns that location and shot-type data of these seasons is unreliable).", "",
        "| flag | shots |", "|---|---|",
        *[f"| `{k}` | {v:,} |" for k, v in flagged.items()],
        f"| shots with at least one flag | {n_flagged_shots:,} of {n_shots:,} |", "",
        "## Shots at (0, 0), regular seasons", "",
        "| season | shots at (0,0) | share of all shots | layup/dunk/tip share | jump shots | 3-pointers | distance > 0 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in reg.itertuples(index=False):
        lines.append(f"| {season_label(r.season_end_year)} | {r.n_xy_zero:,} | {pct(r.xy_zero)} | {pct(r.xy0_rim_types)} | "
                     f"{r.xy0_jump:,} | {r.xy0_3pt:,} | {r.xy0_dist_gt0:,} |")
    lines += ["", "## Regular seasons", "",
              "| season | shots | xy missing | at (0,0) | action types | layup | dunk | jump shot | hook | tip | other | layup ≥10 ft | jump at 0 ft | season flags |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in reg.itertuples(index=False):
        flags = " ".join(f for f, on in [("rim-imprecise", r.flag_xy_zero), ("early", r.flag_early)] if on) or "—"
        lines.append(f"| {season_label(r.season_end_year)} | {r.shots:,} | {pct(r.xy_missing)} | {pct(r.xy_zero)} | "
                     f"{r.n_action_types} | {pct(r.type_layup)} | {pct(r.type_dunk)} | {pct(r.type_jump_shot)} | "
                     f"{pct(r.type_hook)} | {pct(r.type_tip)} | {pct(r.type_other)} | {r.layup_far_10ft:.2%} | "
                     f"{r.jump_at_0ft:.2%} | {flags} |")
    lines += ["", "Shot-distance distribution (regular season):", "",
              "| season | " + " | ".join(DIST_LABELS) + " |", "|---|" + "---|" * len(DIST_LABELS)]
    for r in reg.to_dict("records"):  # labels such as "0 ft" are not attribute names
        lines.append(f"| {season_label(r['season_end_year'])} | " + " | ".join(pct(r[f'dist_{k}']) for k in DIST_LABELS) + " |")
    po = prof[prof["season_type"] == "playoffs"]
    lines += ["", "## Playoffs (summary)", "",
              "| season | shots | at (0,0) | (0,0) jump / 3PT | action types | layup | jump shot | season flags |",
              "|---|---|---|---|---|---|---|---|"]
    for r in po.itertuples(index=False):
        flags = " ".join(f for f, on in [("rim-imprecise", r.flag_xy_zero), ("early", r.flag_early)] if on) or "—"
        lines.append(f"| {season_label(r.season_end_year)} | {r.shots:,} | {pct(r.xy_zero)} | {r.xy0_jump} / {r.xy0_3pt} | "
                     f"{r.n_action_types} | {pct(r.type_layup)} | {pct(r.type_jump_shot)} | {flags} |")
    e = reg[reg["season_end_year"].isin(suspect)]
    later = reg[(reg["season_end_year"] > max(suspect)) & (reg["season_end_year"] <= max(suspect) + 4)]
    lines += ["", "## 1996-97 → 1999-00 (Sports Reference warning)", "",
              f"- Action-type vocabulary: {e['n_action_types'].min()}–{e['n_action_types'].max()} distinct types, vs "
              f"{later['n_action_types'].min()}–{later['n_action_types'].max()} in the next four seasons — shot types are coarse.",
              f"- Layups: {pct(e['type_layup'].min())}–{pct(e['type_layup'].max())} of shots (next four seasons "
              f"{pct(later['type_layup'].min())}–{pct(later['type_layup'].max())}); 1996-97 is the outlier "
              f"({pct(e[e['season_end_year'] == min(suspect)]['type_layup'].iloc[0])}), consistent with jump shots logged as layups (inference).",
              f"- Shots at (0, 0): {pct(e['xy_zero'].min())}–{pct(e['xy_zero'].max())}; 1996-97 also has the most "
              f"non-rim shots at (0, 0) ({int(e[e['season_end_year'] == min(suspect)]['xy0_jump'].iloc[0])} jump shots, "
              f"{int(e[e['season_end_year'] == min(suspect)]['xy0_3pt'].iloc[0])} 3-pointers).",
              "- These seasons are flagged as a whole; analyses of shot location or type should exclude or",
              "  down-weight them. **[待確認]** whether to go further (e.g. drop their coordinates in marts).", ""]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    run()


if __name__ == "__main__":
    main()
