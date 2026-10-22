"""Possession rules (CLAUDE.md "Possession rules") on real 2004-05 sequences.

Fixtures: tests/fixtures/possessions/ (short windows of real games, IDs and codes only; see
README there). The expected values follow from the written rules, not from running the code.
(2026-10-21: the code is Claude-written at the owner's request; the owner reviews.)
"""

from pathlib import Path

import pandas as pd
import pytest

from nba_platform.core.free_throws import link_free_throws
from nba_platform.core.possessions import build_possessions, garbage_time
from nba_platform.core.rebounds import classify_rebounds
from nba_platform.core.stints import build_stints
from nba_platform.rules import load_rules

RULES = load_rules(profile="pbpstats_compat")
FIXTURES = Path(__file__).parent / "fixtures" / "possessions"
CASES = [
    "end_of_period", "substitution_between_free_throws", "offensive_rebound", "flagrant_foul",
    "technical_free_throw", "team_rebound_after_non_final_ft", "missed_final_free_throw",
    "jump_ball", "start_type", "garbage_time",
]
REQUIRED = ["fixture", "game_id", "event_seq", "source_event_num", "period", "clock", "secs_elapsed_game",
            "team_id", "event_type", "event_subtype", "player1_id", "player2_id", "points",
            "home_score", "away_score", "home_player_ids", "away_player_ids"]


def load_fixture(case: str, which: str) -> pd.DataFrame:
    df = pd.read_csv(FIXTURES / f"{case}.csv", dtype={"game_id": str})
    return df[df["fixture"] == which].sort_values("event_seq").reset_index(drop=True)


@pytest.mark.parametrize("case", CASES)
def test_fixture_integrity(case):
    df = pd.read_csv(FIXTURES / f"{case}.csv", dtype={"game_id": str})
    assert set(REQUIRED) <= set(df.columns)
    assert sorted(df["fixture"].unique()) == ["A", "B"]
    assert "description" not in df.columns  # no source text in committed fixtures
    for _, part in df.groupby("fixture"):
        assert part["game_id"].nunique() == 1
        assert part["event_seq"].is_monotonic_increasing


# ------------------------------------------------------------------ helpers

def run(case: str, which: str):
    """Build stints, free throws, rebounds and possessions for one fixture window."""
    ev = load_fixture(case, which)
    lu = pd.DataFrame({"game_id": ev["game_id"], "event_seq": ev["event_seq"],
                       "home_player_ids": ev["home_player_ids"].str.split("|").map(lambda x: [int(p) for p in x]),
                       "away_player_ids": ev["away_player_ids"].str.split("|").map(lambda x: [int(p) for p in x])})
    home_players = set(lu["home_player_ids"].iloc[0])
    teams = ev.dropna(subset=["team_id", "player1_id"])
    home = teams.loc[teams["player1_id"].astype(int).isin(home_players), "team_id"].mode()[0]
    away = [t for t in ev["team_id"].dropna().unique() if t != home][0]
    game = pd.Series({"game_id": ev["game_id"].iloc[0], "home_team_id": home, "away_team_id": away, "num_periods": 4})
    st, sid = build_stints(ev, lu, RULES)
    ft = link_free_throws(ev)
    rb = classify_rebounds(ev, ft, RULES)
    pos, links, seg, diag = build_possessions(ev, ft, rb, st, sid, game, RULES)
    ev = ev.merge(links, on="event_seq").merge(ft[["event_seq", "is_technical_ft", "foul_event_seq"]],
                                               on="event_seq", how="left")
    return ev, pos, seg, diag


def poss_of(ev, pos, event_seq):
    pid = ev.loc[ev["event_seq"] == event_seq, "possession_id"].iloc[0]
    return pos.set_index("possession_id").loc[pid]


def seq_of(ev, event_type, nth=0):
    return int(ev.loc[ev["event_type"] == event_type, "event_seq"].iloc[nth])


# ------------------------------------------------------------------ rule tests

def test_end_of_period_zero_point_possession_is_flagged():
    """A: the miss at 0:00 comes in a possession that starts with 2 s left and scores 0."""
    ev, pos, _, _ = run("end_of_period", "A")
    p = poss_of(ev, pos, seq_of(ev, "shot_missed"))
    assert p["secs_remaining_period_at_start"] == 2 and p["points"] == 0 and bool(p["is_end_of_period_heave"])


def test_end_of_period_scoring_possession_is_not_flagged():
    """B: the possession starts with 1 s left but scores two free throws -> kept in efficiency;
    the empty possession after the last free throw (0 s left, 0 points) is flagged."""
    ev, pos, _, _ = run("end_of_period", "B")
    p = poss_of(ev, pos, seq_of(ev, "free_throw", nth=1))
    assert p["secs_remaining_period_at_start"] == 1 and p["points"] == 2 and not bool(p["is_end_of_period_heave"])
    last = pos[pos["period"] == p["period"]].iloc[-1]
    assert last["secs_remaining_period_at_start"] == 0 and bool(last["is_end_of_period_heave"])


@pytest.mark.parametrize("which", ["A", "B"])
def test_substitution_between_free_throws(which):
    """The trip stays in one possession, which spans two stints; every FT keeps its foul."""
    ev, pos, seg, _ = run("substitution_between_free_throws", which)
    fts = ev[ev["event_type"] == "free_throw"]
    assert fts["possession_id"].nunique() == 1 and fts["foul_event_seq"].notna().all()
    assert (seg["possession_id"] == fts["possession_id"].iloc[0]).sum() >= 2


@pytest.mark.parametrize("which, chances", [("A", 2), ("B", 3)])
def test_offensive_rebound(which, chances):
    """Offensive rebounds keep the possession and start a new chance."""
    ev, pos, _, _ = run("offensive_rebound", which)
    p = poss_of(ev, pos, seq_of(ev, "shot_made", nth=0 if which == "A" else 1))
    assert p["num_chances"] == chances and p["end_type"] == "made_fg"
    in_p = ev[ev["possession_id"] == p.name]
    assert sorted(in_p["chance_id"].dropna().unique().astype(int).tolist()) == list(range(1, chances + 1))


@pytest.mark.parametrize("which", ["A", "B"])
def test_flagrant_foul(which):
    """One possession: the flagrant FT trip and the retained ball (owner 2026-10-21, as pbpstats)."""
    ev, pos, _, _ = run("flagrant_foul", which)
    last_ft = int(ev.loc[(ev["event_type"] == "free_throw") & (ev["points"] > 0), "event_seq"].iloc[0])
    trip = poss_of(ev, pos, last_ft)
    assert trip["end_type"] != "made_ft"             # the made last flagrant FT does not end it
    assert trip["num_chances"] == 1                  # and the retained ball is not a new chance
    if which == "B":   # window A ends at the free throw; B shows the retained ball
        later = ev[(ev["event_seq"] > last_ft) & (ev["team_id"] == trip["offense_team_id"])
                   & (ev["event_type"] == "free_throw")]
        assert len(later) and poss_of(ev, pos, int(later["event_seq"].iloc[0])).name == trip.name


def _synthetic(rows):
    """rows: (secs, event_type, event_subtype, team, points[, period]); team 1 = home, 2 = away."""
    ids = {1: 1610612701, 2: 1610612702}
    ev = pd.DataFrame([{"game_id": "0020400001", "event_seq": k + 1, "period": (row[5] if len(row) > 5 else 1),
                        "secs_elapsed_game": float(row[0]), "event_type": row[1], "event_subtype": row[2],
                        "team_id": ids.get(row[3]), "player1_id": 1 if row[3] else None, "player2_id": None,
                        "player3_id": None, "points": row[4], "home_score": None, "away_score": None}
                       for k, row in enumerate(rows)])
    lu = pd.DataFrame({"game_id": ev["game_id"], "event_seq": ev["event_seq"],
                       "home_player_ids": [[1, 2, 3, 4, 5]] * len(ev), "away_player_ids": [[11, 12, 13, 14, 15]] * len(ev)})
    game = pd.Series({"game_id": "0020400001", "home_team_id": ids[1], "away_team_id": ids[2], "num_periods": 4})
    st, sid = build_stints(ev, lu, RULES)
    ft = link_free_throws(ev)
    pos, links, _, diag = build_possessions(ev, ft, classify_rebounds(ev, ft, RULES), st, sid, game, RULES)
    return ev.merge(links, on="event_seq"), pos, diag


def test_free_throw_after_the_possession_ended_is_between_possessions():
    """Option (a) in both profiles: home's made 2 of 2 ends its possession although away fouls again
    at the same second; the extra free throw is outside every possession."""
    ev, pos, diag = _synthetic([(0, "period_start", 0, None, 0), (10, "foul", 2, 2, 0),
                                (10, "free_throw", 11, 1, 1), (10, "free_throw", 12, 1, 1),
                                (10, "foul", 6, 2, 0), (10, "free_throw", 10, 1, 1),
                                (20, "shot_made", 1, 2, 2), (720, "period_end", 0, None, 0)])
    extra = ev[ev["event_seq"] == 6].iloc[0]
    assert bool(extra["is_between_possessions_ft"]) and pd.isna(extra["possession_id"])
    home = pos[pos["offense_team_id"] == 1610612701].iloc[0]
    assert home["end_event_seq"] == 4 and home["points"] == 2 and diag["between_possessions_fts"] == 1
    away = poss_of(ev, pos, 7)
    assert away["offense_team_id"] == 1610612702 and away["start_type"] == "after_free_throw"


def test_jump_ball_change_starts_an_after_jump_ball_possession():
    ev, pos, _ = _synthetic([(0, "period_start", 0, None, 0), (5, "shot_missed", 1, 1, 0), (6, "rebound", 0, 1, 0),
                             (8, "jump_ball", 0, 1, 0), (8, "foul", 1, 1, 0), (12, "shot_made", 1, 2, 2),
                             (720, "period_end", 0, None, 0)])
    assert poss_of(ev, pos, 2)["end_type"] == "jump_ball"
    assert poss_of(ev, pos, 6)["start_type"] == "after_jump_ball"   # the foul by team 1 is skipped


@pytest.mark.parametrize("which", ["A", "B"])
def test_technical_free_throw(which):
    """A technical FT is outside every possession and neither starts nor ends one."""
    ev, pos, _, _ = run("technical_free_throw", which)
    tech = ev[ev["is_technical_ft"] == True]  # noqa: E712
    assert len(tech) == 1 and tech["possession_id"].isna().all()
    assert not pos["end_event_seq"].isin(tech["event_seq"]).any()
    assert not pos["start_event_seq"].isin(tech["event_seq"]).any()


@pytest.mark.parametrize("which", ["A", "B"])
def test_team_rebound_after_non_final_ft(which):
    """The team rebound between the free throws is ignored: no end, no new chance."""
    ev, pos, _, _ = run("team_rebound_after_non_final_ft", which)
    fts = ev[ev["event_type"] == "free_throw"]
    first, second = int(fts["event_seq"].iloc[0]), int(fts["event_seq"].iloc[1])
    team_reb = ev[(ev["event_type"] == "rebound") & ev["event_seq"].between(first, second)]
    assert len(team_reb) == 1
    p = poss_of(ev, pos, first)
    assert poss_of(ev, pos, second).name == p.name == poss_of(ev, pos, int(team_reb["event_seq"].iloc[0])).name
    assert p["num_chances"] == 1


@pytest.mark.parametrize("which, continues", [("A", True), ("B", False)])
def test_missed_final_free_throw(which, continues):
    """A: offensive rebound -> the possession continues (new chance); B: defensive rebound -> it ends."""
    ev, pos, _, _ = run("missed_final_free_throw", which)
    miss = int(ev.loc[(ev["event_type"] == "free_throw") & (ev["points"] == 0), "event_seq"].iloc[-1])
    reb = int(ev.loc[(ev["event_type"] == "rebound") & (ev["event_seq"] > miss), "event_seq"].iloc[0])
    p = poss_of(ev, pos, miss)
    if continues:
        assert poss_of(ev, pos, reb).name == p.name and p["num_chances"] >= 2
    else:
        assert p["end_type"] == "defensive_rebound" and p["end_event_seq"] == reb


@pytest.mark.parametrize("which, changes", [("A", True), ("B", False)])
def test_jump_ball(which, changes):
    """The possession changes only if the other team gains control (the next control event)."""
    ev, pos, _, _ = run("jump_ball", which)
    jb = seq_of(ev, "jump_ball")
    nxt = int(ev.loc[ev["event_seq"] > jb, "event_seq"].iloc[0])
    assert bool(poss_of(ev, pos, nxt).name != poss_of(ev, pos, jb).name) is changes


def test_start_type_after_steal():
    ev, pos, _, _ = run("start_type", "A")
    p = poss_of(ev, pos, seq_of(ev, "turnover"))
    assert p["end_type"] == "turnover"
    assert pos[pos["possession_id"] == p.name + 1].iloc[0]["start_type"] == "after_steal"


def test_start_type_after_timeout():
    ev, pos, _, _ = run("start_type", "B")
    to = ev[ev["event_type"] == "timeout"].iloc[0]
    p = poss_of(ev, pos, int(to["event_seq"]))
    assert bool(p["is_after_timeout"]) and p["timeout_team_id"] == to["team_id"]
    assert p["start_type"] == "after_made_shot"


def _gt_frame(margins, periods=None, starters=0):
    n = len(margins)
    return pd.DataFrame({"period": periods or [4] * n, "start_secs": [2160 + 60 * k for k in range(n)],
                         "start_margin_offense": margins, "starters_on_floor": [starters] * n})


def test_garbage_time_is_retroactive():
    """CTG: 4th quarter, margin over the band threshold, <= 2 starters; only if it holds to the end."""
    margins = [30, 30, 30, 30, 30, 30, 30, 30, 22, 22, 15, 12]
    assert garbage_time(_gt_frame(margins), RULES).tolist() == [True] * 12
    assert garbage_time(_gt_frame(margins[:-1] + [8]), RULES).tolist() == [False] * 12   # closes at the end


def test_garbage_time_needs_bench_players_and_the_fourth_quarter():
    assert not garbage_time(_gt_frame([30] * 4, starters=3), RULES).any()
    assert not garbage_time(_gt_frame([30] * 4, periods=[3, 3, 3, 3]), RULES).any()


def test_garbage_time_band_boundaries():
    """Exactly 9:00 / 6:00 left falls in the lower-threshold band (owner 2026-10-21)."""
    pos = pd.DataFrame({"period": [4, 4], "start_secs": [2160 + 180, 2160 + 360],     # 9:00 and 6:00 left
                        "start_margin_offense": [20, 10], "starters_on_floor": [0, 0]})
    assert garbage_time(pos, RULES).tolist() == [True, True]


def test_no_turnover_row_with_a_steal_ends_the_possession():
    """Source rows with turnover action type 0 ("No Turnover") carry a credited steal: a turnover."""
    ev, pos, _ = _synthetic([(0, "period_start", 0, None, 0), (5, "shot_missed", 1, 1, 0), (6, "rebound", 0, 1, 0),
                             (8, "turnover", 0, 1, 0), (12, "shot_made", 1, 2, 2), (720, "period_end", 0, None, 0)])
    assert poss_of(ev, pos, 4)["end_type"] == "turnover"
    assert poss_of(ev, pos, 5)["offense_team_id"] == 1610612702


def test_repeated_period_start_row_does_not_make_an_empty_possession():
    """A source duplicate of the period_start row joins the first possession (game 0020400756 had two)."""
    ev, pos, diag = _synthetic([(0, "period_start", 0, None, 0), (0, "period_start", 0, None, 0),
                                (0, "jump_ball", 0, 1, 0), (5, "shot_made", 1, 1, 2), (720, "period_end", 0, None, 0)])
    assert diag["possessions_without_offense"] == 0
    assert pos["offense_team_id"].notna().all() and pos.iloc[0]["start_event_seq"] == 1
    assert poss_of(ev, pos, 2).name == poss_of(ev, pos, 4).name == 1


def test_technical_foul_listed_before_the_period_start_row_makes_no_empty_possession():
    """2025-26 pattern: foul + technical FT first, then the period_start row (games 0022500055 ...)."""
    ev, pos, diag = _synthetic([(0, "period_start", 0, None, 0), (5, "shot_made", 1, 1, 2), (720, "period_end", 0, None, 0),
                                (720, "foul", 11, 1, 0, 2), (720, "free_throw", 16, 2, 1, 2),
                                (720, "period_start", 0, None, 0, 2), (731, "turnover", 39, 1, 0, 2),
                                (1440, "period_end", 0, None, 0, 2)])
    assert diag["possessions_without_offense"] == 0
    assert bool(ev.loc[ev["event_seq"] == 5, "possession_id"].isna().iloc[0])      # the technical FT is outside
    assert poss_of(ev, pos, 4).name == poss_of(ev, pos, 6).name == poss_of(ev, pos, 7).name


def test_technical_free_throws_listed_after_the_period_end_row_are_outside_every_possession():
    """Source pattern (2001-02, 2002-03, 2009-10): foul + technical FTs listed after period_end."""
    ev, pos, _ = _synthetic([(0, "period_start", 0, None, 0), (5, "shot_made", 1, 1, 2), (720, "shot_missed", 1, 2, 0),
                             (720, "foul", 11, 2, 0), (720, "period_end", 0, None, 0), (720, "free_throw", 16, 1, 1),
                             (720, "free_throw", 16, 1, 1), (720, "period_start", 0, None, 0, 2),
                             (730, "shot_made", 1, 2, 2, 2), (1440, "period_end", 0, None, 0, 2)])
    assert ev.loc[ev["event_seq"].isin([6, 7]), "possession_id"].isna().all()
    assert pos["points"].sum() == 4          # the technical FTs are not possession points
