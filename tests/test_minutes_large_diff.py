from types import SimpleNamespace as R

from nba_platform.validate.minutes_large_diff import classify

NAN = float("nan")


def row(**kw):
    base = dict(diff=8.0, pbp_min=30.0, box_min=22.0, team_box_off=0.0, longest_period_start_run=NAN,
                counterpart_sum=NAN, bdb_min=NAN)
    base.update(kw)
    return R(**base)


def test_team_box_total_short_means_box_wrong():
    assert classify(row(team_box_off=-60.0), 5, 1) == "box_likely_wrong"


def test_bigdataball_agreeing_with_box_blames_our_lineup():
    assert classify(row(bdb_min=22.5), 5, 1) == "ramirobentes_likely_wrong"


def test_bigdataball_agreeing_with_us_blames_box():
    assert classify(row(bdb_min=30.2), 5, 1) == "box_likely_wrong"


def test_period_start_stretch_matching_the_gap_blames_our_lineup_without_bdb():
    assert classify(row(longest_period_start_run=8.3 * 60), 5, 1) == "ramirobentes_likely_wrong"


def test_teammate_swap_and_undetermined():
    assert classify(row(counterpart_sum=0.4), 5, 1) == "swapped_with_teammate"
    assert classify(row(), 5, 1) == "undetermined"
