"""Team efficiency mart on a hand-made set of possessions."""

import pytest

from nba_platform import db
from nba_platform.marts import team_efficiency as te


def _poss(c, game, pid, off, de, pts, heave=False, garbage=False, profile="pbpstats_compat"):
    c.execute("INSERT INTO core.possessions (game_id, possession_id, offense_team_id, defense_team_id, period, start_secs, end_secs, "
              "start_event_seq, end_event_seq, start_type, end_type, points, num_chances, secs_remaining_period_at_start, "
              "secs_remaining_game_at_start, is_end_of_period_heave, is_garbage_time, is_after_timeout, rules_version, rules_profile) "
              "VALUES (?, ?, ?, ?, 1, 0, 0, 1, 1, 's', 'e', ?, 1, 0, 0, ?, ?, FALSE, 'v1', ?)", [game, pid, off, de, pts, heave, garbage, profile])


@pytest.fixture
def con():
    c = db.connect(":memory:")
    c.execute("INSERT INTO core.games VALUES ('G1', '2024-25', 2025, 'regular', NULL, 1, 2, 0, 0, 4, 't', FALSE, NULL), "
              "('G2', '2024-25', 2025, 'regular', NULL, 3, 1, 0, 0, 4, 't', FALSE, NULL)")
    _poss(c, "G1", 1, 1, 2, 2)
    _poss(c, "G1", 2, 2, 1, 3)
    _poss(c, "G1", 3, 1, 2, 0, heave=True)
    _poss(c, "G1", 4, 2, 1, 2, garbage=True)
    _poss(c, "G2", 1, 1, 3, 3)
    _poss(c, "G2", 2, 3, 1, 0)
    c.execute("INSERT INTO core.events (game_id, event_seq, period, secs_elapsed_game, team_id, event_type, points, is_technical_ft, possession_id, source) "
              "VALUES ('G1', 9, 1, 50, 1, 'free_throw', 1, TRUE, NULL, 't'), "
              # team 1 in G1: a made three, a missed two, a made free throw in a possession; team 2: a made two
              "('G1', 10, 1, 60, 1, 'shot_made', 3, NULL, 1, 't'), ('G1', 11, 1, 70, 1, 'shot_missed', 0, NULL, 3, 't'), "
              "('G1', 12, 1, 80, 1, 'free_throw', 1, FALSE, 1, 't'), ('G1', 13, 1, 90, 2, 'shot_made', 2, NULL, 2, 't')")
    c.execute("UPDATE core.possessions SET end_type = 'turnover' WHERE game_id = 'G1' AND possession_id = 3")
    c.execute("UPDATE core.possessions SET num_chances = 2, end_type = 'defensive_rebound' WHERE game_id = 'G2' AND possession_id = 1")
    yield c
    c.close()


def _row(con, team: int) -> dict:
    cur = con.execute("SELECT * FROM marts.team_efficiency_season WHERE team_id = ?", [team])
    return dict(zip([d[0] for d in cur.description], cur.fetchone()))


def test_offense_and_defense_counts_and_ratings(con):
    assert te.build(con) == {"rows": 3, "possessions": 6}
    t1 = _row(con, 1)
    assert (t1["games"], t1["o_poss"], t1["o_pts"], t1["d_poss"], t1["d_pts"]) == (2, 3, 5, 3, 5)
    assert t1["ortg"] == pytest.approx(500 / 3) and t1["net"] == pytest.approx(0)
    assert t1["poss_per_game"] == 1.5   # (3 offense + 3 defense) / 2 / 2 games


def test_heave_and_garbage_versions(con):
    te.build(con)
    t1 = _row(con, 1)
    assert (t1["o_poss_ex_heave"], t1["o_pts_ex_heave"], t1["ortg_ex_heave"]) == (2, 5, 250.0)
    assert (t1["d_poss_ex_heave_garbage"], t1["d_pts_ex_heave_garbage"]) == (2, 3)
    assert t1["drtg_ex_heave_garbage"] == 150.0


def test_technical_free_throws_are_outside_possessions(con):
    te.build(con)
    assert _row(con, 1)["pts_outside_possessions"] == 1 and _row(con, 2)["pts_outside_possessions"] == 0
    assert _row(con, 1)["o_pts"] == 5  # not 6


def test_rows_carry_rules_version(con):
    te.build(con)
    assert con.execute("SELECT DISTINCT rules_version, rules_profile FROM marts.team_efficiency_season").fetchall() == [("v1", "pbpstats_compat")]


def test_mixed_profiles_fail(con):
    _poss(con, "G2", 3, 1, 3, 2, profile="custom")
    with pytest.raises(te.TeamEfficiencyError, match="rules versions"):
        te.build(con)


def test_team_not_in_game_fails(con):
    _poss(con, "G2", 3, 2, 3, 2)
    with pytest.raises(te.TeamEfficiencyError, match="not one of the game's two teams"):
        te.build(con)


def test_four_factors_from_our_events(con):
    te.build(con)
    t1, t2 = _row(con, 1), _row(con, 2)
    assert (t1["o_fga"], t1["o_fgm"], t1["o_fg3m"], t1["o_ftm"]) == (2, 1, 1, 1)   # the technical free throw is not counted
    assert t1["o_efg"] == 0.75 and t1["o_ft_rate"] == 0.5
    assert (t1["o_tov"], t1["o_tov_pct"]) == (1, pytest.approx(1 / 3))
    assert (t1["o_orb"], t1["o_drb_against"], t1["o_orb_pct"]) == (1, 1, 0.5)     # G2: one offensive rebound, then a defensive one
    # defense = the opponents' offense in the same games: team 2 in G1 (one made two) and team 3 in G2 (nothing)
    assert (t1["d_fga"], t1["d_fgm"], t1["d_efg"]) == (1, 1, 1.0)
    assert (t2["d_fga"], t2["d_fg3m"], t2["d_tov"]) == (2, 1, 1)
