"""Stint rules (CLAUDE.md "lineups on court", rules.yaml `stints`) on small hand-made games
and on the real substitution-between-free-throws fixture."""

from pathlib import Path

import pandas as pd
import pytest

from nba_platform.core.stints import StintError, build_stints, period_bounds, player_seconds
from nba_platform.rules import load_rules

RULES = load_rules(profile="pbpstats_compat")
H0, A0 = [1, 2, 3, 4, 5], [11, 12, 13, 14, 15]
FIXTURES = Path(__file__).parent / "fixtures" / "possessions"


def game(rows):
    """rows: (period, secs, event_type, home_ids, away_ids) -> (events, lineups)."""
    ev = pd.DataFrame([{"game_id": "0020400001", "event_seq": i + 1, "period": p, "secs_elapsed_game": float(t),
                        "event_type": et} for i, (p, t, et, _, _) in enumerate(rows)])
    lu = pd.DataFrame([{"game_id": "0020400001", "event_seq": i + 1, "home_player_ids": h, "away_player_ids": a}
                       for i, (_, _, _, h, a) in enumerate(rows)])
    return ev, lu


def sub(h, out, inn):
    return [inn if p == out else p for p in h]


def test_one_stint_per_period_without_substitutions():
    ev, lu = game([(1, 0, "period_start", H0, A0), (1, 100, "shot_made", H0, A0), (2, 720, "period_start", H0, A0),
                   (2, 800, "shot_missed", H0, A0)])
    st, sid = build_stints(ev, lu, RULES)
    assert st[["start_secs", "end_secs", "start_reason"]].values.tolist() == [[0.0, 720.0, "period_start"],
                                                                            [720.0, 1440.0, "period_start"]]
    assert sid.tolist() == [1, 1, 2, 2]


def test_consecutive_substitutions_at_the_same_second_are_one_stint():
    h1 = sub(H0, 5, 6)
    h2 = sub(h1, 4, 7)
    ev, lu = game([(1, 0, "period_start", H0, A0), (1, 50, "foul", H0, A0), (1, 50, "substitution", h1, A0),
                   (1, 50, "substitution", h2, A0), (1, 60, "shot_made", h2, A0)])
    st, sid = build_stints(ev, lu, RULES)
    assert len(st) == 2 and st.iloc[1][[f"home_p{i}" for i in range(1, 6)]].tolist() == h2  # lineup after the last
    assert sid.tolist() == [1, 1, 2, 2, 2]
    assert (st.iloc[1]["start_secs"], st.iloc[1]["start_event_seq"]) == (50.0, 3)


def test_an_event_between_substitutions_keeps_them_apart():
    """FT 1 -> sub -> FT 2 -> sub at one second: each FT keeps the lineup on the floor."""
    h1, h2 = sub(H0, 5, 6), sub(sub(H0, 5, 6), 4, 7)
    ev, lu = game([(1, 0, "period_start", H0, A0), (1, 50, "free_throw", H0, A0), (1, 50, "substitution", h1, A0),
                   (1, 50, "free_throw", h1, A0), (1, 50, "substitution", h2, A0), (1, 70, "rebound", h2, A0)])
    st, sid = build_stints(ev, lu, RULES)
    assert sid.tolist() == [1, 1, 2, 2, 3, 3]
    assert st["end_secs"].tolist() == [50.0, 50.0, 720.0]  # the middle stint lasts 0 s and is kept


def test_substitutions_at_different_seconds_are_separate_stints():
    h1, h2 = sub(H0, 5, 6), sub(sub(H0, 5, 6), 4, 7)
    ev, lu = game([(1, 0, "period_start", H0, A0), (1, 50, "substitution", h1, A0), (1, 51, "substitution", h2, A0)])
    st, _ = build_stints(ev, lu, RULES)
    assert st["start_secs"].tolist() == [0.0, 50.0, 51.0]


def test_lineup_change_without_a_substitution_row_is_kept_and_labelled():
    ev, lu = game([(1, 0, "period_start", H0, A0), (1, 100, "shot_made", sub(H0, 5, 9), A0)])
    st, _ = build_stints(ev, lu, RULES)
    assert st["start_reason"].tolist() == ["period_start", "lineup_change"]


def test_same_players_in_another_order_is_not_a_lineup_change():
    ev, lu = game([(1, 0, "period_start", H0, A0), (1, 100, "shot_made", H0[::-1], A0)])
    st, _ = build_stints(ev, lu, RULES)
    assert len(st) == 1 and st.iloc[0][[f"home_p{i}" for i in range(1, 6)]].tolist() == H0  # source order kept


def test_period_bounds_regulation_and_overtime():
    assert period_bounds(1, RULES) == (0.0, 720.0) and period_bounds(4, RULES) == (2160.0, 2880.0)
    assert period_bounds(5, RULES) == (2880.0, 3180.0) and period_bounds(6, RULES) == (3180.0, 3480.0)


def test_team_seconds_add_up_to_game_length():
    h1 = sub(H0, 5, 6)
    ev, lu = game([(p, (p - 1) * 720, "period_start", H0, A0) for p in (1, 2, 3, 4)]
                  + [(4, 2500, "substitution", h1, A0)])
    ev = ev.sort_values(["period", "secs_elapsed_game"]).reset_index(drop=True)
    ev["event_seq"] = range(1, len(ev) + 1)
    lu["event_seq"] = range(1, len(lu) + 1)
    st, _ = build_stints(ev, lu, RULES)
    ps = player_seconds(st)
    assert ps.groupby("side")["secs"].sum().tolist() == [5 * 2880.0, 5 * 2880.0]
    assert ps.set_index("player_id").loc[[5, 6], "secs"].tolist() == [2500.0, 380.0]


@pytest.mark.parametrize("home", [[1, 2, 3, 4], [1, 2, 3, 4, 4], [1, 2, 3, 4, 11]])
def test_invalid_lineups_fail(home):
    ev, lu = game([(1, 0, "period_start", home, A0)])
    with pytest.raises(StintError):
        build_stints(ev, lu, RULES)


def test_events_and_lineups_must_match():
    ev, lu = game([(1, 0, "period_start", H0, A0), (1, 10, "shot_made", H0, A0)])
    with pytest.raises(StintError):
        build_stints(ev, lu.iloc[:1], RULES)


@pytest.mark.parametrize("which", ["A", "B"])
def test_real_substitution_between_free_throws(which):
    df = pd.read_csv(FIXTURES / "substitution_between_free_throws.csv", dtype={"game_id": str})
    df = df[df["fixture"] == which].sort_values("event_seq").reset_index(drop=True)
    lu = pd.DataFrame({"game_id": df["game_id"], "event_seq": df["event_seq"],
                       "home_player_ids": df["home_player_ids"].str.split("|").map(lambda x: [int(p) for p in x]),
                       "away_player_ids": df["away_player_ids"].str.split("|").map(lambda x: [int(p) for p in x])})
    st, sid = build_stints(df, lu, RULES)
    fts = df.index[df["event_type"] == "free_throw"]
    subs_between = df.index[(df["event_type"] == "substitution") & (df.index > fts.min()) & (df.index < fts.max())]
    assert len(subs_between) > 0
    # the free throws before and after the substitution belong to different stints
    assert sid[fts.min()] != sid[fts.max()]
    for i in fts:
        row = st.set_index("stint_id").loc[sid[i]]
        on_floor = {int(p) for p in lu.loc[i, "home_player_ids"] + lu.loc[i, "away_player_ids"]}
        assert {int(row[f"{s}_p{k}"]) for s in ("home", "away") for k in range(1, 6)} == on_floor
