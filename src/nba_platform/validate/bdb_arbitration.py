"""Arbitrate lineup disagreements between ramirobentes and BigDataBall (plan 2026-10-18,
step 9). Report only — no data is changed.

A *run* = consecutive aligned events (our event order, one team) where the two sources
show different five-player lineups. For each run, the players on court in only one source
are compared with two independent references:

1. **Box-score minutes** (nba_api LeagueGameLog): each source's lineups give every player a
   game total (time to the next event credited to the five shown). For the run's players,
   a source is *right* if all of them are within `minutes_rounding_tolerance` of the box
   score and the other source has at least one outside it; *leans* to a source if both are
   outside but one is closer by ≥ 2 minutes in total; else *undetermined*.
2. **Official play-by-play substitutions** (shufinskiy `nbastats_*`): a player who is
   substituted **out** (or **in**) inside the run window — or at the event that ends it —
   must have been on court (or off court) before. Such a substitution supports the source
   that agrees with it; none → *no evidence*.

Both verdicts are inferences from evidence, reported separately and combined.
"""

from __future__ import annotations

from collections import Counter

import pandas as pd

from nba_platform.ingest.download import RAW_DIR
from nba_platform.staging import bigdataball as bdb
from nba_platform.staging import shufinskiy as sh
from nba_platform.validate.box_minutes import load_box_minutes


def _official_subs(season_end_year: int, season_type: str) -> pd.DataFrame | None:
    key = f"nbastats{'_po' if season_type == 'playoffs' else ''}_{season_end_year - 1}"
    path = RAW_DIR / "shufinskiy" / f"{key}.tar.xz"
    if not path.exists():
        return None
    df = sh.read_tar_csv(path, dtype={"GAME_ID": str},
                         usecols=["GAME_ID", "EVENTNUM", "EVENTMSGTYPE", "PLAYER1_ID", "PLAYER2_ID"])
    df = df[df["EVENTMSGTYPE"] == 8].copy()
    df["GAME_ID"] = df["GAME_ID"].str.zfill(10)
    return df.rename(columns={"GAME_ID": "game_id", "EVENTNUM": "event_num", "PLAYER1_ID": "out_id", "PLAYER2_ID": "in_id"})


def aligned_sides(con, raw: pd.DataFrame, xref: dict[str, int]) -> pd.DataFrame:
    """One row per (aligned event, side) with both sources' lineups and the event's duration."""
    games = sorted(raw["game_id"].unique())
    con.register("arb_games", pd.DataFrame({"game_id": games}))
    try:
        ours = con.execute("""
            SELECT e.game_id, e.event_seq, e.source_event_num, e.period, e.clock, e.event_type, g.season_type,
                   coalesce(lead(e.secs_elapsed_game) OVER w, e.secs_elapsed_game) - e.secs_elapsed_game AS dt,
                   l.home_player_ids, l.away_player_ids
            FROM core.events e JOIN core.games g USING (game_id) JOIN staging.event_lineups l USING (game_id, event_seq)
            WHERE e.game_id IN (SELECT game_id FROM arb_games)
            WINDOW w AS (PARTITION BY e.game_id ORDER BY e.event_seq)""").df()
    finally:
        con.unregister("arb_games")
    m = raw.merge(ours, left_on=["game_id", "play_id"], right_on=["game_id", "source_event_num"], suffixes=("_bdb", ""))
    m = m[(m["period_bdb"] == m["period"]) & (m["clock_bdb"].str[:5] == m["clock"].astype(str).str[:5])]
    to_ids = lambda names: [xref.get(bdb.normalize_name(n), -1) for n in names]  # noqa: E731
    sides = pd.concat([
        pd.DataFrame({"game_id": m["game_id"], "event_seq": m["event_seq"], "event_num": m["source_event_num"],
                      "event_type": m["event_type"], "season_type": m["season_type"], "dt": m["dt"], "side": "home",
                      "ours": m["home_player_ids"].map(list), "bdb": m["home_names"].map(to_ids)}),
        pd.DataFrame({"game_id": m["game_id"], "event_seq": m["event_seq"], "event_num": m["source_event_num"],
                      "event_type": m["event_type"], "season_type": m["season_type"], "dt": m["dt"], "side": "away",
                      "ours": m["away_player_ids"].map(list), "bdb": m["away_names"].map(to_ids)}),
    ], ignore_index=True).sort_values(["game_id", "side", "event_seq"]).reset_index(drop=True)
    sides["differ"] = [sorted(a) != sorted(b) for a, b in zip(sides["ours"], sides["bdb"])]
    return sides


def game_minutes(sides: pd.DataFrame, column: str) -> pd.Series:
    rows = [(g, p, dt) for g, ids, dt in zip(sides["game_id"], sides[column], sides["dt"]) for p in ids if p != -1]
    df = pd.DataFrame(rows, columns=["game_id", "player_id", "dt"])
    return df.groupby(["game_id", "player_id"])["dt"].sum() / 60


def runs_of(sides: pd.DataFrame) -> pd.DataFrame:
    s = sides.copy()
    new_run = s["differ"] & ~(s.groupby(["game_id", "side"])["differ"].shift(fill_value=False))
    s["run_id"] = new_run.cumsum().where(s["differ"])
    d = s[s["differ"]]
    agg = d.groupby("run_id").agg(game_id=("game_id", "first"), side=("side", "first"),
                                  season_type=("season_type", "first"), start_type=("event_type", "first"),
                                  first_seq=("event_seq", "min"), last_seq=("event_seq", "max"),
                                  first_event=("event_num", "first"), events=("event_seq", "size"),
                                  secs=("dt", "sum"))
    only = d.groupby("run_id").apply(lambda g: pd.Series({
        "only_ours": sorted(set().union(*[set(a) - set(b) for a, b in zip(g["ours"], g["bdb"])])),
        "only_bdb": sorted(set().union(*[set(b) - set(a) for a, b in zip(g["ours"], g["bdb"])]) - {-1}),
        "unmapped": any(-1 in b for b in g["bdb"])}), include_groups=False)
    out = agg.join(only).reset_index()
    # event number that ends the run (the next aligned event of the same side), for the window
    nxt = s.groupby(["game_id", "side"])["event_num"].shift(-1)
    out["end_event"] = [nxt[d.index[d["run_id"] == r][-1]] for r in out["run_id"]]
    return out


def minutes_verdict(run, ours_min, bdb_min, box, tol: float) -> str:
    players = list(dict.fromkeys(run.only_ours + run.only_bdb))
    if not players:
        return "undetermined"
    e_ours, e_bdb = [], []
    for p in players:
        b = box.get((run.game_id, p))
        if b is None:
            return "undetermined"
        e_ours.append(abs(ours_min.get((run.game_id, p), 0.0) - b))
        e_bdb.append(abs(bdb_min.get((run.game_id, p), 0.0) - b))
    ok_ours, ok_bdb = max(e_ours) <= tol, max(e_bdb) <= tol
    if ok_ours and not ok_bdb:
        return "ramirobentes"
    if ok_bdb and not ok_ours:
        return "bigdataball"
    if not ok_ours and not ok_bdb and abs(sum(e_ours) - sum(e_bdb)) >= 2:
        return "leans ramirobentes" if sum(e_ours) < sum(e_bdb) else "leans bigdataball"
    return "undetermined"


def official_verdict(run, subs_by_game: dict) -> str:
    subs = subs_by_game.get(run.game_id)
    if subs is None:
        return "no official data"
    hi = run.end_event if pd.notna(run.end_event) else run.first_event
    w = subs[(subs["event_num"] >= run.first_event) & (subs["event_num"] <= hi)]
    support = set()
    for ev, out_id, in_id in zip(w["event_num"], w["out_id"], w["in_id"]):
        # a player substituted OUT was on court before: supports the source that has him on court
        if out_id in run.only_ours:
            support.add("ramirobentes")
        if out_id in run.only_bdb:
            support.add("bigdataball")
        # a player substituted IN: at the run's first event (sub row shows the post-sub lineup)
        # he is on court from then on; later inside the run he was off court before entering
        at_start = ev == run.first_event
        if in_id in run.only_ours:
            support.add("ramirobentes" if at_start else "bigdataball")
        if in_id in run.only_bdb:
            support.add("bigdataball" if at_start else "ramirobentes")
    if not support:
        return "no evidence"
    return support.pop() if len(support) == 1 else "conflicting"


def arbitrate(con, season: str, season_end_year: int, tol: float) -> tuple[list[str], dict]:
    path = bdb.BDB_DIR.parents[1] / "staging" / "bigdataball" / season / "events.parquet"
    raw = pd.read_parquet(path)
    xref = {bdb.normalize_name(k): v for k, v in con.execute(
        "SELECT source_player_key, player_id FROM core.player_xref WHERE source = 'bigdataball'").fetchall()}
    sides = aligned_sides(con, raw, xref)
    runs = runs_of(sides)
    ours_min, bdb_min = game_minutes(sides, "ours").to_dict(), game_minutes(sides, "bdb").to_dict()
    box, subs_by_game = {}, {}
    for t in runs["season_type"].unique():
        b = load_box_minutes(season_end_year, t)
        if b is not None:
            box.update({(g, p): m for g, p, m in zip(b["game_id"], b["player_id"], b["box_min"])})
        o = _official_subs(season_end_year, t)
        if o is not None:
            subs_by_game.update({g: grp for g, grp in o.groupby("game_id")})
    runs["minutes"] = [minutes_verdict(r, ours_min, bdb_min, box, tol) for r in runs.itertuples(index=False)]
    runs["official"] = [official_verdict(r, subs_by_game) for r in runs.itertuples(index=False)]

    def combined(m, o):
        m_side = m.replace("leans ", "") if m != "undetermined" else None
        o_side = o if o in ("ramirobentes", "bigdataball") else None
        if m_side and o_side and m_side != o_side:
            return "conflicting evidence"
        side = m_side or o_side
        return side or "undetermined"

    runs["verdict"] = [combined(m, o) for m, o in zip(runs["minutes"], runs["official"])]
    runs["category"] = runs["start_type"].map(lambda x: x if x in ("substitution", "period_start") else "other")

    lines = [f"### Arbitration of lineup disagreements ({season})", "",
             "Report only. Evidence: box-score minutes (nba_api) and official play-by-play substitutions",
             "(shufinskiy `nbastats_*`); rules in `src/nba_platform/validate/bdb_arbitration.py`. Each verdict is an",
             "**inference** from that evidence.", "",
             f"Disagreement runs (our event order): {len(runs):,}.", ""]
    summary = {}
    for cat in ("substitution", "period_start", "other"):
        part = runs[runs["category"] == cat]
        if part.empty:
            continue
        mv, ov, cv = Counter(part["minutes"]), Counter(part["official"]), Counter(part["verdict"])
        summary[cat] = dict(cv)
        lines += [f"**Runs starting at a {cat.replace('_', ' ')}: {len(part):,}**", "",
                  "| evidence | ramirobentes right | BigDataBall right | leans ramirobentes | leans BigDataBall | conflicting | undetermined / none |",
                  "|---|---|---|---|---|---|---|",
                  f"| box-score minutes | {mv['ramirobentes']} | {mv['bigdataball']} | {mv['leans ramirobentes']} | "
                  f"{mv['leans bigdataball']} | — | {mv['undetermined']} |",
                  f"| official substitutions | {ov['ramirobentes']} | {ov['bigdataball']} | — | — | {ov['conflicting']} | "
                  f"{ov['no evidence'] + ov['no official data']} |",
                  f"| **combined** | **{cv['ramirobentes']}** | **{cv['bigdataball']}** | — | — | {cv['conflicting evidence']} | "
                  f"{cv['undetermined']} |", ""]
    total = Counter(runs["verdict"])
    decided = total["ramirobentes"] + total["bigdataball"]
    lines += [f"Overall: {decided:,} of {len(runs):,} runs decided ({decided / max(len(runs), 1):.0%}) — "
              f"ramirobentes right in {total['ramirobentes']:,}, BigDataBall right in {total['bigdataball']:,}; "
              f"{total['conflicting evidence']:,} with conflicting evidence, {total['undetermined']:,} undetermined.", ""]
    summary["overall"] = dict(total)
    summary["runs"] = len(runs)
    return lines, summary
