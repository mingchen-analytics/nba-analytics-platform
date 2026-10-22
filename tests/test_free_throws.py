"""Free-throw trips and their fouls (core/free_throws.py) on hand-made sequences and real fixtures."""

from pathlib import Path

import pandas as pd
import pytest

from nba_platform.core.free_throws import FT_CODES, FreeThrowError, link_free_throws

HOME, AWAY = 1610612701, 1610612702
FIXTURES = Path(__file__).parent / "fixtures" / "possessions"


def game(rows):
    """rows: (secs, event_type, event_subtype, team_id)."""
    return pd.DataFrame([{"game_id": "0020400001", "event_seq": i + 1, "period": 1, "secs_elapsed_game": float(t),
                          "event_type": et, "event_subtype": st, "team_id": tm} for i, (t, et, st, tm) in enumerate(rows)])


def test_two_shot_trip_links_to_the_shooting_foul_before_it():
    f = link_free_throws(game([(10, "foul", 2, AWAY), (10, "free_throw", 11, HOME), (10, "free_throw", 12, HOME)]))
    assert f["foul_event_seq"].tolist() == [1, 1] and f["trip_id"].nunique() == 1
    assert f["is_last_ft_of_trip"].tolist() == [False, True] and f["trip_complete"].all()
    assert f[["ft_number", "ft_of"]].values.tolist() == [[1, 2], [2, 2]]


def test_and_one_links_to_the_foul_at_the_same_second():
    f = link_free_throws(game([(10, "shot_made", 1, HOME), (10, "foul", 2, AWAY), (10, "free_throw", 10, HOME)]))
    assert f["foul_event_seq"].tolist() == [2]


def test_foul_listed_after_the_free_throws_is_found():
    f = link_free_throws(game([(10, "free_throw", 11, HOME), (10, "free_throw", 12, HOME), (10, "foul", 2, AWAY)]))
    assert f["foul_event_seq"].tolist() == [3, 3]


def test_foul_of_the_shooting_team_or_another_second_does_not_fit():
    f = link_free_throws(game([(10, "foul", 2, HOME), (9, "foul", 2, AWAY), (10, "free_throw", 10, HOME)]))
    assert f["foul_event_seq"].isna().all()   # unknown -> NULL, never guessed


def test_technical_ft_links_to_a_technical_foul_without_a_team():
    f = link_free_throws(game([(10, "foul", 17, None), (10, "free_throw", 16, HOME)]))
    assert f["foul_event_seq"].tolist() == [1] and f["is_technical_ft"].tolist() == [True]


def test_technical_ft_inside_a_regular_trip_does_not_cut_it():
    """1 of 2, substitution, technical foul, technical FT, 2 of 2 (real pattern, 2004-05)."""
    f = link_free_throws(game([(10, "foul", 2, AWAY), (10, "free_throw", 11, HOME), (10, "substitution", 0, HOME),
                               (10, "foul", 11, AWAY), (10, "free_throw", 16, HOME), (10, "free_throw", 12, HOME)]))
    reg = f[f["ft_kind"] == "regular"]
    assert reg["trip_id"].nunique() == 1 and reg["foul_event_seq"].tolist() == [1, 1] and reg["trip_complete"].all()
    assert f.loc[f["ft_kind"] == "technical", "foul_event_seq"].tolist() == [4]


def test_a_foul_feeds_only_one_trip():
    f = link_free_throws(game([(10, "foul", 1, AWAY), (10, "foul", 1, AWAY), (10, "free_throw", 10, HOME),
                               (10, "free_throw", 10, HOME)]))
    assert sorted(f["foul_event_seq"].tolist()) == [1, 2]


def test_kind_must_match():
    f = link_free_throws(game([(10, "foul", 2, AWAY), (10, "foul", 14, AWAY), (10, "free_throw", 18, HOME),
                               (10, "free_throw", 19, HOME)]))
    assert f["ft_kind"].unique().tolist() == ["flagrant"] and f["foul_event_seq"].tolist() == [2, 2]


def test_unnumbered_clear_path_free_throws_are_numbered_by_order():
    f = link_free_throws(game([(10, "foul", 9, AWAY), (10, "free_throw", 17, HOME), (10, "free_throw", 17, HOME)]))
    assert f[["ft_number", "ft_of"]].values.tolist() == [[1, 2], [2, 2]] and f["foul_event_seq"].tolist() == [1, 1]


def test_trip_stopped_by_a_lane_violation_is_incomplete():
    f = link_free_throws(game([(10, "foul", 2, AWAY), (10, "free_throw", 11, HOME), (10, "turnover", 17, HOME)]))
    assert f["trip_complete"].tolist() == [False] and f["is_last_ft_of_trip"].tolist() == [True]


def test_transition_take_free_throw():
    f = link_free_throws(game([(10, "foul", 31, AWAY), (10, "free_throw", 81, HOME)]))
    assert f[["ft_kind", "foul_event_seq"]].values.tolist() == [["transition_take", 1]]


def test_unknown_free_throw_code_fails():
    with pytest.raises(FreeThrowError):
        link_free_throws(game([(10, "free_throw", 99, HOME)]))


def test_every_code_has_a_kind_and_valid_numbers():
    for code, (kind, num, of) in FT_CODES.items():
        assert kind in {"regular", "technical", "flagrant", "clear_path", "transition_take"}
        assert (num is None) == (of is None) and (num is None or 1 <= num <= of <= 3), code


@pytest.mark.parametrize("case", ["technical_free_throw", "substitution_between_free_throws", "flagrant_foul",
                                  "missed_final_free_throw"])
def test_real_fixtures_trips_with_a_foul_in_the_window_are_linked(case):
    """Fixtures are short windows; some start at the free throw, without the foul row."""
    df = pd.read_csv(FIXTURES / f"{case}.csv", dtype={"game_id": str})
    for _, part in df.groupby("fixture"):
        f = link_free_throws(part).merge(part[["event_seq", "secs_elapsed_game", "team_id"]], on="event_seq")
        assert len(f) == (part["event_type"] == "free_throw").sum()
        fouls = part[part["event_type"] == "foul"]
        for r in f.itertuples():
            has_foul = ((fouls["secs_elapsed_game"] == r.secs_elapsed_game) & (fouls["team_id"] != r.team_id)).any()
            if has_foul:
                assert pd.notna(r.foul_event_seq), (case, r.event_seq)
    if case == "technical_free_throw":
        f = pd.concat([link_free_throws(p) for _, p in df.groupby("fixture")])
        assert f["is_technical_ft"].any()


def test_plain_one_of_one_after_a_take_foul_is_a_transition_take_free_throw():
    """2022-23 -> 2024-25: the transition-take FT has the plain "1 of 1" code (10); the take foul is code 31."""
    f = link_free_throws(game([(10, "foul", 31, AWAY), (10, "free_throw", 10, HOME)]))
    assert f[["ft_kind", "foul_event_seq"]].values.tolist() == [["transition_take", 1]]
