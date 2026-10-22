"""Rebounds: which miss each rebound follows, whether it is a real rebound, offensive or defensive
(possession code, step 3).

Rules (CLAUDE.md "Possession rules", rules.yaml `team_rebound_after_nonfinal_ft`):
1. A rebound belongs to the most recent miss before it in the same period (source order):
   a missed field goal or a missed free throw.
2. It is a **real** rebound only after a missed field goal or a missed **last** free throw of a
   trip that is not technical. After a missed non-final free throw (owner: "not a rebound;
   ignore") or a missed technical free throw (no live ball; technical FTs never start or end a
   possession) the row is kept but `is_real_rebound` is False. Same as pbpstats, where only an
   "end" free throw can be followed by a real rebound.
3. Offensive = the rebounding team is the team that missed; defensive otherwise. Team rebounds
   (no player) count the same way.
4. A rebound with no miss before it in the period, or without a team, is not real
   (`miss_kind = 'none'` / offensive NULL) and is counted.

Pure functions; nothing here touches the database.
"""

from __future__ import annotations

import pandas as pd

REBOUND_COLUMNS = ["event_seq", "missed_event_seq", "miss_kind", "is_real_rebound", "is_offensive"]


class ReboundError(ValueError):
    """Rebounds cannot be classified (the pipeline must stop)."""


def classify_rebounds(events: pd.DataFrame, free_throws: pd.DataFrame, rules: dict) -> pd.DataFrame:
    """One row per rebound of one game.

    `free_throws`: the output of `core.free_throws.link_free_throws` for the same game.
    """
    if rules["team_rebound_after_nonfinal_ft"] != "ignore":
        raise ReboundError(f"rule not implemented: team_rebound_after_nonfinal_ft = {rules['team_rebound_after_nonfinal_ft']}")
    ev = events.sort_values("event_seq")
    ft = free_throws.set_index("event_seq")
    rows, last = [], None   # last = (event_seq, kind, team_id)
    period = None
    for r in ev.itertuples(index=False):
        if r.period != period:
            period, last = r.period, None
        if r.event_type == "shot_missed":
            last = (int(r.event_seq), "field_goal", r.team_id)
        elif r.event_type == "free_throw" and r.points == 0:
            f = ft.loc[r.event_seq]
            kind = ("technical_ft" if f["is_technical_ft"] else "last_ft" if f["is_last_ft_of_trip"] else "non_final_ft")
            last = (int(r.event_seq), kind, r.team_id)
        elif r.event_type == "rebound":
            if last is None:
                rows.append({"event_seq": int(r.event_seq), "missed_event_seq": None, "miss_kind": "none",
                             "is_real_rebound": False, "is_offensive": None})
                continue
            seq, kind, miss_team = last
            real = kind in ("field_goal", "last_ft") and pd.notna(r.team_id)
            offensive = None if pd.isna(r.team_id) or pd.isna(miss_team) else bool(r.team_id == miss_team)
            rows.append({"event_seq": int(r.event_seq), "missed_event_seq": seq, "miss_kind": kind,
                         "is_real_rebound": bool(real), "is_offensive": offensive})
            last = None     # a miss is rebounded once
    return pd.DataFrame(rows, columns=REBOUND_COLUMNS)
