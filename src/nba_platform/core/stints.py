"""Stints: stretches of play with the same ten players on the floor.

Rules (CLAUDE.md "lineups on court", config/rules.yaml `stints`, owner 2026-10-21):

1. The lineup on a substitution row is the lineup *after* the substitution (as the source gives it).
2. A substitution starts a new stint. **Consecutive substitutions at the same second, with no
   other event between them, are one stint**; its lineup is the one after the last of them.
   An event between them (a free throw, a timeout, ...) keeps them apart, so every free
   throw stays with the lineup that was on the floor when it happened.
3. **Every period starts a new stint.** A stint ends where the next stint starts, or at the end
   of its period (regulation 720 s, overtime 300 s).
4. A lineup change on a row that is *not* a substitution also starts a stint
   (`start_reason = 'lineup_change'`). It means the source changed the lineup without a
   substitution row; it is kept and counted, never hidden.
5. Player IDs keep the source order of the row that defines the stint's lineup.

Pure functions: DataFrames in, DataFrames out; nothing here touches the database.
"""

from __future__ import annotations

import pandas as pd

STINT_COLUMNS = (["game_id", "stint_id", "period", "start_secs", "end_secs", "start_event_seq", "end_event_seq",
                  "start_reason", "n_events"]
                 + [f"home_p{i}" for i in range(1, 6)] + [f"away_p{i}" for i in range(1, 6)])


class StintError(ValueError):
    """The inputs cannot be turned into stints (the pipeline must stop)."""


def period_bounds(period: int, rules: dict) -> tuple[float, float]:
    """(start, end) of a period in seconds since tip-off."""
    reg = rules["stints"]["period_length_secs"]["regulation"]
    ot = rules["stints"]["period_length_secs"]["overtime"]
    if period <= 4:
        start = (period - 1) * reg
        return float(start), float(start + reg)
    start = 4 * reg + (period - 5) * ot
    return float(start), float(start + ot)


def _lineup(game_id: str, event_seq: int, home_ids, away_ids) -> tuple[tuple[int, ...], tuple[int, ...]]:
    home, away = tuple(int(p) for p in home_ids), tuple(int(p) for p in away_ids)
    if len(home) != 5 or len(away) != 5 or len(set(home) | set(away)) != 10:
        raise StintError(f"{game_id} event_seq {event_seq}: lineup is not 5 + 5 distinct players")
    return home, away


def _same(a: tuple, b: tuple) -> bool:
    return set(a[0]) == set(b[0]) and set(a[1]) == set(b[1])


def build_stints(events: pd.DataFrame, lineups: pd.DataFrame, rules: dict) -> tuple[pd.DataFrame, pd.Series]:
    """Stints of one game, and the stint_id of every event (indexed like `events`).

    `events`: core.events rows of one game; `lineups`: staging.event_lineups rows of the same game.
    """
    if events.empty:
        raise StintError("no events")
    if events["game_id"].nunique() != 1:
        raise StintError("build_stints works on one game at a time")
    cfg = rules["stints"]
    if not (cfg["merge_consecutive_substitutions_same_second"] and cfg["new_stint_each_period"]
            and cfg["player_order"] == "source"):
        raise StintError(f"stint rules not implemented: {cfg}")

    ev = events.sort_values("event_seq")
    lu = lineups.set_index("event_seq")
    if len(lu) != len(ev) or not lu.index.equals(pd.Index(ev["event_seq"])):
        raise StintError(f"{ev['game_id'].iloc[0]}: events and lineups do not cover the same event_seq")

    game_id = ev["game_id"].iloc[0]
    stints: list[dict] = []
    stint_of_event: dict[int, int] = {}
    cur = None            # the open stint
    prev = None           # the previous event row

    for row in ev.itertuples(index=True):
        lineup = _lineup(game_id, row.event_seq, lu.at[row.event_seq, "home_player_ids"], lu.at[row.event_seq, "away_player_ids"])
        is_sub = row.event_type == "substitution"
        merged_sub = (is_sub and prev is not None and prev.event_type == "substitution"
                      and prev.period == row.period and prev.secs_elapsed_game == row.secs_elapsed_game)
        reason = None
        if prev is None or row.period != prev.period:
            reason = "period_start"
        elif is_sub and not merged_sub:
            reason = "substitution"
        elif not is_sub and not _same(lineup, cur["lineup"]):
            reason = "lineup_change"

        if reason:
            if cur is not None:
                stints.append(cur)
            start = period_bounds(int(row.period), rules)[0] if reason == "period_start" else float(row.secs_elapsed_game)
            cur = {"stint_id": len(stints) + 1, "period": int(row.period), "start_secs": start,
                   "start_event_seq": int(row.event_seq), "start_reason": reason, "lineup": lineup, "n_events": 0}
        elif merged_sub:
            cur["lineup"] = lineup        # lineup after the last substitution of the run
        cur["end_event_seq"] = int(row.event_seq)
        cur["n_events"] += 1
        stint_of_event[row.Index] = cur["stint_id"]
        prev = row
    stints.append(cur)

    # end of each stint: the next stint's start in the same period, else the period's end
    for i, s in enumerate(stints):
        nxt = stints[i + 1] if i + 1 < len(stints) else None
        s["end_secs"] = nxt["start_secs"] if nxt is not None and nxt["period"] == s["period"] \
            else period_bounds(s["period"], rules)[1]
        if s["end_secs"] < s["start_secs"]:
            raise StintError(f"{game_id} stint {s['stint_id']}: ends before it starts")

    out = pd.DataFrame([{"game_id": game_id, **{k: v for k, v in s.items() if k != "lineup"},
                         **{f"home_p{i + 1}": p for i, p in enumerate(s["lineup"][0])},
                         **{f"away_p{i + 1}": p for i, p in enumerate(s["lineup"][1])}} for s in stints])
    return out[STINT_COLUMNS], pd.Series(stint_of_event, name="stint_id").reindex(events.index)


def player_seconds(stints: pd.DataFrame) -> pd.DataFrame:
    """(game_id, player_id, side, secs) on court, summed over stints. For checks and on/off."""
    rows = []
    for side in ("home", "away"):
        cols = [f"{side}_p{i}" for i in range(1, 6)]
        part = stints.melt(id_vars=["game_id", "start_secs", "end_secs"], value_vars=cols, value_name="player_id")
        part["side"] = side
        rows.append(part)
    df = pd.concat(rows, ignore_index=True)
    df["secs"] = df["end_secs"] - df["start_secs"]
    return df.groupby(["game_id", "player_id", "side"], as_index=False)["secs"].sum()
