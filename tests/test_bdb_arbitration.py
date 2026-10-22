from types import SimpleNamespace as R

import pandas as pd

from nba_platform.validate import bdb_arbitration as arb


def run(**kw):
    base = dict(game_id="g1", only_ours=[1], only_bdb=[2], first_event=100, end_event=120)
    base.update(kw)
    return R(**base)


BOX = {("g1", 1): 30.0, ("g1", 2): 10.0}


def test_minutes_verdict_picks_the_source_matching_the_box():
    ours = {("g1", 1): 30.2, ("g1", 2): 10.4}
    bdb = {("g1", 1): 26.0, ("g1", 2): 14.0}
    assert arb.minutes_verdict(run(), ours, bdb, BOX, 1.0) == "ramirobentes"
    assert arb.minutes_verdict(run(), bdb, ours, BOX, 1.0) == "bigdataball"


def test_minutes_verdict_leans_and_undetermined():
    ours = {("g1", 1): 28.0, ("g1", 2): 12.0}   # 4 min total error
    bdb = {("g1", 1): 25.0, ("g1", 2): 15.0}    # 10 min total error
    assert arb.minutes_verdict(run(), ours, bdb, BOX, 1.0) == "leans ramirobentes"
    assert arb.minutes_verdict(run(), BOX, BOX, BOX, 1.0) == "undetermined"
    assert arb.minutes_verdict(run(only_ours=[9], only_bdb=[]), ours, bdb, BOX, 1.0) == "undetermined"  # no box


def _subs(rows):
    return {"g1": pd.DataFrame(rows, columns=["event_num", "out_id", "in_id"])}


def test_official_sub_out_supports_the_source_with_the_player_on_court():
    assert arb.official_verdict(run(), _subs([(110, 1, 7)])) == "ramirobentes"
    assert arb.official_verdict(run(), _subs([(110, 2, 7)])) == "bigdataball"


def test_official_sub_in_depends_on_where_it_happens():
    assert arb.official_verdict(run(), _subs([(100, 7, 1)])) == "ramirobentes"   # enters at the run start
    assert arb.official_verdict(run(), _subs([(110, 7, 1)])) == "bigdataball"    # enters later: was off before
    assert arb.official_verdict(run(), _subs([(130, 1, 7)])) == "no evidence"    # outside the window
    # mid-run: the ours-only player leaves and the BigDataBall-only player enters -> both support ours
    assert arb.official_verdict(run(), _subs([(110, 1, 2)])) == "ramirobentes"
    # evidence pointing both ways is reported as conflicting
    assert arb.official_verdict(run(), _subs([(110, 1, 7), (115, 2, 8)])) == "conflicting"
    assert arb.official_verdict(run(game_id="g2"), _subs([])) == "no official data"
