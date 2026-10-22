"""Check the scoring-storage design (plan 2026-10-18, step 6c).

Design under test: possessions keep a single `points` column = the offense's points in that
possession, technical free throws excluded; team totals come from the events table. This
holds only if every scoring event by the team *not* on offense is a technical free throw.

Using ramirobentes' reference possessions (its own `possession` flag; not our logic), list
every scoring event (made FG, made FT) whose team differs from the offense of the
possession it falls in, by event type and FT type.

Writes docs/validation/scoring_attribution.md (codes and counts only).

Usage:
    python -m nba_platform.validate.scoring_attribution --season-end-year 2005 2025
"""

from __future__ import annotations

import argparse
import sys

import duckdb

from nba_platform.db import PROJECT_ROOT
from nba_platform.rules import load_rules
from nba_platform.seasons import season_label
from nba_platform.validate import phase3_prep as prep

REPORT = PROJECT_ROOT / "docs" / "validation" / "scoring_attribution.md"
FT_LABEL = {10: "FT 1 of 1", 11: "FT 1 of 2", 12: "FT 2 of 2", 13: "FT 1 of 3", 14: "FT 2 of 3", 15: "FT 3 of 3",
            16: "technical FT", 17: "clear-path FT", 18: "flagrant FT 1 of 2", 19: "flagrant FT 2 of 2",
            20: "flagrant FT 1 of 1", 21: "technical FT 1 of 2", 22: "technical FT 2 of 2",
            25: "clear-path FT 1 of 2", 26: "clear-path FT 2 of 2", 27: "clear-path FT 1 of 1"}
TECHNICAL = {16, 21, 22}


def mismatches(con) -> list[tuple]:
    """(msg_type, act_type, situation, events, points, example game_id, example event_num).

    situation: `and-1` = a made FG by the same team at the same clock precedes the FT (the
    reference segmentation ends the possession on the FG); `period boundary` = FT at 0:00
    or at a period's starting clock; `other`.
    """
    return con.execute("""
        WITH m AS (
            SELECT e.*,
                   CASE WHEN e.msg_type = 3 AND EXISTS (
                            SELECT 1 FROM rbe f WHERE f.game_id = e.game_id AND f.msg_type = 1 AND f.team_abb = e.team_abb
                              AND f.period = e.period AND f.clock = e.clock AND f.rn < e.rn) THEN 'and-1'
                        WHEN e.clock LIKE '00:00%' OR e.clock LIKE '12:00%' OR (e.period > 4 AND e.clock LIKE '05:00%')
                             THEN 'period boundary'
                        ELSE 'other' END AS situation
            FROM rbe e JOIN rbp4 p ON p.game_id = e.game_id AND p.grp = e.grp
            WHERE e.shot_pts > 0 AND e.msg_type IN (1, 3) AND e.team_abb IS NOT NULL AND e.team_abb <> p.offense
        )
        SELECT msg_type, act_type, situation, count(*) AS n, sum(shot_pts) AS pts,
               min(game_id) AS ex_game, arg_min(event_num, game_id) AS ex_event
        FROM m GROUP BY ALL ORDER BY n DESC""").fetchall()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--season-end-year", type=int, nargs="+", default=[2005, 2025])
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    rules = load_rules()
    lines = ["# Scoring events by the team not on offense (design check, plan 2026-10-18 step 6c)", "",
             "Reference possessions: ramirobentes' own possession flag (not our possession logic).",
             "A row = scoring events whose team differs from the offense of the possession they fall in.", ""]
    verdicts = {}
    for y in args.season_end_year:
        con = duckdb.connect()
        prep.build(con, y, rules)
        rows = mismatches(con)
        n_scoring = con.execute("SELECT count(*) FROM rbe WHERE shot_pts > 0 AND msg_type IN (1, 3)").fetchone()[0]
        con.close()
        non_tech = [r for r in rows if not (r[0] == 3 and r[1] in TECHNICAL)]
        non_tech_other = [r for r in non_tech if r[2] == "other"]
        verdicts[y] = (non_tech, non_tech_other)
        lines += [f"## {season_label(y)} regular season", "",
                  f"Scoring events: {n_scoring:,}; by the team not on offense: {sum(r[3] for r in rows):,} "
                  f"({int(sum(r[4] for r in rows)):,} points).", "",
                  "| event | type | situation | events | points | example game_id / event_num | technical FT? |",
                  "|---|---|---|---|---|---|---|"]
        for msg, act, situation, n, pts, g, ev in rows:
            kind = "made FG" if msg == 1 else "free throw"
            label = FT_LABEL.get(int(act), f"act {int(act)}") if msg == 3 else f"act {int(act)}"
            lines.append(f"| {kind} | {label} | {situation} | {n:,} | {int(pts):,} | {g} / {int(ev)} | "
                         f"{'yes' if msg == 3 and act in TECHNICAL else '**no**'} |")
        lines.append("")
        print(f"{y}: {sum(r[3] for r in rows)} mismatching scoring events; non-technical rows: {len(non_tech)} "
              f"({sum(r[3] for r in non_tech)} events, {sum(r[3] for r in non_tech_other)} 'other')")
    ok = all(not v[0] for v in verdicts.values())
    lines += ["## Verdict", ""]
    if ok:
        lines.append("All scoring events by the team not on offense are technical free throws → the design "
                     "(single `points` per possession, technical FTs excluded, totals from events) holds.")
    else:
        n_and1 = sum(r[3] for v in verdicts.values() for r in v[0] if r[2] == "and-1")
        n_bound = sum(r[3] for v in verdicts.values() for r in v[0] if r[2] == "period boundary")
        n_other = sum(r[3] for v in verdicts.values() for r in v[1])
        lines += [
            "Not every scoring event by the team not on offense is a technical free throw, so by the plan's rule",
            "the design is **not** declared valid here and nothing is changed. **[待確認]**", "",
            f"- **and-1 free throws: {n_and1:,}.** The reference segmentation ends the possession on the made",
            "  field goal, so the and-1 FT lands in the opponent's next possession. Under CLAUDE.md's rule",
            "  (an and-1 possession ends after the free throw) these FTs belong to the shooter's possession —",
            "  a reference artifact, not a counter-example (inference).",
            f"- **Free throws at a period boundary: {n_bound:,}** (clock 0:00 or a period's starting clock): FTs",
            "  from a foul at the buzzer, shot when the reference has already moved to the next possession.",
            f"- **Other: {n_other:,}.** Listed above; to be looked at one by one.",
            "",
            "If the owner's possession code ends and-1 possessions after the FT, only the boundary cases and the",
            "'other' rows remain to be decided."]
    lines.append("")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
