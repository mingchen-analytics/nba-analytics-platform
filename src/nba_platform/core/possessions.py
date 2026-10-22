"""Possessions (possession code, steps 4-7): where possessions end, possession and chance ids,
one summary row per possession, and possession x stint segments.

Every rule is in CLAUDE.md "Possession rules" and config/rules.yaml; the profile used is
recorded (`rules_version`). Inputs come from the earlier steps: core/stints.py,
core/free_throws.py, core/rebounds.py. Pure functions; nothing here touches the database.

A possession ENDS on (source order, owner 2026-10-21):
- a made field goal by the offense, unless the offense gets a free-throw trip at the same second
  (and-1, or a flagrant foul right after the basket): then the trip decides;
- a real defensive rebound (core/rebounds.py);
- a turnover by the offense, including the rows the source labels "No Turnover" (action type 0):
  they carry a credited steal, so they are turnovers; pbpstats counts them too (2004-05
  comparison: 98.37 % -> 98.54 % identical; rules.yaml `turnovers`);
- the made last free throw of a non-technical trip ("n of n"), except when the fouled team keeps
  the ball: flagrant, clear-path, transition-take, away-from-play and inbound-foul free throws
  (one possession with the retained ball; owner 2026-10-21, both profiles = pbpstats' reference
  data; away-from-play and inbound with no clock condition, as pbpstats). The made last FT ends
  the possession even when the other team fouls again at the same second (owner, option (a)
  in both profiles; pbpstats keeps the possession open there, so we differ on purpose);
- a jump ball after which the other team has the ball (owner: decided by the next event that
  shows who has the ball: a shot, a turnover, a non-technical free throw or a real rebound;
  fouls are skipped because their team is the fouling team);
- the end of the period.

Not part of any possession (possession_id NULL): technical free throws, and non-technical
free throws awarded to a team after its possession already ended on a made last free throw at
the same second (`is_between_possessions_ft`, owner 2026-10-21). Events in the dead ball
between two possessions belong to the next one; rows after a period-end row stay with the
possession that ended there.

Chances: a real offensive rebound by the offense starts a new chance (rules.yaml `chances`);
`chance_id` is the chance number within the possession (1, 2, ...).

Diagnostics are counted, never hidden: a control event by the team without the ball closes
the open possession (`end_type = 'implied'`) and opens one for that team.
"""

from __future__ import annotations

import pandas as pd

from nba_platform.core.stints import period_bounds

POSSESSION_COLUMNS = [
    "game_id", "possession_id", "offense_team_id", "defense_team_id", "period", "start_secs", "end_secs",
    "start_event_seq", "end_event_seq", "start_type", "end_type", "points", "num_chances",
    "secs_remaining_period_at_start", "secs_remaining_game_at_start", "start_margin_offense", "offense_is_home",
    "is_end_of_period_heave", "is_garbage_time", "is_after_timeout", "timeout_team_id", "rules_version"]
EVENT_COLUMNS = ["event_seq", "possession_id", "chance_id", "is_between_possessions_ft"]
SEGMENT_COLUMNS = ["game_id", "possession_id", "segment_seq", "stint_id", "start_event_seq", "end_event_seq",
                   "start_secs", "end_secs"]

# foul codes (core/free_throws.py, NBA action types)
AWAY_FROM_PLAY_FOUL, INBOUND_FOUL = 6, 5
AND_ONE_FOULS = {2, 29, 14, 15}                   # shooting, shooting block, flagrant 1 / 2
PLAYER_COLS = [f"{s}_p{k}" for s in ("home", "away") for k in range(1, 6)]


class PossessionError(ValueError):
    """Possessions cannot be built from these inputs (the pipeline must stop)."""


def _check_rules(rules: dict) -> None:
    jb = rules["jump_ball"]
    retained = rules["free_throws_with_ball_retained"]
    ok = (rules["chances"]["boundaries"] == ["offensive_rebound"] and rules["event_order"] == "source"
          and jb["possession_change"] == "other_team_gains_control" and not jb["new_chance"]
          and rules["free_throws_between_possessions"]["treat_like_technical_ft"]
          and not retained["new_possession_after_last_ft"]
          and set(retained["same_possession"]) <= {"flagrant", "clear_path", "transition_take", "away_from_play", "inbound"}
          and rules["free_throws_between_possessions"]["made_last_ft_ends_even_if_other_team_fouls_at_same_second"]
          and rules["turnovers"]["no_turnover_rows_end_possession"]
          and rules["end_of_period"]["clock_precision"] == "exact"
          and rules["after_timeout"]["window"] == "dead_ball_between_possessions")
    if not ok:
        raise PossessionError("rules.yaml has possession rules this code does not implement; update the code first")


def _na(x) -> bool:
    return x is None or x is pd.NA or (isinstance(x, float) and x != x)


def _prepare(events, free_throws, rebounds, stint_ids) -> pd.DataFrame:
    order = events.sort_values("event_seq").index
    ev = events.loc[order].reset_index(drop=True).copy()
    ev["stint_id"] = stint_ids.reindex(order).values if stint_ids is not None else None
    ft = free_throws.set_index("event_seq")
    for c in ("ft_kind", "ft_number", "ft_of", "is_last_ft_of_trip", "is_technical_ft", "foul_event_seq"):
        ev[c] = ev["event_seq"].map(ft[c]) if len(ft) else None
    ev["is_technical_ft"] = ev["is_technical_ft"].fillna(False).astype(bool)
    foul_code = dict(zip(ev["event_seq"], ev["event_subtype"]))
    ev["linked_foul_code"] = ev["foul_event_seq"].map(lambda s: None if _na(s) else foul_code.get(int(s)))
    rb = rebounds.set_index("event_seq")
    real = ev["event_seq"].map(rb["is_real_rebound"]) if len(rb) else pd.Series(False, index=ev.index)
    ev["is_real_rebound"] = real.fillna(False).astype(bool)
    for c in ("player2_id", "player3_id"):
        if c not in ev:
            ev[c] = None
    # nullable integer columns (pd.NA) -> plain Python values with None, so comparisons never raise
    for c in ("team_id", "event_subtype", "player1_id", "player2_id", "player3_id", "stint_id", "ft_number", "ft_of",
              "foul_event_seq", "linked_foul_code", "home_score", "away_score"):
        if c in ev:
            ev[c] = ev[c].astype(object).where(ev[c].notna(), None)
    return ev


def _is_control(r) -> bool:
    """Does this event show which team has the ball?"""
    if _na(r.team_id):
        return False
    if r.event_type in ("shot_made", "shot_missed"):
        return True
    if r.event_type == "turnover":
        return True
    if r.event_type == "free_throw":
        return not r.is_technical_ft
    if r.event_type == "rebound":
        return bool(r.is_real_rebound)
    return False


def ball_retained_kind(r) -> str | None:
    """The rules.yaml `free_throws_with_ball_retained` kind of a free throw, or None."""
    if r.ft_kind in ("flagrant", "clear_path", "transition_take"):
        return r.ft_kind
    code = None if _na(r.linked_foul_code) else int(r.linked_foul_code)
    if r.ft_kind == "regular" and code == AWAY_FROM_PLAY_FOUL:
        return "away_from_play"
    if r.ft_kind == "regular" and code == INBOUND_FOUL:
        return "inbound"
    return None


def _ft_ends_possession(r, same_possession: set[str]) -> bool:
    """Does the free throw r end the possession (made, last of a non-technical trip, ball not retained)?"""
    if r.is_technical_ft or r.points <= 0 or _na(r.ft_number) or int(r.ft_number) != int(r.ft_of):
        return False
    return ball_retained_kind(r) not in same_possession


def _and_one_follows(recs, i, r) -> bool:
    """Is this make an and-1 (or followed by a flagrant foul)? Then the possession does not end on it.

    True when, at the same second after the make, the defense commits a shooting or flagrant
    foul, or the shooting team gets a non-technical free throw. A lane violation can cancel the
    free throw; the possession then ends on that turnover (as pbpstats).
    """
    for n in recs[i + 1:]:
        if n.period != r.period or n.secs_elapsed_game != r.secs_elapsed_game:
            return False
        if n.event_type == "free_throw" and n.team_id == r.team_id and not n.is_technical_ft:
            return True
        if (n.event_type == "foul" and not _na(n.team_id) and n.team_id != r.team_id
                and not _na(n.event_subtype) and int(n.event_subtype) in AND_ONE_FOULS):
            return True
    return False


def _next_control_team(recs, i):
    for n in recs[i + 1:]:
        if n.period != recs[i].period:
            return None
        if _is_control(n):
            return n.team_id
    return None


def build_possessions(events: pd.DataFrame, free_throws: pd.DataFrame, rebounds: pd.DataFrame,
                      stints: pd.DataFrame, stint_ids: pd.Series, game: pd.Series, rules: dict
                      ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    """(possessions, event_links, segments, diagnostics) for one game."""
    _check_rules(rules)
    ev = _prepare(events, free_throws, rebounds, stint_ids)
    recs = list(ev.itertuples(index=False))
    game_id = recs[0].game_id
    home, away = int(game["home_team_id"]), int(game["away_team_id"])
    other = {home: away, away: home}
    same_possession = set(rules["free_throws_with_ball_retained"]["same_possession"])
    diag = {"implied_ends": 0, "offense_corrected": 0, "between_possessions_fts": 0, "possessions_without_offense": 0}

    poss: list[dict] = []
    links: dict[int, tuple] = {}   # event position -> (possession index or None, chance, is_between)
    cur = None                    # the open possession
    pending = {"start_type": "period_start", "offense": None, "end_secs": None, "end_type": None}
    after_period_end = False      # rows after a period_end row (0:00 bookkeeping) stay with that possession

    def open_poss(i, r):
        nonlocal cur
        start = pending["end_secs"] if pending["end_secs"] is not None else period_bounds(int(r.period), rules)[0]
        cur = {"offense": pending["offense"], "period": int(r.period), "start_secs": start,
               "start_event_seq": int(r.event_seq), "start_type": pending["start_type"], "chances": 1,
               "controlled": False, "timeout": False, "timeout_team": None, "first_pos": i}

    def close(i, end_type, next_offense, next_start_type):
        nonlocal cur
        r = recs[i]
        cur.update(end_secs=float(r.secs_elapsed_game), end_event_seq=int(r.event_seq), end_type=end_type)
        poss.append(cur)
        cur = None
        pending.update(start_type=next_start_type, offense=next_offense, end_secs=float(r.secs_elapsed_game),
                       end_type=end_type)

    for i, r in enumerate(recs):
        prev_period = recs[i - 1].period if i else None
        # a period_start row that arrives while this period's possession is still open and without any
        # ball control joins it: a duplicated start row, or a technical foul listed before the start row
        repeated_start = (r.event_type == "period_start" and cur is not None and int(r.period) == cur["period"]
                          and cur["start_type"] == "period_start" and not cur["controlled"])
        new_period = ((r.event_type == "period_start" and not repeated_start)
                      or (cur is not None and int(r.period) != cur["period"])
                      or (after_period_end and r.period != prev_period))
        if new_period:
            if cur is not None:
                close(i - 1, "period_end", None, "period_start")
            pending.update(start_type="period_start", offense=None, end_secs=None, end_type=None)
            after_period_end = False
        # technical free throws are outside every possession (also when listed after the period_end row)
        if r.event_type == "free_throw" and r.is_technical_ft:
            links[i] = (None, None, False)
            continue
        if after_period_end:
            links[i] = (len(poss) - 1, poss[-1]["chances"], False)
            continue
        # free throws for a team whose possession just ended on a made last free throw at this second
        if (r.event_type == "free_throw" and pending["end_type"] == "made_ft" and pending["offense"] is not None
                and r.team_id != pending["offense"] and (cur is None or not cur["controlled"])
                and r.secs_elapsed_game == pending["end_secs"]):
            links[i] = (None, None, True)
            diag["between_possessions_fts"] += 1
            continue
        if cur is None:
            open_poss(i, r)
        control = _is_control(r)
        if control:
            if cur["offense"] is None:
                cur["offense"] = r.team_id
            elif r.team_id != cur["offense"] and r.event_type != "rebound":
                if not cur["controlled"]:
                    cur["offense"] = r.team_id
                    diag["offense_corrected"] += 1
                else:   # the source never showed the end of the previous possession
                    close(i - 1, "implied", r.team_id, "implied")
                    diag["implied_ends"] += 1
                    open_poss(i, r)
                    cur["offense"] = r.team_id
            cur["controlled"] = cur["controlled"] or r.event_type != "rebound" or r.team_id == cur["offense"]
        elif r.event_type == "timeout" and not cur["controlled"]:
            cur["timeout"] = True
            if not _na(r.team_id):
                cur["timeout_team"] = int(r.team_id)
        links[i] = (len(poss), cur["chances"], False)
        offense = cur["offense"]

        if r.event_type == "period_end":
            close(i, "period_end", None, "period_start")
            after_period_end = True
        elif r.event_type == "shot_made" and r.team_id == offense:
            if not _and_one_follows(recs, i, r):
                close(i, "made_fg", other.get(int(r.team_id)), "after_made_shot")
        elif r.event_type == "rebound" and r.is_real_rebound:
            if offense is not None and r.team_id == offense:
                cur["chances"] += 1
            else:
                close(i, "defensive_rebound", r.team_id, "after_defensive_rebound")
        elif r.event_type == "turnover" and control and r.team_id == offense:
            live = not _na(r.player2_id) or not _na(r.player3_id)
            close(i, "turnover", other.get(int(r.team_id)), "after_steal" if live else "after_dead_ball_turnover")
        elif r.event_type == "free_throw" and r.team_id == offense:
            if _ft_ends_possession(r, same_possession):
                close(i, "made_ft", other.get(int(r.team_id)), "after_free_throw")
        elif r.event_type == "jump_ball" and offense is not None and cur["controlled"]:
            nxt = _next_control_team(recs, i)
            if nxt is not None and nxt != offense:
                close(i, "jump_ball", nxt, "after_jump_ball")
    if cur is not None:
        close(len(recs) - 1, "period_end", None, "period_start")

    # ------------------------------------------------------------------ summary rows
    ev_links = pd.DataFrame([{"event_seq": int(recs[i].event_seq), "possession_id": None if p is None else p + 1,
                              "chance_id": c, "is_between_possessions_ft": b} for i, (p, c, b) in sorted(links.items())],
                            columns=EVENT_COLUMNS)
    members_of: dict[int, list[int]] = {}
    for i, (p, _, _) in links.items():
        if p is not None:
            members_of.setdefault(p, []).append(i)
    # running score before each event = the score after the previous event
    score_before = ev[["home_score", "away_score"]].ffill().fillna(0).shift(1).fillna(0).astype(int).values.tolist()
    n_periods = int(ev["period"].max()) if _na(game.get("num_periods")) else int(game["num_periods"])
    game_end = period_bounds(n_periods, rules)[1]
    starters = {int(x) for x in stints.iloc[0][PLAYER_COLS]}
    on_floor_of = {int(s.stint_id): {int(getattr(s, c)) for c in PLAYER_COLS} for s in stints.itertuples()}
    threshold = rules["end_of_period"]["end_of_period_threshold_secs"]
    rows = []
    for k, p in enumerate(poss):
        offense = p["offense"]
        if offense is None:
            diag["possessions_without_offense"] += 1
        pts = 0 if offense is None else int(sum(recs[i].points for i in members_of.get(k, [])
                                                if recs[i].team_id == offense and not recs[i].is_technical_ft))
        hs, as_ = score_before[p["first_pos"]]
        left = period_bounds(p["period"], rules)[1] - p["start_secs"]
        sid = recs[p["first_pos"]].stint_id
        on_floor = set() if _na(sid) else on_floor_of.get(int(sid), set())
        rows.append({"game_id": game_id, "possession_id": k + 1,
                     "offense_team_id": offense, "defense_team_id": None if offense is None else other[int(offense)],
                     "period": p["period"], "start_secs": p["start_secs"], "end_secs": p["end_secs"],
                     "start_event_seq": p["start_event_seq"], "end_event_seq": p["end_event_seq"],
                     "start_type": p["start_type"], "end_type": p["end_type"], "points": pts,
                     "num_chances": p["chances"],
                     "secs_remaining_period_at_start": left, "secs_remaining_game_at_start": game_end - p["start_secs"],
                     "start_margin_offense": None if offense is None else (hs - as_ if offense == home else as_ - hs),
                     "offense_is_home": None if offense is None else offense == home,
                     "is_end_of_period_heave": bool(left <= threshold and pts == 0), "is_garbage_time": False,
                     "is_after_timeout": p["timeout"], "timeout_team_id": p["timeout_team"],
                     "starters_on_floor": len(on_floor & starters), "rules_version": rules["rules_version"]})
    pos = pd.DataFrame(rows)
    pos["is_garbage_time"] = garbage_time(pos, rules)
    return pos[POSSESSION_COLUMNS], ev_links, segments(recs, links, stints, pos, game_id), diag


def garbage_time(pos: pd.DataFrame, rules: dict) -> pd.Series:
    """Cleaning the Glass garbage time (rules.yaml `garbage_time`), retroactive to the game's end.

    Needs columns period, start_secs, start_margin_offense and starters_on_floor (starters = the
    lineup on the game's first event, both teams combined).
    """
    gt = rules["garbage_time"]
    if gt["definition"] != "cleaning_the_glass" or not gt["retroactive_until_game_end"]:
        raise PossessionError(f"garbage-time rule not implemented: {gt}")

    def threshold(period, start_secs):
        if period not in gt["periods"]:
            return None
        left = period_bounds(period, rules)[1] - start_secs
        for band in gt["margin_thresholds"]:
            lo, hi = band["secs_remaining_min"], band["secs_remaining_max"]
            if lo < left <= hi or (lo == 0 and left == 0):
                return band["min_margin"]
        return None

    cond = []
    for r in pos.itertuples():
        t = threshold(r.period, r.start_secs)
        cond.append(t is not None and not _na(r.start_margin_offense) and abs(r.start_margin_offense) >= t
                    and r.starters_on_floor <= gt["max_combined_starters_on_court"])
    # retroactive: only if the condition holds from this possession to the end of the game
    out, ok = [False] * len(cond), True
    for k in range(len(cond) - 1, -1, -1):
        ok = ok and cond[k]
        out[k] = ok
    return pd.Series(out, index=pos.index)


def segments(recs, links, stints, pos, game_id) -> pd.DataFrame:
    """One row per (possession, stint) stretch of consecutive events."""
    st = {int(r.stint_id): (float(r.start_secs), float(r.end_secs)) for r in stints.itertuples()}
    pp = {int(r.possession_id): (float(r.start_secs), float(r.end_secs)) for r in pos.itertuples()}
    rows, last = [], None
    for i, (p, _, _) in sorted(links.items()):
        if p is None:
            continue
        pid, sid, seq = p + 1, int(recs[i].stint_id), int(recs[i].event_seq)
        if last is not None and last["possession_id"] == pid and last["stint_id"] == sid:
            last["end_event_seq"] = seq
            continue
        n = 1 + (last["segment_seq"] if last is not None and last["possession_id"] == pid else 0)
        last = {"game_id": game_id, "possession_id": pid, "segment_seq": n, "stint_id": sid,
                "start_event_seq": seq, "end_event_seq": seq,
                "start_secs": max(pp[pid][0], st[sid][0]), "end_secs": min(pp[pid][1], st[sid][1])}
        rows.append(last)
    return pd.DataFrame(rows, columns=SEGMENT_COLUMNS)
