"""Investigate player-games whose PBP minutes differ from the box score by more than
`validation.minutes_large_diff` (plan 2026-10-18, step 3). Report only — nothing changes.

For each player-game the evidence is:
- team_box_off: the team's box minutes minus 5 x game length. If it is off by about the
  same amount as the player, the box score is the likely culprit (minutes missing/extra).
- period_start_run: seconds the player was on court in stretches that start at a period
  start without a logged substitution bringing him in (ramirobentes infers those lineups).
  If such a stretch is about the size of the difference, ramirobentes' lineup is suspect.
- counterpart: a teammate in the same game with an opposite difference of similar size
  (minutes swapped between two players — the two sources disagree on who was on court).
- bigdataball (where a BigDataBall season exists): the player's minutes from BigDataBall's
  lineups on the same aligned events and the same clock. Close to the box score -> our
  lineup is the odd one out; close to ours -> the box score is the odd one out.

Classification (first rule that applies):
  box_likely_wrong          team box total off by >= large_diff/2 in the player's direction
  ramirobentes_likely_wrong BigDataBall agrees with the box (<= tolerance) and not with us,
                            or (no BigDataBall) a period-start stretch matches the difference
  box_likely_wrong          BigDataBall agrees with us (<= tolerance) and not with the box
  swapped_with_teammate     a teammate has the opposite difference (sum within tolerance)
  undetermined              anything else

Usage:
    python -m nba_platform.validate.minutes_large_diff
"""

from __future__ import annotations

import sys

import pandas as pd

from nba_platform import db
from nba_platform.db import PROJECT_ROOT
from nba_platform.rules import load_rules
from nba_platform.seasons import season_label
from nba_platform.staging import bigdataball as bdb
from nba_platform.validate import checks
from nba_platform.validate.box_minutes import load_box_minutes

REPORT = PROJECT_ROOT / "docs" / "validation" / "minutes_large_diff.md"
SEASONS = [(1997, "regular"), (2006, "regular"), (2007, "regular")]


def large_diffs(con, y: int, t: str, large: float) -> pd.DataFrame:
    box = load_box_minutes(y, t)
    con.register("box_m", box)
    try:
        df = con.execute(f"""
            WITH p AS ({checks.pbp_player_seconds_sql(y, t)})
            SELECT p.game_id, p.player_id, b.team_id, p.pbp_secs / 60.0 AS pbp_min, b.box_min,
                   p.pbp_secs / 60.0 - b.box_min AS diff
            FROM p JOIN box_m b USING (game_id, player_id)""").df()
        team = con.execute("""
            SELECT b.game_id, b.team_id, sum(b.box_min) - 5 * (48 + 5 * (any_value(g.num_periods) - 4)) AS team_box_off
            FROM box_m b JOIN core.games g USING (game_id) GROUP BY ALL""").df()
    finally:
        con.unregister("box_m")
    df = df.merge(team, on=["game_id", "team_id"], how="left")
    big = df[df["diff"].abs() > large].copy()
    # counterpart: a teammate with an opposite difference in the same game
    partners = df.merge(big[["game_id", "team_id", "player_id", "diff"]], on=["game_id", "team_id"], suffixes=("", "_big"))
    partners = partners[(partners["player_id"] != partners["player_id_big"]) & (partners["diff"] * partners["diff_big"] < 0)]
    partners["sum"] = (partners["diff"] + partners["diff_big"]).abs()
    best = partners.sort_values("sum").groupby(["game_id", "player_id_big"]).head(1)
    big = big.merge(best[["game_id", "player_id_big", "player_id", "sum"]].rename(
        columns={"player_id": "counterpart_id", "player_id_big": "player_id", "sum": "counterpart_sum"}),
        on=["game_id", "player_id"], how="left")
    return big


def period_start_runs(con, games: list[str]) -> pd.DataFrame:
    """Seconds per (game, player) in on-court stretches that begin at a period start
    without a substitution bringing the player in."""
    con.register("gl", pd.DataFrame({"game_id": games}))
    try:
        return con.execute("""
            WITH e AS (
                SELECT e.game_id, e.event_seq, e.event_type, e.player2_id AS sub_in, e.period,
                       coalesce(lead(e.secs_elapsed_game) OVER w, e.secs_elapsed_game) - e.secs_elapsed_game AS dt,
                       l.home_player_ids || l.away_player_ids AS on_court
                FROM core.events e JOIN staging.event_lineups l USING (game_id, event_seq)
                WHERE e.game_id IN (SELECT game_id FROM gl)
                WINDOW w AS (PARTITION BY e.game_id ORDER BY e.event_seq)
            ),
            pe AS (SELECT game_id, event_seq, event_type, sub_in, period, dt, unnest(on_court) AS player_id FROM e),
            runs AS (
                SELECT *, event_seq - row_number() OVER (PARTITION BY game_id, player_id, period ORDER BY event_seq) AS grp
                FROM pe
            ),
            r AS (
                SELECT game_id, player_id, period, grp, sum(dt) AS secs,
                       arg_min(event_type, event_seq) AS first_type, arg_min(sub_in, event_seq) AS first_sub_in
                FROM runs GROUP BY ALL
            )
            SELECT game_id, player_id, sum(secs) FILTER (first_type = 'period_start') AS period_start_secs,
                   max(secs) FILTER (first_type = 'period_start') AS longest_period_start_run
            FROM r GROUP BY ALL""").df()
    finally:
        con.unregister("gl")


def bigdataball_minutes(con, season: str, games: list[str]) -> pd.DataFrame | None:
    """Player seconds from BigDataBall lineups on our aligned events (same clock)."""
    path = PROJECT_ROOT / "data" / "staging" / "bigdataball" / season / "events.parquet"
    if not path.exists():
        return None
    raw = pd.read_parquet(path)
    raw = raw[raw["game_id"].isin(games)]
    xref = {bdb.normalize_name(k): v for k, v in con.execute(
        "SELECT source_player_key, player_id FROM core.player_xref WHERE source = 'bigdataball'").fetchall()}
    ev = con.execute(f"""
        SELECT game_id, source_event_num, period, clock,
               coalesce(lead(secs_elapsed_game) OVER w, secs_elapsed_game) - secs_elapsed_game AS dt
        FROM core.events WHERE game_id IN ({','.join("'" + g + "'" for g in games)})
        WINDOW w AS (PARTITION BY game_id ORDER BY event_seq)""").df()
    m = raw.merge(ev, left_on=["game_id", "play_id"], right_on=["game_id", "source_event_num"])
    m = m[(m["period_x"] == m["period_y"]) & (m["clock_x"].str[:5] == m["clock_y"].astype(str).str[:5])]
    rows = []
    for gid, dt, home, away in zip(m["game_id"], m["dt"], m["home_names"], m["away_names"]):
        for n in list(home) + list(away):
            rows.append((gid, xref.get(bdb.normalize_name(n)), dt))
    out = pd.DataFrame(rows, columns=["game_id", "player_id", "dt"]).dropna()
    out["player_id"] = out["player_id"].astype("int64")
    return out.groupby(["game_id", "player_id"])["dt"].sum().div(60).rename("bdb_min").reset_index()


def classify(r, large: float, tol: float) -> str:
    if pd.notna(r.team_box_off) and abs(r.team_box_off) >= large / 2 and (r.team_box_off * r.diff) < 0:
        return "box_likely_wrong"  # team box total short/long in the direction of the player's gap
    if pd.notna(getattr(r, "bdb_min", float("nan"))):
        bdb_box, bdb_ours = abs(r.bdb_min - r.box_min), abs(r.bdb_min - r.pbp_min)
        if bdb_box <= tol < bdb_ours:
            return "ramirobentes_likely_wrong"
        if bdb_ours <= tol < bdb_box:
            return "box_likely_wrong"
    elif r.diff > 0 and pd.notna(r.longest_period_start_run) and abs(r.longest_period_start_run / 60 - r.diff) <= tol + 1:
        return "ramirobentes_likely_wrong"
    if pd.notna(r.counterpart_sum) and r.counterpart_sum <= tol:
        return "swapped_with_teammate"
    return "undetermined"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    v = load_rules()["validation"]
    large, tol = float(v["minutes_large_diff"]), float(v["minutes_rounding_tolerance"])
    con = db.connect(read_only=True)
    lines = ["# Check 5 follow-up: player-games with a large minutes difference", "",
             f"Player-games where |PBP minutes − box minutes| > {large:g}. Report only: nothing was changed.",
             "Evidence and rules are described in `src/nba_platform/validate/minutes_large_diff.py`.",
             "Every classification is an **inference** from that evidence, not a verified fact.", ""]
    try:
        for y, t in SEASONS:
            big = large_diffs(con, y, t, large)
            if big.empty:
                lines += [f"## {season_label(y)} {t}", "", "_(none)_", ""]
                continue
            games = sorted(big["game_id"].unique())
            big = big.merge(period_start_runs(con, games), on=["game_id", "player_id"], how="left")
            big["longest_period_start_run"] = big["longest_period_start_run"].astype("float64")
            bdbm = bigdataball_minutes(con, season_label(y), games)
            third = "BigDataBall lineups used as a third source." if bdbm is not None else \
                "No BigDataBall data for this season: classification uses team box totals, period-start stretches and teammates only."
            if bdbm is not None:
                big = big.merge(bdbm, on=["game_id", "player_id"], how="left")
            else:
                big["bdb_min"] = float("nan")
            big["class"] = [classify(r, large, tol) for r in big.itertuples(index=False)]
            counts = big["class"].value_counts()
            agree = ""
            if bdbm is not None:
                has = big["bdb_min"].notna()
                n_ours = int(((big["bdb_min"] - big["pbp_min"]).abs() <= tol)[has].sum())
                n_box = int(((big["bdb_min"] - big["box_min"]).abs() <= tol)[has].sum())
                agree = (f"BigDataBall minutes available for {int(has.sum())} of {len(big)}: within {tol:g} min of our "
                         f"PBP in **{n_ours}**, within {tol:g} min of the box score in **{n_box}**. Team box totals "
                         f"of these games are short by a median of {-big['team_box_off'].median():.0f} minutes.")
            lines += [f"## {season_label(y)} {t}", "", third, "", agree, "",
                      f"{len(big)} player-games in {len(games)} games.", "",
                      "| classification | player-games |", "|---|---|",
                      *[f"| {k} | {v} |" for k, v in counts.items()], "",
                      "| game_id | player_id | PBP min | box min | diff | team box off | longest period-start stretch (min) | teammate swap (sum) | BigDataBall min | classification |",
                      "|---|---|---|---|---|---|---|---|---|---|"]
            for r in big.sort_values(["game_id", "player_id"]).itertuples(index=False):
                f = lambda x, d=1: "—" if pd.isna(x) else f"{x:.{d}f}"  # noqa: E731
                lines.append(f"| {r.game_id} | {r.player_id} | {r.pbp_min:.1f} | {r.box_min:.0f} | {r.diff:+.1f} | "
                             f"{f(r.team_box_off, 0)} | {f(r.longest_period_start_run / 60 if pd.notna(r.longest_period_start_run) else float('nan'))} | "
                             f"{f(r.counterpart_sum)} | {f(r.bdb_min)} | {r['class'] if isinstance(r, dict) else r[-1]} |")
            lines.append("")
            print(f"{y} {t}: {len(big)} player-games: {counts.to_dict()}")
    finally:
        con.close()
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
