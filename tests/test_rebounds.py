"""Rebound classification (core/rebounds.py) on hand-made sequences and real fixtures."""

from pathlib import Path

import pandas as pd
import pytest

from nba_platform.core.free_throws import link_free_throws
from nba_platform.core.rebounds import ReboundError, classify_rebounds
from nba_platform.rules import load_rules

RULES = load_rules(profile="pbpstats_compat")
HOME, AWAY = 1610612701, 1610612702
FIXTURES = Path(__file__).parent / "fixtures" / "possessions"


def game(rows):
    """rows: (period, event_type, event_subtype, team_id, points)."""
    return pd.DataFrame([{"game_id": "0020400001", "event_seq": i + 1, "period": p, "secs_elapsed_game": 10.0,
                          "event_type": et, "event_subtype": st, "team_id": tm, "points": pts}
                         for i, (p, et, st, tm, pts) in enumerate(rows)])


def classify(ev):
    return classify_rebounds(ev, link_free_throws(ev), RULES).set_index("event_seq")


def test_offensive_and_defensive_after_a_missed_shot():
    r = classify(game([(1, "shot_missed", 1, HOME, 0), (1, "rebound", 0, HOME, 0),
                       (1, "shot_missed", 1, HOME, 0), (1, "rebound", 0, AWAY, 0)]))
    assert [bool(r.loc[2, "is_offensive"]), bool(r.loc[4, "is_offensive"])] == [True, False]
    assert r["is_real_rebound"].all()


def test_team_rebound_after_a_non_final_free_throw_is_ignored():
    r = classify(game([(1, "foul", 2, AWAY, 0), (1, "free_throw", 11, HOME, 0), (1, "rebound", 0, HOME, 0),
                       (1, "free_throw", 12, HOME, 0), (1, "rebound", 0, AWAY, 0)]))
    assert (r.loc[3, "miss_kind"], bool(r.loc[3, "is_real_rebound"])) == ("non_final_ft", False)
    assert (r.loc[5, "miss_kind"], bool(r.loc[5, "is_real_rebound"]), bool(r.loc[5, "is_offensive"])) == ("last_ft", True, False)


def test_rebound_after_a_missed_technical_free_throw_is_not_real():
    r = classify(game([(1, "foul", 17, AWAY, 0), (1, "free_throw", 16, HOME, 0), (1, "rebound", 0, HOME, 0)]))
    assert (r.loc[3, "miss_kind"], bool(r.loc[3, "is_real_rebound"])) == ("technical_ft", False)


def test_rebound_without_a_miss_in_the_period_is_not_real():
    r = classify(game([(1, "shot_missed", 1, HOME, 0), (2, "rebound", 0, AWAY, 0)]))
    assert (r.loc[2, "miss_kind"], bool(r.loc[2, "is_real_rebound"])) == ("none", False)


def test_made_free_throw_is_not_a_miss():
    r = classify(game([(1, "shot_missed", 1, AWAY, 0), (1, "rebound", 0, HOME, 0), (1, "foul", 2, AWAY, 0),
                       (1, "free_throw", 10, HOME, 1), (1, "rebound", 0, HOME, 0)]))
    assert r.loc[5, "miss_kind"] == "none"   # the earlier miss was already rebounded


def test_other_rule_value_fails():
    with pytest.raises(ReboundError):
        classify_rebounds(game([]), pd.DataFrame(columns=["event_seq"]), {"team_rebound_after_nonfinal_ft": "count"})


@pytest.mark.parametrize("case", ["offensive_rebound", "missed_final_free_throw", "team_rebound_after_non_final_ft"])
def test_real_fixtures(case):
    df = pd.read_csv(FIXTURES / f"{case}.csv", dtype={"game_id": str})
    for _, part in df.groupby("fixture"):
        r = classify_rebounds(part, link_free_throws(part), RULES)
        assert len(r) == (part["event_type"] == "rebound").sum()
        if case == "offensive_rebound":
            assert (r["is_real_rebound"] & (r["is_offensive"] == True)).sum() >= 1  # noqa: E712
        if case == "team_rebound_after_non_final_ft":
            assert (r["miss_kind"] == "non_final_ft").any() and not r.loc[r["miss_kind"] == "non_final_ft", "is_real_rebound"].any()
