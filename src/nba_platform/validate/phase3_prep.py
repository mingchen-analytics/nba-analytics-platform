"""Phase 3 preparation (overnight plan step 4): facts about one season for each
possession-rule case in CLAUDE.md.

This is NOT our possession logic (the owner writes that in core/). Every possession
number here comes from a reference, and is labelled as such:
- **ramirobentes (source-provided)**: its own `possession` flag (1 on the event that
  ends a possession) and `start_poss` (clock when that possession started). Its
  synthetic msg_type 99 rows are kept here because they carry that flag.
- **pbpstats (reference)**: shufinskiy `pbpstats_*`, one row per event, possession-level
  columns repeated on every row.
Thresholds come from config/rules.yaml.

Usage:
    python -m nba_platform.validate.phase3_prep --season-end-year 2005
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb
import pandas as pd

from nba_platform.db import PROJECT_ROOT
from nba_platform.rules import load_rules
from nba_platform.seasons import season_label
from nba_platform.staging import ramirobentes as rb
from nba_platform.staging import shufinskiy as sh

DOCS = PROJECT_ROOT / "docs"

MULTI_FT_ACT = (11, 12, 13, 14, 15, 18, 19)      # x of 2, x of 3, flagrant x of 2
NON_FINAL_FT_ACT = (11, 13, 14, 18)               # 1 of 2, 1 of 3, 2 of 3, flagrant 1 of 2
TECHNICAL_FT_ACT = (16,)
FLAGRANT_FT_ACT = (18, 19, 20)
FLAGRANT_FOUL_ACT = (14, 15)


def _clock_secs(col: str) -> str:
    return (f"(CAST(split_part({col}, ':', 1) AS DOUBLE) * 60 "
            f"+ CAST(split_part({col}, ':', 2) AS DOUBLE))")


def build(con: duckdb.DuckDBPyConnection, season_end_year: int, rules: dict, season_type: str = "regular") -> None:
    raw = rb.raw_path(season_end_year, season_type).as_posix()
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE rbe AS
        WITH r AS (
            SELECT *, row_number() OVER (PARTITION BY game_id ORDER BY number_event) AS rn
            FROM read_parquet('{raw}')
        )
        SELECT *,
               coalesce(sum(possession) OVER (PARTITION BY game_id ORDER BY rn
                        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 0)::INT AS grp
        FROM r""")

    # One row per ramirobentes possession (source-provided segmentation).
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE rbp AS
        WITH ends AS (
            SELECT game_id, grp, rn AS end_rn, period, team_abb AS offense, team_home, team_away,
                   start_poss, msg_type AS end_msg, act_type AS end_act, player2_name AS end_p2,
                   {_clock_secs('start_poss')} AS start_remaining
            FROM rbe WHERE possession = 1
        ),
        g AS (
            SELECT game_id, grp, min(rn) AS first_rn,
                   min(rn) FILTER (msg_type IN (1, 2, 3, 4, 5, 6, 7, 10)) AS first_action_rn
            FROM rbe GROUP BY ALL
        ),
        pts AS (
            SELECT game_id, grp, team_abb, sum(shot_pts) AS pts, count(*) FILTER (msg_type = 4 AND reb_type = 'off') AS orb
            FROM rbe WHERE team_abb IS NOT NULL GROUP BY ALL
        ),
        tmo AS (
            SELECT e.game_id, e.grp, count(*) AS n_timeouts
            FROM rbe e JOIN g USING (game_id, grp)
            WHERE e.msg_type = 9 AND (g.first_action_rn IS NULL OR e.rn < g.first_action_rn) GROUP BY ALL
        )
        SELECT ends.*,
               g.first_rn,
               coalesce(po.pts, 0) AS offense_points,
               coalesce((SELECT sum(pts) FROM pts p2 WHERE p2.game_id = ends.game_id AND p2.grp = ends.grp
                         AND p2.team_abb <> ends.offense), 0) AS other_team_points,
               1 + coalesce(po.orb, 0) AS num_chances,
               coalesce(tmo.n_timeouts, 0) > 0 AS is_after_timeout,
               prev.hs AS start_hs, prev.vs AS start_vs,
               -- CTG: starters = the game's starters (lineup on the game's first event), counted on court
               -- at the possession start (our computation; the source column is kept for comparison)
               len(list_intersect(list_transform(string_split(first.lineup_home, ', '), s -> TRY_CAST(split_part(s, ' ', 1) AS INTEGER)) || list_transform(string_split(first.lineup_away, ', '), s -> TRY_CAST(split_part(s, ' ', 1) AS INTEGER)), st.starters)) AS starters_combined,
               first.total_starters_home + first.total_starters_away AS starters_combined_source,
               lag(ends.end_msg) OVER w AS prev_end_msg,
               lag(ends.end_p2) OVER w AS prev_end_p2,
               lag(ends.period) OVER w AS prev_period,
               ends.offense = ends.team_home AS offense_is_home
        FROM ends
        JOIN g USING (game_id, grp)
        LEFT JOIN pts po ON po.game_id = ends.game_id AND po.grp = ends.grp AND po.team_abb = ends.offense
        LEFT JOIN tmo USING (game_id, grp)
        LEFT JOIN rbe prev ON prev.game_id = ends.game_id AND prev.rn = g.first_rn - 1
        LEFT JOIN rbe first ON first.game_id = ends.game_id AND first.rn = g.first_rn
        LEFT JOIN (SELECT game_id, list_transform(string_split(lineup_home, ', '), s -> TRY_CAST(split_part(s, ' ', 1) AS INTEGER)) || list_transform(string_split(lineup_away, ', '), s -> TRY_CAST(split_part(s, ' ', 1) AS INTEGER)) AS starters FROM rbe WHERE rn = 1) st ON st.game_id = ends.game_id
        WINDOW w AS (PARTITION BY ends.game_id ORDER BY ends.end_rn)""")
    con.execute("""
        CREATE OR REPLACE TEMP TABLE rbp2 AS
        SELECT *,
               CASE WHEN offense_is_home THEN coalesce(start_hs, 0) - coalesce(start_vs, 0)
                    ELSE coalesce(start_vs, 0) - coalesce(start_hs, 0) END AS start_margin_offense,
               CASE WHEN prev_end_msg IS NULL OR prev_period <> period THEN 'period_start'
                    WHEN prev_end_msg = 1 THEN 'after_made_shot'
                    WHEN prev_end_msg = 2 THEN 'after_defensive_rebound'
                    WHEN prev_end_msg = 3 THEN 'after_free_throw'
                    WHEN prev_end_msg = 5 AND prev_end_p2 IS NOT NULL THEN 'after_steal'
                    WHEN prev_end_msg = 5 THEN 'after_dead_ball_turnover'
                    ELSE 'other (prev end msg ' || prev_end_msg || ')' END AS start_type_ref
        FROM rbp""")

    # Garbage time, Cleaning the Glass definition from rules.yaml (two variants because
    # whether it stays on once triggered is not confirmed).
    gt = rules["garbage_time"]
    conds = " OR ".join(
        f"(start_remaining <= {b['secs_remaining_max']} AND start_remaining "
        f"{'>=' if b['secs_remaining_min'] == 0 else '>'} {b['secs_remaining_min']} "
        f"AND abs(start_margin_offense) >= {b['min_margin']})"
        for b in gt["margin_thresholds"])
    periods = ", ".join(str(p) for p in gt["periods"])
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE rbp3 AS
        SELECT *,
               (period IN ({periods}) AND ({conds})
                AND starters_combined <= {gt['max_combined_starters_on_court']}) AS gt_ctg_each,
        FROM rbp2""")
    con.execute("""
        CREATE OR REPLACE TEMP TABLE rbp4 AS
        -- CTG (owner-confirmed): retroactive -- the condition must hold from this possession
        -- through the end of the game.
        SELECT *, bool_and(gt_ctg_each) OVER (PARTITION BY game_id ORDER BY end_rn
                  ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING) AS gt_ctg_retro
        FROM rbp3""")

    # pbpstats possessions (reference).
    ps = sh.read_tar_csv(sh.raw_path("pbpstats", season_end_year, season_type), dtype={"GAMEID": str})
    ps["GAMEID"] = ps["GAMEID"].str.zfill(10)
    con.register("ps_raw", ps)
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE psp AS
        SELECT GAMEID AS game_id, OPPONENT AS defense, PERIOD AS period, STARTTIME, ENDTIME, STARTTYPE,
               STARTSCOREDIFFERENTIAL, EVENTS, any_value(FG2M) * 2 + any_value(FG3M) * 3 AS fg_points,
               {_clock_secs('STARTTIME')} AS start_remaining
        FROM ps_raw GROUP BY ALL""")


def _md_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_(none)_"
    cols = list(df.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for row in df.itertuples(index=False):
        out.append("| " + " | ".join("" if pd.isna(v) else str(v).replace("|", "/") for v in row) + " |")
    return "\n".join(out)


def _sequence(con, game_id: str, rn_from: int, rn_to: int) -> str:
    df = con.execute("""
        SELECT rn AS seq, event_num, period, clock, team_abb AS team, msg_type AS msg, act_type AS act,
               TRY_CAST(split_part(player1_name, ' ', 1) AS INTEGER) AS player1_id, possession AS rb_poss_end
        FROM rbe WHERE game_id = ? AND rn BETWEEN ? AND ? ORDER BY rn""", [game_id, rn_from, rn_to]).df()
    for c in ("event_num", "msg", "act", "period", "player1_id", "rb_poss_end"):
        df[c] = df[c].astype("Int64")
    return f"Game `{game_id}`:\n\n" + _md_table(df)


def _examples(con, sql: str, before: int = 2, after: int = 2, n: int = 3) -> str:
    rows = con.execute(sql + f" LIMIT {n}").fetchall()
    return "\n\n".join(_sequence(con, g, lo - before, hi + after) for g, lo, hi in rows) or "_(no example)_"


def facts(con, season_end_year: int, rules: dict) -> dict:
    f = {}
    q = lambda s, p=None: con.execute(s, p or []).fetchone()  # noqa: E731

    f["n_rb_poss"] = q("SELECT count(*) FROM rbp4")[0]
    f["n_ps_poss"] = q("SELECT count(*) FROM psp")[0]
    f["n_ps_empty"] = q("SELECT count(*) FROM psp WHERE EVENTS IS NULL")[0]

    # End of period thresholds
    rows = []
    for t in rules["analysis"]["end_of_period_thresholds_to_compare"]:
        n, n0, pts, n99 = q(f"""SELECT count(*), count(*) FILTER (offense_points = 0), sum(offense_points),
                                       count(*) FILTER (end_msg = 99)
                                FROM rbp4 WHERE start_remaining <= {t}""")
        psn, psn0 = q(f"SELECT count(*), count(*) FILTER (fg_points = 0) FROM psp WHERE start_remaining <= {t}")
        rows.append({"threshold_s": t, "rb_poss_starting_le_t": n, "rb_excluded_(0_pts)": n0,
                     "rb_excluded_share_of_all": f"{n0 / f['n_rb_poss']:.3%}", "rb_points_in_them": int(pts or 0),
                     "rb_ended_by_synthetic_msg99": n99,
                     "pbpstats_poss_starting_le_t": psn, "pbpstats_0_fg_pts": psn0})
    f["eop"] = pd.DataFrame(rows)
    tmax = max(rules["analysis"]["end_of_period_thresholds_to_compare"])
    f["eop_by_second"] = con.execute(f"""
        WITH r AS (SELECT start_remaining AS secs_left, count(*) AS rb_poss,
                          count(*) FILTER (end_msg = 99) AS rb_ended_by_msg99,
                          count(*) FILTER (offense_points = 0) AS rb_0_pts
                   FROM rbp4 WHERE start_remaining <= {tmax} GROUP BY 1),
             p AS (SELECT start_remaining AS secs_left, count(*) AS pbpstats_poss
                   FROM psp WHERE start_remaining <= {tmax} GROUP BY 1)
        SELECT secs_left, coalesce(rb_poss, 0) AS rb_poss, coalesce(rb_ended_by_msg99, 0) AS rb_ended_by_msg99,
               coalesce(rb_0_pts, 0) AS rb_0_pts, coalesce(pbpstats_poss, 0) AS pbpstats_poss
        FROM r FULL JOIN p USING (secs_left) ORDER BY secs_left""").df()
    t0 = rules["end_of_period"]["end_of_period_threshold_secs"]
    f["eop_examples"] = _examples(con, f"""
        SELECT game_id, first_rn, end_rn FROM rbp4 WHERE start_remaining <= {t0} AND end_rn - first_rn BETWEEN 0 AND 4
        ORDER BY game_id, end_rn""", before=1, after=1)

    # Free-throw trips and substitutions between free throws
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE trips AS
        SELECT game_id, period, clock, player1_name AS shooter, team_abb AS shooting_team,
               min(rn) AS first_rn, max(rn) AS last_rn, count(*) AS n_ft,
               bool_or(act_type IN {FLAGRANT_FT_ACT}) AS flagrant
        FROM rbe WHERE msg_type = 3 AND act_type IN {MULTI_FT_ACT} GROUP BY ALL""")
    con.execute("""
        CREATE OR REPLACE TEMP TABLE trip_subs AS
        SELECT t.*, count(s.rn) AS n_subs,
               count(s.rn) FILTER (s.team_abb = t.shooting_team) AS n_subs_shooting_team,
               count(s.rn) FILTER (s.team_abb <> t.shooting_team) AS n_subs_defending_team
        FROM trips t LEFT JOIN rbe s ON s.game_id = t.game_id AND s.msg_type = 8 AND s.rn > t.first_rn AND s.rn < t.last_rn
        GROUP BY ALL""")
    f["trips"] = q("SELECT count(*), count(*) FILTER (n_subs > 0), count(*) FILTER (n_subs_shooting_team > 0), "
                   "count(*) FILTER (n_subs_defending_team > 0), sum(n_subs), count(*) FILTER (n_ft <> 2 AND n_ft <> 3) "
                   "FROM trip_subs")
    f["trip_sub_examples"] = _examples(con, """
        SELECT game_id, first_rn, last_rn FROM trip_subs WHERE n_subs > 0 ORDER BY game_id, first_rn""", before=1, after=1)
    # Substitution between the foul and the first FT (relevant to option B)
    f["foul_to_ft_subs"] = q("""
        WITH t AS (
            SELECT t.*, (SELECT max(f.rn) FROM rbe f WHERE f.game_id = t.game_id AND f.msg_type = 6
                         AND f.rn < t.first_rn AND f.clock = t.clock AND f.period = t.period) AS foul_rn
            FROM trips t
        )
        SELECT count(*) FILTER (foul_rn IS NOT NULL),
               count(*) FILTER (foul_rn IS NOT NULL AND EXISTS (
                   SELECT 1 FROM rbe s WHERE s.game_id = t.game_id AND s.msg_type = 8 AND s.rn > t.foul_rn AND s.rn < t.first_rn))
        FROM t""")
    f["n_ft_rows"] = q("SELECT count(*) FROM rbe WHERE msg_type = 3")[0]

    # Offensive rebounds / chances
    f["orb"] = q("SELECT count(*) FILTER (reb_type = 'off'), count(*) FILTER (reb_type = 'def'), "
                 "count(*) FILTER (reb_type IS NULL) FROM rbe WHERE msg_type = 4")
    f["chances"] = con.execute("""
        SELECT CASE WHEN num_chances >= 4 THEN '4+' ELSE num_chances::TEXT END AS chances,
               count(*) AS possessions, round(100.0 * count(*) / sum(count(*)) OVER (), 2) AS pct
        FROM rbp4 GROUP BY 1 ORDER BY 1""").df()
    f["orb_examples"] = _examples(con, """
        SELECT game_id, first_rn, end_rn FROM rbp4 WHERE num_chances >= 3 AND end_rn - first_rn <= 6
        ORDER BY game_id, end_rn""", before=0, after=0)

    # Flagrant fouls
    f["flagrant"] = q(f"""SELECT count(*) FILTER (msg_type = 6 AND act_type IN {FLAGRANT_FOUL_ACT}),
                                 count(*) FILTER (msg_type = 3 AND act_type IN {FLAGRANT_FT_ACT}),
                                 count(*) FILTER (msg_type = 3 AND act_type IN {FLAGRANT_FT_ACT} AND shot_pts = 1)
                          FROM rbe""")
    f["flagrant_examples"] = _examples(con, f"""
        SELECT game_id, rn, rn FROM rbe WHERE msg_type = 6 AND act_type IN {FLAGRANT_FOUL_ACT} ORDER BY game_id, rn""",
        before=1, after=5)

    # Technical free throws
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE tech AS
        SELECT e.*, p.offense,
               CASE WHEN p.offense IS NULL THEN 'unknown' WHEN e.team_abb = p.offense THEN 'offense' ELSE 'defense' END AS shooter_side
        FROM rbe e LEFT JOIN rbp4 p ON p.game_id = e.game_id AND p.grp = e.grp
        WHERE e.msg_type = 3 AND e.act_type IN {TECHNICAL_FT_ACT}""")
    f["tech"] = q("SELECT count(*), count(*) FILTER (shot_pts = 1), count(*) FILTER (shooter_side = 'offense'), "
                  "count(*) FILTER (shooter_side = 'defense'), count(*) FILTER (shooter_side = 'unknown'), "
                  "count(*) FILTER (possession = 1) FROM tech")
    f["tech_examples"] = _examples(con, "SELECT game_id, rn, rn FROM tech WHERE shooter_side = 'defense' ORDER BY game_id, rn",
                                   before=2, after=2)

    # Team rebound after a non-final missed FT
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE ft_team_reb AS
        SELECT r.game_id, r.rn, r.reb_type
        FROM rbe r JOIN rbe f ON f.game_id = r.game_id AND f.rn = r.rn - 1
        WHERE r.msg_type = 4 AND r.player1_name IS NULL
          AND f.msg_type = 3 AND f.act_type IN {NON_FINAL_FT_ACT} AND f.shot_pts = 0""")
    f["ft_team_reb"] = q("SELECT count(*), count(*) FILTER (reb_type IS NULL) FROM ft_team_reb")
    f["n_team_reb"] = q("SELECT count(*) FROM rbe WHERE msg_type = 4 AND player1_name IS NULL")[0]
    f["ft_team_reb_examples"] = _examples(con, "SELECT game_id, rn, rn FROM ft_team_reb ORDER BY game_id, rn",
                                          before=2, after=1)

    # Jump balls that are not the opening tip of a period
    con.execute("""
        CREATE OR REPLACE TEMP TABLE jb AS
        SELECT j.game_id, j.rn, j.team_abb AS jb_team,
               (SELECT p.team_abb FROM rbe p WHERE p.game_id = j.game_id AND p.rn < j.rn
                  AND p.msg_type IN (1, 2, 3, 4, 5) ORDER BY p.rn DESC LIMIT 1) AS team_before,
               (SELECT n.team_abb FROM rbe n WHERE n.game_id = j.game_id AND n.rn > j.rn
                  AND n.msg_type IN (1, 2, 3, 5) ORDER BY n.rn LIMIT 1) AS team_next_action
        FROM rbe j JOIN rbe prev ON prev.game_id = j.game_id AND prev.rn = j.rn - 1
        WHERE j.msg_type = 10 AND prev.msg_type <> 12""")
    f["jb"] = q("SELECT (SELECT count(*) FROM rbe WHERE msg_type = 10), count(*), "
                "count(*) FILTER (team_next_action IS DISTINCT FROM team_before) FROM jb")
    f["jb_examples"] = _examples(con, "SELECT game_id, rn, rn FROM jb ORDER BY game_id, rn", before=2, after=2)

    # Substitutions anywhere inside a possession (after its first action, before its end)
    f["poss_with_sub"] = q("""
        WITH s AS (
            SELECT p.game_id, p.grp, count(e.rn) AS n_subs
            FROM rbp4 p
            JOIN (SELECT game_id, grp, min(rn) FILTER (msg_type IN (1, 2, 3, 4, 5, 6, 7, 10)) AS first_action_rn
                  FROM rbe GROUP BY ALL) fa USING (game_id, grp)
            LEFT JOIN rbe e ON e.game_id = p.game_id AND e.grp = p.grp AND e.msg_type = 8
                 AND e.rn > fa.first_action_rn AND e.rn < p.end_rn
            GROUP BY ALL
        )
        SELECT count(*) FILTER (n_subs > 0), count(*) FROM s""")

    # Start types (reference) and timeouts
    f["start_type_examples"] = _examples(con, """
        SELECT game_id, first_rn, end_rn FROM (
            SELECT *, row_number() OVER (PARTITION BY start_type_ref ORDER BY game_id, end_rn) AS k
            FROM rbp4 WHERE start_type_ref IN ('after_steal', 'after_dead_ball_turnover') OR is_after_timeout
        ) WHERE k = 1 AND end_rn - first_rn <= 5 ORDER BY game_id, end_rn""", before=2, after=0)
    f["start_types_rb"] = con.execute("""
        SELECT start_type_ref AS start_type, count(*) AS possessions,
               round(100.0 * count(*) / sum(count(*)) OVER (), 2) AS pct,
               count(*) FILTER (is_after_timeout) AS after_timeout
        FROM rbp4 GROUP BY 1 ORDER BY 2 DESC""").df()
    f["start_types_ps"] = con.execute("""
        SELECT STARTTYPE AS pbpstats_start_type, count(*) AS possessions,
               round(100.0 * count(*) / sum(count(*)) OVER (), 2) AS pct
        FROM psp GROUP BY 1 ORDER BY 2 DESC""").df()

    # Garbage time
    f["gt"] = q("SELECT count(*) FILTER (gt_ctg_each), count(*) FILTER (gt_ctg_retro), count(*) FROM rbp4")
    f["starters_agree"] = q("SELECT count(*) FILTER (starters_combined = starters_combined_source), count(*) FROM rbp4")
    f["gt_rb_flag_events"] = q("SELECT count(*) FILTER (garbage_time = 1), count(*) FROM rbe")
    f["gt_examples"] = _examples(con, """
        SELECT game_id, first_rn, end_rn FROM rbp4 WHERE gt_ctg_retro AND end_rn - first_rn <= 3
        ORDER BY game_id, end_rn""", before=0, after=0, n=2)

    # Possession counts per game: ramirobentes (poss_home / poss_away) vs pbpstats
    per_game = con.execute("""
        WITH r AS (
            SELECT game_id, any_value(team_home) AS home, any_value(team_away) AS away,
                   sum(poss_home)::INT AS rb_home, sum(poss_away)::INT AS rb_away
            FROM rbe GROUP BY 1
        ),
        p AS (
            SELECT p.game_id,
                   count(*) FILTER (p.defense = r.away) AS ps_home,
                   count(*) FILTER (p.defense = r.home) AS ps_away,
                   count(*) FILTER (p.defense NOT IN (r.home, r.away)) AS ps_unmatched
            FROM psp p JOIN r USING (game_id) GROUP BY 1
        )
        SELECT r.game_id, r.home, r.away, r.rb_home, r.rb_away,
               coalesce(p.ps_home, 0) AS ps_home, coalesce(p.ps_away, 0) AS ps_away,
               r.rb_home - coalesce(p.ps_home, 0) AS diff_home, r.rb_away - coalesce(p.ps_away, 0) AS diff_away,
               coalesce(p.ps_unmatched, 0) AS ps_unmatched
        FROM r LEFT JOIN p USING (game_id) ORDER BY r.game_id""").df()
    f["per_game"] = per_game
    return f


def _bucket_table(per_game: pd.DataFrame) -> pd.DataFrame:
    d = pd.concat([per_game["diff_home"], per_game["diff_away"]]).abs()
    labels = {0: "0", 1: "1", 2: "2"}
    b = d.map(lambda v: labels.get(v, "3-5" if v <= 5 else ">5"))
    out = b.value_counts().reindex(["0", "1", "2", "3-5", ">5"], fill_value=0).rename_axis("abs_diff").reset_index(name="team_games")
    out["pct"] = (100 * out["team_games"] / len(d)).round(2)
    return out


def write(f: dict, season_end_year: int, rules: dict) -> list[Path]:
    label = season_label(season_end_year)
    pg = f["per_game"]
    csv_path = DOCS / "validation" / f"possession_counts_{label}.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    pg.to_csv(csv_path, index=False)

    trips, n_trip_sub, n_trip_sub_shoot, n_trip_sub_def, n_subs, n_odd = f["trips"]
    foul_trips, foul_trips_sub = f["foul_to_ft_subs"]
    orb, drb, reb_null = f["orb"]
    fl_fouls, fl_fts, fl_made = f["flagrant"]
    tech_n, tech_made, tech_off, tech_def, tech_unk, tech_poss_end = f["tech"]
    ftr_n, ftr_null = f["ft_team_reb"]
    jb_all, jb_mid, jb_change = f["jb"]
    gt_each, gt_retro, gt_all = f["gt"]
    gt_ev, n_ev = f["gt_rb_flag_events"]
    within_rb = (pg["rb_home"] - pg["rb_away"]).abs()
    within_ps = (pg["ps_home"] - pg["ps_away"]).abs()
    total_rb = int(pg["rb_home"].sum() + pg["rb_away"].sum())
    total_ps = int(pg["ps_home"].sum() + pg["ps_away"].sum())
    worst = pg.assign(abs_max=pg[["diff_home", "diff_away"]].abs().max(axis=1)).sort_values(
        ["abs_max", "game_id"], ascending=[False, True]).head(10).drop(columns="abs_max")
    t0 = rules["end_of_period"]["end_of_period_threshold_secs"]
    pct = lambda a, b: f"{a / b:.2%}" if b else "n/a"  # noqa: E731

    md = f"""# Possession rules — draft with {label} facts

> **Draft for the owner.** Rules and their status are copied from CLAUDE.md
> ("Possession rules"); nothing here changes a rule or decides an open one.
> The overnight plan asked to keep every rule "proposed"; after the owner's decisions
> of 2026-10-16 the statuses below follow CLAUDE.md instead (decided stays decided,
> open stays open, proposed stays proposed). **[待確認]**

Generated by `python -m nba_platform.validate.phase3_prep --season-end-year {season_end_year}`
(rules_version `{rules['rules_version']}`).

## What the numbers are (observed fact vs source value vs assumption)

- **Observed facts**: counts of rows in the raw files (event types, FT codes, subs,
  rebounds, jump balls).
- **Source-provided values**: every *possession* count below uses either
  ramirobentes' own possession columns (`possession` = 1 on the event that ends a
  possession, `start_poss` = clock at its start; its synthetic msg 99 rows are what end
  the last possession of a quarter) or shufinskiy pbpstats possessions. **None of it is
  our possession logic**, which the owner writes in `core/`.
- **Assumptions** (marked where used): Cleaning the Glass garbage-time thresholds
  (from rules.yaml, themselves [待確認]); "start type" derived from how the *previous*
  ramirobentes possession ended; "possession changed on a jump ball" approximated by the
  team of the next shot/FT/turnover.

Season totals: ramirobentes **{f['n_rb_poss']:,}** possessions; pbpstats **{f['n_ps_poss']:,}**
(of which {f['n_ps_empty']:,} with no events listed). Difference {f['n_rb_poss'] - f['n_ps_poss']:+,}
({pct(f['n_rb_poss'] - f['n_ps_poss'], f['n_ps_poss'])}).

Event sequences below show IDs and codes only (no source text): `seq` = row order in the
game, `event_num` = NBA event number, `msg` = NBA message type (1 made FG, 2 missed FG,
3 free throw, 4 rebound, 5 turnover, 6 foul, 7 violation, 8 substitution, 9 timeout,
10 jump ball, 12/13 period start/end, 99 = ramirobentes synthetic row), `act` = NBA
action code (FT: 10 = 1 of 1, 11/12 = 1/2 of 2, 13-15 = x of 3, 16 technical,
18/19 flagrant 1/2 of 2; foul: 14/15 flagrant), `rb_poss_end` = ramirobentes possession flag.

## Rule table (from CLAUDE.md)

A possession **ends** on: made FG (if and-1, after the FT), defensive rebound (incl. team
rebound), turnover, **made** final FT of a trip, end of period. A **missed** final FT does
not end it by itself: the rebound decides. An offensive rebound does not end a possession.

| Case | Rule (short) | Status | {label} count |
|---|---|---|---|
| End-of-period possessions | start ≤ `end_of_period_threshold_secs` ({t0}) left and 0 pts → excluded from efficiency, kept + flagged | decided | {int(f['eop'].iloc[0]['rb_excluded_(0_pts)']) if not f['eop'].empty else 'n/a'} of {f['n_rb_poss']:,} excluded at {t0} s (ramirobentes) |
| Substitution during a possession (incl. between FTs) | pbpstats hybrid: possession to the lineup at its end, free-throw points to the lineup at the foul; A and C stay computable | decided (owner 2026-10-22) | {n_trip_sub:,} of {trips:,} multi-FT trips ({pct(n_trip_sub, trips)}) |
| Offensive rebound | does not end possession; record `num_chances` | decided | {orb:,} offensive rebounds |
| Flagrant foul | FT trip + retained possession = 2 possessions | decided | {fl_fouls:,} flagrant fouls, {fl_fts:,} flagrant FTs |
| Technical free throws | no start/end; team points; `is_technical_ft`; excluded from lineup efficiency / RAPM | decided | {tech_n:,} technical FTs ({tech_made:,} made) |
| Team rebound after a non-final missed FT | not a rebound; ignore | proposed | {ftr_n:,} rows |
| Jump ball / held ball | possession changes only if the other team gains control | proposed | {jb_mid:,} non-opening jump balls |
| Possession start type | 6 fine-grained types + `is_after_timeout` | decided | see table below |
| Garbage time | flag `is_garbage_time` (CTG definition); exclusion decided at RAPM time | decided (as flag) | **{pct(gt_retro, gt_all)}** of possessions (CTG retroactive definition) |

---

## 1. End-of-period possessions

Possession start = ramirobentes `start_poss` (seconds left in the period). "Excluded" =
starts with ≤ T seconds left **and** the offense scores 0 points (pbpstats approach,
CLAUDE.md). pbpstats columns: possessions starting with ≤ T seconds left, and how many of
them have 0 *field-goal* points (pbpstats rows carry no free-throw makes, so this is an
upper bound on its exclusions).

{_md_table(f['eop'])}

**Finding: the pbpstats file appears to have already dropped most 0–2 s possessions.**
By second left in the period:

{_md_table(f['eop_by_second'])}

From 3 s up the two references agree exactly on how many possessions start at each
second; at 0–2 s ramirobentes has far more. ramirobentes' 0-point possessions starting
with ≤ 2 s left ({int(f['eop'].iloc[0]['rb_excluded_(0_pts)']) if not f['eop'].empty else 'n/a'}) are close to the season-total
difference between the two sources ({f['n_rb_poss'] - f['n_ps_poss']:+,}). **pbpstats removes possessions
that start with ≤ 2 s left and score 0 points before publishing** (owner, 2026-10-18) — the same
rule and threshold as our default. So pbpstats counts must be compared with **our counts after
that exclusion**, not before; the 3 s and 5 s rows show what a higher threshold would add.

Examples (≤ {t0} s left at the start):

{f['eop_examples']}

## 2. Substitution during a possession — especially between free throws (open)

Multi-FT trips = consecutive FTs by the same shooter at the same clock with codes
"1 of 2 … 3 of 3" and flagrant "1 of 2 / 2 of 2" (technical, 1-of-1 and clear-path FTs
are single shots and are not trips).

| Measure | Count | Share |
|---|---|---|
| All FT rows | {f['n_ft_rows']:,} | |
| Multi-FT trips | {trips:,} | |
| Trips with ≥ 1 substitution **between the first and last FT** | **{n_trip_sub:,}** | **{pct(n_trip_sub, trips)}** |
| … by the shooting team | {n_trip_sub_shoot:,} | {pct(n_trip_sub_shoot, trips)} |
| … by the defending team | {n_trip_sub_def:,} | {pct(n_trip_sub_def, trips)} |
| Substitution rows inside trips | {n_subs:,} | |
| Trips with an unexpected number of FTs (not 2 or 3) | {n_odd:,} | |
| Trips with a foul at the same clock found | {foul_trips:,} | |
| … with ≥ 1 substitution **between the foul and the first FT** | {foul_trips_sub:,} | {pct(foul_trips_sub, foul_trips)} |

Substitutions anywhere inside a possession (after its first action and before the event
that ends it, ramirobentes segmentation): **{f['poss_with_sub'][0]:,}** of
{f['poss_with_sub'][1]:,} possessions ({pct(f['poss_with_sub'][0], f['poss_with_sub'][1])}) — these
are the possessions that span more than one stint (`possession_stint_segments`).

Why it matters: under option (A) the FT points go to the lineup on court when the
possession ends (after the last FT); under (B) to the lineup on court at the foul; under
(C) the possession is split into chances. The rows above are where A and B differ.

Examples:

{f['trip_sub_examples']}

## 3. Offensive rebounds and chances

ramirobentes `reb_type`: offensive {orb:,}, defensive {drb:,}, missing {reb_null:,}
(missing = mostly team rebounds after non-final FTs, see §6).
Chances per possession = 1 + offensive rebounds by the offense inside the ramirobentes
possession (chance boundary = `offensive_rebound`, rules.yaml):

{_md_table(f['chances'])}

Examples (possessions with ≥ 3 chances):

{f['orb_examples']}

## 4. Flagrant fouls

Flagrant fouls (foul codes 14 / 15): **{fl_fouls:,}**; flagrant FTs (FT codes 18–20):
**{fl_fts:,}** ({fl_made:,} made). Rule (decided): the FT trip and the retained possession
are two possessions.

{f['flagrant_examples']}

## 5. Technical free throws

| Measure | Count |
|---|---|
| Technical FTs (code 16) | {tech_n:,} |
| made | {tech_made:,} |
| shot by the team on offense in that ramirobentes possession | {tech_off:,} |
| shot by the **defense** (why `scoring_team_id` ≠ `offense_team_id`) | {tech_def:,} |
| possession unknown | {tech_unk:,} |
| ramirobentes marks the technical FT as a possession end | {tech_poss_end:,} |

Examples (technical FT by the defense):

{f['tech_examples']}

## 6. "Team rebound" after a non-final missed free throw (proposed: ignore)

Team rebound rows (msg 4, no player) right after a **missed** FT coded 1 of 2, 1 of 3,
2 of 3 or flagrant 1 of 2: **{ftr_n:,}** (of {f['n_team_reb']:,} team rebounds;
{ftr_null:,} of them have no `reb_type` in ramirobentes).

{f['ft_team_reb_examples']}

## 7. Jump balls / held balls (proposed)

All jump balls {jb_all:,}; not the opening tip of a period: **{jb_mid:,}**. Of those, the
team of the next shot / FT / turnover differs from the team of the last shot / FT /
rebound / turnover before the jump ball in {jb_change:,} cases — an **approximation** of
"the other team gained control" (assumption).

{f['jb_examples']}

## 8. Possession start types (decided)

Reference only — derived from how the **previous ramirobentes possession** ended
(`after_steal` = turnover row naming a stealer; `is_after_timeout` = a timeout before the
first action of the possession):

{_md_table(f['start_types_rb'])}

pbpstats start types for comparison (its categories are finer, e.g. by shot zone):

{_md_table(f['start_types_ps'])}

Examples (each sequence starts with the two events before the possession):

{f['start_type_examples']}

## 9. Garbage time — Cleaning the Glass definition (decided as flag)

Definition from rules.yaml. **Retroactive rule confirmed by the owner (CTG official)**; the
numeric thresholds and the starters condition were **checked by the owner against CTG's
official definition** (2026-10-18): period {rules['garbage_time']['periods']}, margin ≥ 25 / 20 / 10 with
12–9 / 9–6 / ≤ 6 minutes left, and ≤ {rules['garbage_time']['max_combined_starters_on_court']} of the
game's starters on the floor combined. Starters are computed by us (the lineup on the game's first
event); margin and starters are taken at the possession start. Our starter count equals
ramirobentes' `total_starters_*` on {pct(f['starters_agree'][0], f['starters_agree'][1])} of possessions.

| Variant | Possessions | Share |
|---|---|---|
| **CTG (retroactive): condition holds from the possession to the end of the game** | {gt_retro:,} | **{pct(gt_retro, gt_all)}** |
| For comparison: condition checked on each possession alone | {gt_each:,} | {pct(gt_each, gt_all)} |
| All possessions | {gt_all:,} | |

For comparison, ramirobentes' own `garbage_time` flag is on for {gt_ev:,} of {n_ev:,}
events ({pct(gt_ev, n_ev)}; its definition is not documented in the source).

{f['gt_examples']}

## 10. Possession counts per game: ramirobentes vs pbpstats

Full per-game list: `docs/validation/possession_counts_{label}.csv`
(columns `rb_home, rb_away` = sum of ramirobentes `poss_home / poss_away`;
`ps_home, ps_away` = pbpstats possessions by offense; `diff_* = rb − ps`).

Totals: ramirobentes {total_rb:,}, pbpstats {total_ps:,}.

Distribution of |ramirobentes − pbpstats| per team-game:

{_md_table(_bucket_table(pg))}

Within-game balance (CLAUDE.md check 7, |home − away| ≤ 2): ramirobentes
{(within_rb <= 2).sum():,} / {len(pg):,} games; pbpstats {(within_ps <= 2).sum():,} / {len(pg):,}.

Largest differences:

{_md_table(worst)}

## Notes for the possession code

- **Duplicate steal / block rows (2025-26):** the cdn.nba.com-era file has steals (msg 95) and
  blocks (msg 92) as their own rows *and* still names the stealer / blocker on the turnover /
  missed-shot row. Count each steal or block once.
- **player1 / player2 / player3 roles change by era** (e.g. jump ball: 2004-05 player1 = jumper,
  2025-26 player1 = player who got the tip; blocker on a miss: player3 → player2). Never assume a
  fixed role order (`docs/validation/format_diff_2004-05_vs_2025-26.md`).
- **Substitution rows** show the lineup **after** the substitution (owner definition 2026-10-18,
  same as ramirobentes); every substitution starts a new stint.
- **pbpstats comparison:** pbpstats has already removed possessions that start with ≤ 2 s left
  and score 0 points (same as our default threshold) — compare against our counts **after** the
  exclusion.
- **Reference only, not a decision:** pbpstats' source code uses a hybrid for substitutions
  during a possession — the possession is credited to the lineup on court when it ends, free-throw
  points to the lineup on court at the time of the foul. The owner decided on 2026-10-22 to follow
  it in both profiles.
- **Scoring by the team not on offense:** `docs/validation/scoring_attribution.md`. With the
  reference segmentation, almost all such events are and-1 free throws (the reference ends the
  possession on the made shot) or technical FTs; a handful are FTs at a period boundary.

## Development strategy: copy first, then deviate

Two profiles in `config/rules.yaml`: **`pbpstats_compat`** (a baseline as close to pbpstats as
possible; case 2 uses pbpstats' hybrid) and **`custom`** (the owner's adjustments, e.g.
technical FTs excluded by default; case 2 open). When the possession code exists, run
`pbpstats_compat` first and compare game by game with `reference.pbpstats_possessions`: the goal
is equal per-team possession counts in the vast majority of games. Every mismatch is
investigated and explained; the logic is never bent to match a number. Then deviate in `custom`,
one documented change at a time.

## Open questions for the owner

1. Statuses copied from CLAUDE.md instead of "all proposed" (see top). **[待確認]**
2. Cleaning the Glass definition: checked by the owner against CTG's official text (2026-10-18).
   Open detail: the minute boundaries (exactly 9:00 / 6:00 left) are assigned to the lower
   threshold here. **[待確認]**
3. Chance boundaries: only `offensive_rebound` so far; CTG may split on other events. **[待確認]**
4. Player roles in player1/2/3 differ by era (jump balls, blocks): possession code must
   not assume a fixed order (see `docs/validation/format_diff_2004-05_vs_2025-26.md`).
"""
    path = DOCS / "possession_rules.md"
    path.write_text(md, encoding="utf-8")
    return [path, csv_path]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--season-end-year", type=int, default=2005)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    rules = load_rules()
    con = duckdb.connect()
    build(con, args.season_end_year, rules)
    for p in write(facts(con, args.season_end_year, rules), args.season_end_year, rules):
        print(f"wrote {p.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
