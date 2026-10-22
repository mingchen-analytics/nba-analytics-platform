"""Free-throw trips and the foul that caused each one (possession code, step 2).

For every free throw of one game this returns: the trip it belongs to, its kind (regular,
technical, flagrant, clear_path, transition_take), its number in the trip ("2 of 3"),
whether it is the last free throw of the trip (and whether the trip has all its free throws:
`trip_complete`), `is_technical_ft`, and `foul_event_seq`
(the event_seq of the fouling event). Nothing here decides possessions.

Free-throw kinds come from the NBA action-type code (`event_subtype`), which is the same in
every season 1996-97 → 2025-26 (checked on the data 2026-10-21; codes below). The codes
are a property of the data, not a basketball rule, so they live here, with tests.

Linking a trip to its foul (owner decisions: source order, unknown -> NULL):
1. Same period and same second, fouling team = the other team (a foul without a team, e.g. a
   team technical the source records without one, also fits).
2. The foul kind must fit the free-throw kind (technical FT <- technical-type foul, flagrant
   FT <- flagrant foul, clear-path FT <- clear-path foul, transition-take FT <- take foul,
   regular FT <- any other personal foul). A rescinded foul (code 0) never counts.
3. Nearest such foul **before** the trip in source order; if there is none, the nearest after
   it (the source sometimes lists the foul after the free throw; pbpstats does the same).
4. A foul feeds at most one trip. No fitting foul -> `foul_event_seq` NULL (counted, never guessed).

Pure functions; nothing here touches the database.
"""

from __future__ import annotations

import pandas as pd

# event_subtype of a free throw -> (kind, number in trip, trip length); None = not numbered
FT_CODES: dict[int, tuple[str, int | None, int | None]] = {
    10: ("regular", 1, 1), 11: ("regular", 1, 2), 12: ("regular", 2, 2),
    13: ("regular", 1, 3), 14: ("regular", 2, 3), 15: ("regular", 3, 3),
    16: ("technical", 1, 1), 21: ("technical", 1, 2), 22: ("technical", 2, 2),
    18: ("flagrant", 1, 2), 19: ("flagrant", 2, 2), 20: ("flagrant", 1, 1),
    27: ("flagrant", 1, 3), 28: ("flagrant", 2, 3), 29: ("flagrant", 3, 3),
    17: ("clear_path", None, None),              # 2000-01 → 2006-07: one code for every clear-path FT
    25: ("clear_path", 1, 2), 26: ("clear_path", 2, 2),
    81: ("transition_take", 1, 1),               # 2025-26 (rule since 2022-23)
}
# event_subtype of a foul -> kind it can cause
TECHNICAL_FOULS = {11, 12, 13, 16, 17, 18, 19, 25, 30, 32, 33}
FLAGRANT_FOULS = {14, 15}
CLEAR_PATH_FOULS = {9}
TAKE_FOULS = {31}
NO_FOUL = {0}

FT_COLUMNS = ["event_seq", "trip_id", "ft_kind", "ft_number", "ft_of", "is_last_ft_of_trip", "trip_complete",
              "is_technical_ft", "foul_event_seq"]


class FreeThrowError(ValueError):
    """A free throw cannot be classified (the pipeline must stop)."""


def foul_kind(code) -> str | None:
    """The free-throw kind a foul with this code can cause (None: rescinded foul)."""
    if pd.isna(code) or int(code) in NO_FOUL:
        return None
    c = int(code)
    if c in TECHNICAL_FOULS:
        return "technical"
    if c in FLAGRANT_FOULS:
        return "flagrant"
    if c in CLEAR_PATH_FOULS:
        return "clear_path"
    if c in TAKE_FOULS:
        return "transition_take"
    return "regular"


def _trips(fts: pd.DataFrame) -> list[list[int]]:
    """Group free-throw rows (positions in `fts`) into trips.

    Open trips are kept per (kind, team): a technical FT in the middle of a regular trip
    ("1 of 2, technical FT, 2 of 2") does not cut the regular trip.
    """
    trips: list[list[int]] = []
    open_trips: dict[tuple, dict] = {}   # (kind, team) -> {"trip": index, "next": n, "of": m, "period", "secs"}
    for pos, r in enumerate(fts.itertuples(index=False)):
        kind, num, of = FT_CODES[int(r.event_subtype)]
        key = (kind, r.team_id)
        o = open_trips.get(key)
        if num is None:   # unnumbered clear-path FTs: same team and second
            continues = o is not None and o["period"] == r.period and o["secs"] == r.secs_elapsed_game
        else:
            continues = (o is not None and num > 1 and num == o["next"] and of == o["of"] and o["period"] == r.period)
        if continues:
            trips[o["trip"]].append(pos)
        else:
            trips.append([pos])
        idx = o["trip"] if continues else len(trips) - 1
        done = num is not None and num == of
        if done:
            open_trips.pop(key, None)
        else:
            open_trips[key] = {"trip": idx, "next": None if num is None else num + 1, "of": of,
                               "period": r.period, "secs": r.secs_elapsed_game}
    return trips


def link_free_throws(events: pd.DataFrame) -> pd.DataFrame:
    """One row per free throw of one game (columns FT_COLUMNS), in source order."""
    if events["game_id"].nunique() > 1:
        raise FreeThrowError("link_free_throws works on one game at a time")
    ev = events.sort_values("event_seq").reset_index(drop=True)
    fts = ev[ev["event_type"] == "free_throw"].reset_index()      # column "index" = position in ev
    if fts.empty:
        return pd.DataFrame(columns=FT_COLUMNS)
    unknown = sorted(set(fts["event_subtype"].dropna().astype(int)) - set(FT_CODES))
    if unknown or fts["event_subtype"].isna().any():
        raise FreeThrowError(f"{ev['game_id'].iloc[0]}: unknown free-throw codes {unknown or ['NULL']}")

    fouls = ev[ev["event_type"] == "foul"].copy()
    fouls["kind"] = fouls["event_subtype"].map(foul_kind)
    used: set[int] = set()
    rows = []
    for trip_id, trip in enumerate(_trips(fts), start=1):
        first = fts.iloc[trip[0]]
        kind = FT_CODES[int(first["event_subtype"])][0]
        # 2022-23 -> 2024-25: a transition-take free throw has the plain "1 of 1" code; only the
        # take foul (code 31) shows its kind, so a regular free throw may link to a take foul
        fits = {"regular", "transition_take"} if kind == "regular" else {kind}
        cand = fouls[(fouls["period"] == first["period"]) & (fouls["secs_elapsed_game"] == first["secs_elapsed_game"])
                     & ((fouls["team_id"] != first["team_id"]) | fouls["team_id"].isna())
                     & fouls["kind"].isin(fits) & ~fouls["event_seq"].isin(used)]
        before = cand[cand.index < first["index"]]
        after = cand[cand.index > fts.iloc[trip[-1]]["index"]]
        hit = before.iloc[-1] if not before.empty else after.iloc[0] if not after.empty else None
        foul_seq = None if hit is None else int(hit["event_seq"])
        if foul_seq is not None:
            used.add(foul_seq)
            kind = hit["kind"] if kind == "regular" else kind
        for k, pos in enumerate(trip):
            r = fts.iloc[pos]
            _, num, of = FT_CODES[int(r["event_subtype"])]
            if num is None:            # unnumbered: number by order in the trip
                num, of = k + 1, len(trip)
            rows.append({"event_seq": int(r["event_seq"]), "trip_id": trip_id, "ft_kind": kind, "ft_number": num,
                         "ft_of": of, "is_last_ft_of_trip": k == len(trip) - 1, "trip_complete": len(trip) == of,
                         "is_technical_ft": kind == "technical", "foul_event_seq": foul_seq})
    return pd.DataFrame(rows, columns=FT_COLUMNS).sort_values("event_seq").reset_index(drop=True)
