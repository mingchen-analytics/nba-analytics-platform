"""Validation check 11: BigDataBall vs our database (BigDataBall is validation-only).

For every BigDataBall season folder in data/raw/bigdataball/:
1. Final score per game (last BigDataBall row) vs core.games.
2. Event alignment: BigDataBall `play_id` = NBA `source_event_num`, then period and clock
   must agree too ("aligned by event time").
3. player_xref: BigDataBall name -> NBA player_id, built from the aligned lineups.
   - rule `name`: the accent/case/punctuation-insensitive name equals a name of exactly
     one player who is in that team's aligned lineups that season;
   - rule `lineup`: otherwise, in every aligned lineup where the name appears there is
     exactly one unmatched name and one unmatched ID, always the same ID (>= MIN_VOTES
     times). Anything else stays **unmatched** and is listed (no guessing).
   Rows go to core.player_xref (source 'bigdataball', method 'auto').
4. Lineup agreement: share of aligned events whose five home and five away IDs are the
   same in both sources (BigDataBall names mapped through the xref).

Writes docs/validation/bigdataball_crosscheck.md and data/staging/bigdataball/.

Usage:
    python -m nba_platform.validate.bdb_crosscheck
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict

import pandas as pd

from nba_platform import db
from nba_platform.db import PROJECT_ROOT
from nba_platform.load import STAGING_DIR
from nba_platform.staging import bigdataball as bdb
from nba_platform.validate import checks, report

REPORT = PROJECT_ROOT / "docs" / "validation" / "bigdataball_crosscheck.md"
MIN_VOTES = 10


def read_season(season_dir) -> pd.DataFrame:
    frames = []
    for gid, path in bdb.game_files(season_dir).items():
        g = bdb.read_game(path)
        g["file_row"] = range(len(g))  # play_id is not monotonic in the files: keep file order
        frames.append(g[["game_id", "file_row", "play_id", "period", "clock", "away_score", "home_score",
                         "away_names", "home_names", "data_set"]])
    return pd.concat(frames, ignore_index=True)


def build_xref(aligned: pd.DataFrame, id_names: dict[int, set[str]]) -> tuple[dict[str, tuple[int, str]], dict]:
    """aligned: one row per (event, side) with `names` (BigDataBall) and `ids` (ours).

    Returns ({normalized_name: (player_id, rule)}, info_for_unmatched).
    """
    # rule `name`: candidates are IDs seen in the same team's lineups
    seen_with: dict[str, set[int]] = defaultdict(set)
    for names, ids, team in zip(aligned["names"], aligned["ids"], aligned["team_id"]):
        for n in names:
            seen_with[(n, team)].update(ids)
    xref: dict[str, tuple[int, str]] = {}
    for (n, team), ids in seen_with.items():
        cands = {i for i in ids if n in id_names.get(i, set())}
        if len(cands) == 1:
            pid = next(iter(cands))
            if n in xref and xref[n][0] != pid:
                xref[n] = (-1, "conflict")
            else:
                xref.setdefault(n, (pid, "name"))
    xref = {n: v for n, v in xref.items() if v[0] != -1}

    # rule `lineup`: single leftover name <-> single leftover ID, consistently
    votes: dict[str, Counter] = defaultdict(Counter)
    for names, ids in zip(aligned["names"], aligned["ids"]):
        matched_ids = {xref[n][0] for n in names if n in xref}
        left_names = [n for n in names if n not in xref]
        left_ids = [i for i in ids if i not in matched_ids]
        if len(left_names) == 1 and len(left_ids) == 1:
            votes[left_names[0]][left_ids[0]] += 1
        else:
            for n in left_names:
                votes[n]["ambiguous"] += 1
    unmatched = {}
    for n, c in votes.items():
        ids = [k for k in c if k != "ambiguous"]
        if len(ids) == 1 and c[ids[0]] >= MIN_VOTES and c["ambiguous"] == 0 and ids[0] not in {v[0] for v in xref.values()}:
            xref[n] = (ids[0], "lineup")
        else:
            unmatched[n] = {(k if k == "ambiguous" else int(k)): v for k, v in c.items()}
    return xref, unmatched


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    run()


def run(con=None, seasons: list[str] | None = None) -> list[dict]:
    """Cross-check every BigDataBall season (or only `seasons`). Uses `con` if given (pipeline --all),
    else opens one. Returns one summary dict per season."""
    summaries: list[dict] = []
    own = con is None
    con = con or db.connect()
    lines = ["# BigDataBall cross-check (validation check 11)", "",
             "BigDataBall is used for validation only; nothing from it is loaded into core tables except",
             "`core.player_xref` rows (source `bigdataball`). Numbers and IDs only, except the list of",
             "unmatched BigDataBall names, which is the point of that list.", ""]
    try:
        if seasons is None:  # full run rebuilds the BigDataBall xref; a partial run only upserts
            con.execute("DELETE FROM core.player_xref WHERE source = 'bigdataball'")
        for season_dir in sorted(p for p in bdb.BDB_DIR.iterdir() if p.is_dir()):
            season = season_dir.name
            if seasons is not None and season not in seasons:
                continue
            raw = read_season(season_dir)
            out = STAGING_DIR / "bigdataball" / season
            out.mkdir(parents=True, exist_ok=True)
            raw.to_parquet(out / "events.parquet", index=False)
            raw["home_norm"] = raw["home_names"].map(lambda v: [bdb.normalize_name(x) for x in v])
            raw["away_norm"] = raw["away_names"].map(lambda v: [bdb.normalize_name(x) for x in v])
            game_ids = sorted(raw["game_id"].unique())
            con.register("bdb_games", pd.DataFrame({"game_id": game_ids}))

            ours = con.execute("""
                SELECT e.game_id, e.source_event_num, e.period, e.clock, e.event_type, g.home_team_id, g.away_team_id,
                       l.home_player_ids, l.away_player_ids
                FROM core.events e JOIN core.games g USING (game_id)
                JOIN staging.event_lineups l USING (game_id, event_seq)
                WHERE e.game_id IN (SELECT game_id FROM bdb_games)""").df()
            games = con.execute("""SELECT game_id, season_type, home_score, away_score FROM core.games
                                   WHERE game_id IN (SELECT game_id FROM bdb_games)""").df()
            names = con.execute("SELECT player_id, name FROM staging.player_names").df()
            con.unregister("bdb_games")
            id_names: dict[int, set[str]] = defaultdict(set)
            for pid, n in zip(names["player_id"], names["name"]):
                id_names[int(pid)].add(bdb.normalize_name(n))

            # 1. final scores
            last = raw.sort_values(["game_id", "file_row"]).groupby("game_id").tail(1)  # final row of the file
            sc = last.merge(games, on="game_id", how="left", suffixes=("_bdb", "_ours"))
            missing_games = sc["home_score_ours"].isna()
            score_bad = sc[~missing_games & ((sc["home_score_bdb"] != sc["home_score_ours"])
                                             | (sc["away_score_bdb"] != sc["away_score_ours"]))]

            # 2. alignment
            m = raw.merge(ours, left_on=["game_id", "play_id"], right_on=["game_id", "source_event_num"],
                          how="left", suffixes=("_bdb", ""))
            m["matched_id"] = m["source_event_num"].notna()
            m["same_time"] = m["matched_id"] & (m["period_bdb"] == m["period"]) & (
                m["clock_bdb"].str[:5] == m["clock"].astype(str).str[:5])
            al = m[m["same_time"]]
            al = al.sort_values(["game_id", "file_row"])
            sides = pd.concat([
                pd.DataFrame({"game_id": al["game_id"], "names": al["home_norm"], "ids": al["home_player_ids"].map(list),
                              "team_id": al["home_team_id"], "side": "home", "event_type": al["event_type"],
                              "file_row": al["file_row"]}),
                pd.DataFrame({"game_id": al["game_id"], "names": al["away_norm"], "ids": al["away_player_ids"].map(list),
                              "team_id": al["away_team_id"], "side": "away", "event_type": al["event_type"],
                              "file_row": al["file_row"]}),
            ], ignore_index=True)

            # 3. xref
            xref, unmatched = build_xref(sides, id_names)
            original = {}
            for v in pd.concat([raw["home_names"], raw["away_names"]]):
                for x in v:
                    original.setdefault(bdb.normalize_name(x), x)
            rows = [("bigdataball", original.get(n, n), int(pid), "auto") for n, (pid, _) in xref.items()]
            con.executemany("INSERT OR REPLACE INTO core.player_xref VALUES (?, ?, ?, ?)", rows)
            rule_counts = Counter(r for _, r in xref.values())

            # 4. lineup agreement through the xref
            def agree(row) -> bool:
                mapped = [xref.get(n, (None,))[0] for n in row["names"]]
                return None not in mapped and sorted(mapped) == sorted(row["ids"])

            sides["agree"] = sides.apply(agree, axis=1)
            per_game = sides.groupby("game_id")["agree"].mean()
            sides["n_diff"] = [len({xref.get(n, (-1,))[0] for n in nm} ^ set(i)) // 2 for nm, i in zip(sides["names"], sides["ids"])]
            sides = sides.sort_values(["game_id", "side", "file_row"])
            prev_bad = sides.groupby(["game_id", "side"])["agree"].shift(fill_value=True)
            run_starts = sides[~sides["agree"] & prev_bad]
            n_diff_dist = sides.loc[~sides["agree"], "n_diff"].value_counts().sort_index()
            start_types = run_starts["event_type"].value_counts()
            ev_agree = sides.groupby(sides.index % len(al) if len(al) else sides.index)["agree"].all() if len(al) else pd.Series(dtype=bool)
            n_events_both = int(ev_agree.sum())

            lines += [f"## {season}", "",
                      "| measure | value |", "|---|---|",
                      f"| BigDataBall game files | {len(game_ids):,} |",
                      f"| … found in core.games | {int((~missing_games).sum()):,} |",
                      f"| … not in core.games | {int(missing_games.sum()):,} |",
                      f"| final score differs | {len(score_bad):,} |",
                      f"| BigDataBall events | {len(raw):,} |",
                      f"| … same event number in our events | {int(m['matched_id'].sum()):,} ({m['matched_id'].mean():.2%}) |",
                      f"| … and same period + clock (aligned) | {len(al):,} ({len(al) / len(raw):.2%}) |",
                      f"| aligned events with identical home **and** away lineups | {n_events_both:,} ({n_events_both / max(len(al), 1):.2%}) |",
                      f"| aligned team-lineups identical | {int(sides['agree'].sum()):,} / {len(sides):,} ({sides['agree'].mean():.2%}) |",
                      f"| BigDataBall names | {len(original):,} |",
                      f"| … mapped by name | {rule_counts.get('name', 0):,} |",
                      f"| … mapped by lineup | {rule_counts.get('lineup', 0):,} |",
                      f"| … unmatched (listed below) | {len(unmatched):,} |", ""]
            if len(score_bad):
                lines += ["Final score differences:", "", "| game_id | home bdb | home ours | away bdb | away ours |",
                          "|---|---|---|---|---|"]
                for r in score_bad.itertuples(index=False):
                    lines.append(f"| {r.game_id} | {r.home_score_bdb:g} | {r.home_score_ours:g} | {r.away_score_bdb:g} | {r.away_score_ours:g} |")
                lines.append("")
            lines += ["Where the lineups differ:", "",
                      "| players different | team-lineups |", "|---|---|",
                      *[f"| {k} | {v:,} |" for k, v in n_diff_dist.items()], "",
                      f"Differences come in runs: {len(run_starts):,} runs; the event where a run starts:", "",
                      "| event type | runs |", "|---|---|",
                      *[f"| {k} | {v:,} |" for k, v in start_types.items()], "",
                      "Reading: almost every difference is **one** player, persisting from a substitution or",
                      "a period start until the next substitution — the two sources reconstruct some lineups",
                      "differently (typically substitutions not logged between periods). Neither source is",
                      "the ground truth; which one is right needs a third source (e.g. box-score minutes",
                      "or video). Unmatched names below also count as disagreement.", ""]
            low = per_game.sort_values().head(10)
            lines += ["Games with the lowest lineup agreement:", "", "| game_id | team-lineups identical |", "|---|---|"]
            lines += [f"| {g} | {v:.2%} |" for g, v in low.items()]
            lines += ["", "Unmatched BigDataBall names (not guessed):", ""]
            if unmatched:
                lines += ["| name | votes by candidate ID (`ambiguous` = not a single leftover) |", "|---|---|"]
                for n, c in sorted(unmatched.items()):
                    lines.append(f"| {original.get(n, n)} | {c} |")
            else:
                lines.append("_(none)_")
            lines += ["", "An unmatched name can be added by hand as a `manual` row in `core.player_xref` after",
                      "checking it; the candidate IDs above are evidence, not decisions.", ""]
            # arbitration of the disagreements (report only)
            from nba_platform.rules import load_rules
            from nba_platform.validate import bdb_arbitration
            tol = float(load_rules()["validation"]["minutes_rounding_tolerance"])
            arb_lines, arb_summary = bdb_arbitration.arbitrate(con, season, int(season.split("-")[0]) + 1, tol)
            lines += arb_lines
            print(f"{season} arbitration: {arb_summary}")
            summaries.append({"season": season, "games": len(game_ids), "score_diffs": len(score_bad),
                              "events_aligned": round(len(al) / max(len(raw), 1), 5),
                              "lineups_identical": round(float(sides["agree"].mean()), 4),
                              "xref": len(xref), "unmatched": len(unmatched), "runs": arb_summary.get("runs", 0),
                              "ramirobentes_right": arb_summary.get("overall", {}).get("ramirobentes", 0),
                              "bigdataball_right": arb_summary.get("overall", {}).get("bigdataball", 0)})
            # record check 11 per season type (warning level)
            gtype = dict(zip(games["game_id"], games["season_type"]))
            sides["season_type"] = sides["game_id"].map(gtype)
            y = int(season.split("-")[0]) + 1
            for stype, part in sides.groupby("season_type"):
                n_score = int(score_bad["game_id"].map(gtype).eq(stype).sum())
                n_bad = int((~part["agree"]).sum()) + n_score
                checks.save_check_results(con, y, stype, [checks.CheckResult(
                    11, "cross-source: BigDataBall scores and lineups", "pass" if n_bad == 0 else "fail",
                    len(part), n_bad,
                    {"games": int(part["game_id"].nunique()), "final_score_diffs": n_score,
                     "team_lineups_identical": round(float(part["agree"].mean()), 4),
                     "unmatched_names": len(unmatched), "report": "docs/validation/bigdataball_crosscheck.md"})])
            print(f"{season}: {len(game_ids)} games, aligned {len(al)}/{len(raw)}, "
                  f"lineups identical {sides['agree'].mean():.2%}, xref {len(xref)}, unmatched {len(unmatched)}, "
                  f"score diffs {len(score_bad)}")
        report.write_season_report(con)
    finally:
        if own:
            con.close()
    if seasons is None:  # a partial run must not overwrite the full report
        REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summaries


if __name__ == "__main__":
    main()
