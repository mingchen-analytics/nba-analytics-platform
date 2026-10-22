"""Build tests/fixtures/possessions/*.csv: two real 2004-05 event sequences per
possession-rule case (CLAUDE.md "Possession rules"), for the owner's possession tests.

This only *selects* sequences (using the reference queries of validate/phase3_prep.py);
it contains no possession logic. Rows are in the core.events layout plus the on-court
lineups, IDs / codes / numbers only (no description text).

Usage:
    python scripts/build_possession_fixtures.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pandas as pd

from nba_platform.load import staging_dir
from nba_platform.rules import load_rules
from nba_platform.validate import phase3_prep as prep

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "possessions"
CONTEXT = 2  # events before and after the selected window

# case -> (description for the README, SQL returning game_id, rn_from, rn_to; ordered)
CASES = {
    "end_of_period": ("possession starting with <= 2 s left in a period (one 0-point, one scoring)", """
        (SELECT game_id, first_rn, end_rn FROM rbp4 WHERE start_remaining <= 2 AND offense_points = 0
           AND end_msg <> 99 AND end_rn - first_rn BETWEEN 0 AND 3 ORDER BY game_id, end_rn LIMIT 1)
        UNION ALL
        (SELECT game_id, first_rn, end_rn FROM rbp4 WHERE start_remaining <= 2 AND offense_points > 0
           AND end_rn - first_rn BETWEEN 0 AND 3 ORDER BY game_id, end_rn LIMIT 1)"""),
    "substitution_between_free_throws": ("substitution between the first and last FT of a trip (shooting team / defending team)", """
        (SELECT game_id, first_rn, last_rn FROM trip_subs WHERE n_subs_shooting_team > 0 ORDER BY game_id, first_rn LIMIT 1)
        UNION ALL
        (SELECT game_id, first_rn, last_rn FROM trip_subs WHERE n_subs_defending_team > 0 AND n_subs_shooting_team = 0
           ORDER BY game_id, first_rn LIMIT 1)"""),
    "offensive_rebound": ("possession with 2 and with 3 chances (offensive rebounds)", """
        (SELECT game_id, first_rn, end_rn FROM rbp4 WHERE num_chances = 2 AND end_rn - first_rn <= 5 ORDER BY game_id, end_rn LIMIT 1)
        UNION ALL
        (SELECT game_id, first_rn, end_rn FROM rbp4 WHERE num_chances = 3 AND end_rn - first_rn <= 7 ORDER BY game_id, end_rn LIMIT 1)"""),
    "flagrant_foul": ("flagrant foul: FT trip, then the fouled team keeps the ball", """
        SELECT game_id, rn, rn + 4 FROM rbe WHERE msg_type = 6 AND act_type IN (14, 15) ORDER BY game_id, rn LIMIT 2"""),
    "technical_free_throw": ("technical FT shot by the defense / by the offense", """
        (SELECT game_id, rn, rn FROM tech WHERE shooter_side = 'defense' ORDER BY game_id, rn LIMIT 1)
        UNION ALL
        (SELECT game_id, rn, rn FROM tech WHERE shooter_side = 'offense' ORDER BY game_id, rn LIMIT 1)"""),
    "team_rebound_after_non_final_ft": ("team rebound row after a missed non-final FT", """
        SELECT game_id, rn - 1, rn + 1 FROM ft_team_reb ORDER BY game_id, rn LIMIT 2"""),
    "missed_final_free_throw": ("missed final FT followed by an offensive / a defensive rebound", """
        WITH f AS (
            SELECT f.game_id, f.rn, f.team_abb, r.team_abb AS reb_team
            FROM rbe f JOIN rbe r ON r.game_id = f.game_id AND r.rn = f.rn + 1 AND r.msg_type = 4
            WHERE f.msg_type = 3 AND f.act_type IN (10, 12, 15, 19) AND f.shot_pts = 0)
        (SELECT game_id, rn, rn + 1 FROM f WHERE reb_team = team_abb ORDER BY game_id, rn LIMIT 1)
        UNION ALL
        (SELECT game_id, rn, rn + 1 FROM f WHERE reb_team <> team_abb ORDER BY game_id, rn LIMIT 1)"""),
    "jump_ball": ("jump ball that is not an opening tip (possession changes / is kept, approximated)", """
        (SELECT game_id, rn, rn FROM jb WHERE team_next_action IS DISTINCT FROM team_before ORDER BY game_id, rn LIMIT 1)
        UNION ALL
        (SELECT game_id, rn, rn FROM jb WHERE team_next_action = team_before ORDER BY game_id, rn LIMIT 1)"""),
    "start_type": ("possession after a steal / possession after a timeout", """
        (SELECT game_id, first_rn, end_rn FROM rbp4 WHERE start_type_ref = 'after_steal' AND end_rn - first_rn <= 3
           ORDER BY game_id, end_rn LIMIT 1)
        UNION ALL
        (SELECT game_id, first_rn, end_rn FROM rbp4 WHERE is_after_timeout AND end_rn - first_rn <= 4
           ORDER BY game_id, end_rn LIMIT 1)"""),
    "garbage_time": ("start of garbage time (CTG, retroactive) / margin that closes again (not garbage time)", """
        (SELECT game_id, first_rn, end_rn FROM (
            SELECT *, lag(gt_ctg_retro) OVER (PARTITION BY game_id ORDER BY end_rn) AS prev FROM rbp4)
         WHERE gt_ctg_retro AND NOT coalesce(prev, false) ORDER BY game_id, end_rn LIMIT 1)
        UNION ALL
        (SELECT game_id, first_rn, end_rn FROM rbp4 WHERE gt_ctg_each AND NOT gt_ctg_retro ORDER BY game_id, end_rn LIMIT 1)"""),
}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    rules = load_rules()
    con = duckdb.connect()
    prep.build(con, 2005, rules)
    prep.facts(con, 2005, rules)  # creates the helper tables (trips, tech, jb, ...)
    st = staging_dir("ramirobentes", 2005, "regular")
    events = pd.read_parquet(st / "events.parquet").drop(columns=["description", "source_secs_game"], errors="ignore")
    lineups = pd.read_parquet(st / "lineups.parquet")
    ev = events.merge(lineups[["game_id", "event_seq", "home_player_ids", "away_player_ids"]], on=["game_id", "event_seq"])
    ev["home_player_ids"] = ev["home_player_ids"].map(lambda v: "|".join(str(int(x)) for x in v))
    ev["away_player_ids"] = ev["away_player_ids"].map(lambda v: "|".join(str(int(x)) for x in v))
    OUT.mkdir(parents=True, exist_ok=True)
    readme = ["# Possession fixtures (2004-05, real sequences)", "",
              "Built by `scripts/build_possession_fixtures.py`. One CSV per possession-rule case, two",
              "sequences each (`fixture` = A / B), in the `core.events` layout plus on-court lineups",
              "(`home_player_ids` / `away_player_ids`, `|`-separated, as the source gives them: on a",
              "substitution row the source lineup is already post-sub). IDs and codes only.", "",
              "| file | sequences |", "|---|---|"]
    for case, (what, sql) in CASES.items():
        picks = con.execute(sql).fetchall()
        frames = []
        for label, (gid, lo, hi) in zip("AB", picks):
            nums = [r[0] for r in con.execute(
                "SELECT event_num FROM rbe WHERE game_id = ? AND rn BETWEEN ? AND ? AND msg_type <> 99 ORDER BY rn",
                [gid, lo - CONTEXT, hi + CONTEXT]).fetchall()]
            part = ev[(ev["game_id"] == gid) & ev["source_event_num"].isin([int(n) for n in nums])]
            frames.append(part.sort_values("event_seq").assign(fixture=label))
        if len(frames) < 2:
            print(f"WARNING {case}: found {len(frames)} sequence(s)")
        out = pd.concat(frames, ignore_index=True)
        cols = ["fixture"] + [c for c in out.columns if c != "fixture"]
        out[cols].to_csv(OUT / f"{case}.csv", index=False)
        readme.append(f"| `{case}.csv` | {what} |")
        print(f"{case}: {len(frames)} sequences, {len(out)} rows")
    (OUT / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
