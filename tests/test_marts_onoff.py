"""On/off and lineup marts on one hand-made game.

Game G1: home team 1 (players 11-15), away team 2 (players 21-25), 100 s per stint.
Stint 1: home 11-15. Stint 2: home 11-14 + 16 (16 replaces 15); away unchanged.
  p1  team 1, one field goal (2 pts), ends in stint 1
  p2  team 2, spans both stints, one field goal (3 pts), ends in stint 2      -> credited to stint 2
  p3  team 1, foul in stint 1, substitution, two made free throws in stint 2  -> possession to stint 2, FT points to stint 1
  p4  team 2, end-of-period heave flagged, 0 pts, stint 2
plus a technical free throw by team 2 that belongs to no possession and is counted nowhere.
"""

import pytest

from nba_platform import db
from nba_platform.marts import onoff

HOME, AWAY = list(range(11, 16)), list(range(21, 26))


@pytest.fixture
def con():
    c = db.connect(":memory:")
    c.execute("INSERT INTO core.games VALUES ('G1', '2024-25', 2025, 'regular', NULL, 1, 2, 4, 3, 4, 't', FALSE, NULL)")
    for sid, home in ((1, HOME), (2, [11, 12, 13, 14, 16])):
        c.execute("INSERT INTO core.stints VALUES ('G1', ?, 1, ?, ?, 1, 20, 'substitution', 5, " + ", ".join(["?"] * 10) + ", 'v1')",
                  [sid, (sid - 1) * 100.0, sid * 100.0, *home, *AWAY])
    poss = [(1, 1, 2, 2, False, 1, 1), (2, 2, 1, 3, False, 1, 2), (3, 1, 2, 2, False, 1, 2), (4, 2, 1, 0, True, 2, 2)]
    for pid, off, de, pts, heave, first_stint, last_stint in poss:
        c.execute("INSERT INTO core.possessions (game_id, possession_id, offense_team_id, defense_team_id, period, start_secs, end_secs, "
                  "start_event_seq, end_event_seq, start_type, end_type, points, num_chances, secs_remaining_period_at_start, "
                  "secs_remaining_game_at_start, is_end_of_period_heave, is_garbage_time, is_after_timeout, rules_version, rules_profile) "
                  "VALUES ('G1', ?, ?, ?, 1, 0, 0, 1, 1, 's', 'e', ?, 1, 0, 0, ?, FALSE, FALSE, 'v1', 'pbpstats_compat')",
                  [pid, off, de, pts, heave])
        for seq, sid in enumerate(range(first_stint, last_stint + 1), 1):
            c.execute("INSERT INTO core.possession_stint_segments VALUES ('G1', ?, ?, ?, 1, 1, 0, 0)", [pid, seq, sid])
    ev = "INSERT INTO core.events (game_id, event_seq, period, secs_elapsed_game, team_id, event_type, points, stint_id, possession_id, foul_event_seq, is_technical_ft, source) VALUES "
    c.execute(ev + "('G1', 2, 1, 10, 1, 'shot_made', 2, 1, 1, NULL, NULL, 't'), ('G1', 3, 1, 120, 2, 'shot_made', 3, 2, 2, NULL, NULL, 't'),"
                   "('G1', 10, 1, 50, 2, 'foul', 0, 1, 3, NULL, NULL, 't'),"
                   "('G1', 12, 1, 130, 1, 'free_throw', 1, 2, 3, 10, FALSE, 't'), ('G1', 13, 1, 131, 1, 'free_throw', 1, 2, 3, 10, FALSE, 't'),"
                   "('G1', 20, 1, 150, 2, 'free_throw', 1, 2, NULL, NULL, TRUE, 't')")
    yield c
    c.close()


def _player(con, player_id: int) -> dict:
    cur = con.execute("SELECT * FROM marts.player_onoff_season WHERE player_id = ?", [player_id])
    return dict(zip([d[0] for d in cur.description], cur.fetchone()))


def test_possession_goes_to_end_stint_and_free_throw_points_to_the_foul_stint(con):
    out = onoff.build(con)
    assert out["player_rows"] == 11 and out["ft_without_foul"] == 0
    p15, p16 = _player(con, 15), _player(con, 16)
    # 15 was on only in stint 1: p1 (2 pts) and the free throws of p3 (2 pts), but not the possession p3 itself
    assert (p15["on_o_poss"], p15["on_o_pts"], p15["on_d_poss"], p15["on_d_pts"], p15["on_secs"]) == (1, 4, 0, 0, 100.0)
    # 16 was on only in stint 2: the possession p3 (0 pts credited here), and p2 + p4 on defense
    assert (p16["on_o_poss"], p16["on_o_pts"], p16["on_d_poss"], p16["on_d_pts"], p16["on_secs"]) == (1, 0, 2, 3, 100.0)
    assert p16["on_d_heave_poss"] == 1 and p16["on_o_heave_poss"] == 0


def test_off_is_team_total_minus_on_and_rates(con):
    onoff.build(con)
    p15 = _player(con, 15)
    assert (p15["off_o_poss"], p15["off_o_pts"], p15["off_d_poss"], p15["off_d_pts"], p15["off_secs"]) == (1, 0, 2, 3, 100.0)
    assert p15["on_ortg"] == 400.0 and p15["on_drtg"] is None and p15["on_net"] is None  # no defensive possession on: NULL, not 0
    assert p15["off_ortg"] == 0.0 and p15["off_drtg"] == 150.0 and p15["off_net"] == -150.0
    assert p15["net_on_minus_off"] is None
    p11 = _player(con, 11)  # on for both stints: off is empty
    assert (p11["off_secs"], p11["off_o_poss"], p11["off_d_poss"]) == (0.0, 0, 0)
    assert p11["on_ortg"] == 200.0 and p11["on_drtg"] == 150.0 and p11["on_net"] == 50.0 and p11["net_on_minus_off"] is None


def test_technical_free_throw_is_counted_nowhere(con):
    onoff.build(con)
    assert con.execute("SELECT sum(on_o_pts) / 5 FROM marts.player_onoff_season WHERE team_id = 2").fetchone()[0] == 3
    assert con.execute("SELECT sum(o_pts) FROM marts.lineup_stats").fetchone()[0] == 7  # 4 + 3, not 8


def test_lineups_group_the_same_five_players_across_stints(con):
    onoff.build(con)
    rows = con.execute("SELECT team_id, lineup_key, stints, secs, o_poss, o_pts, d_poss, d_pts FROM marts.lineup_stats ORDER BY team_id, lineup_key").fetchall()
    assert rows == [(1, "11-12-13-14-15", 1, 100.0, 1, 4, 0, 0), (1, "11-12-13-14-16", 1, 100.0, 1, 0, 2, 3),
                    (2, "21-22-23-24-25", 2, 200.0, 2, 3, 2, 4)]


def test_lineup_key_is_sorted_whatever_the_source_order(con):
    con.execute("UPDATE core.stints SET home_p1 = 15, home_p5 = 11 WHERE stint_id = 1")
    onoff.build(con)
    assert con.execute("SELECT count(*) FROM marts.lineup_stats WHERE lineup_key = '11-12-13-14-15'").fetchone()[0] == 1


def test_rows_carry_the_rules_version_and_credit_method(con):
    onoff.build(con)
    assert con.execute("SELECT DISTINCT credit_method, rules_version, rules_profile FROM marts.player_onoff_season").fetchall() == [("pbpstats_hybrid", "v1", "pbpstats_compat")]
    assert con.execute("SELECT DISTINCT credit_method, rules_version FROM marts.lineup_stats").fetchall() == [("pbpstats_hybrid", "v1")]


def test_free_throw_without_foul_goes_to_its_own_stint_and_is_counted(con):
    con.execute("UPDATE core.events SET foul_event_seq = NULL WHERE event_seq = 12")
    out = onoff.build(con)
    assert out["ft_without_foul"] == 1
    assert _player(con, 16)["on_o_pts"] == 1 and _player(con, 15)["on_o_pts"] == 3  # one free throw moved from stint 1 to stint 2


def test_possession_without_stint_segment_fails_and_rolls_back(con):
    con.execute("DELETE FROM core.possession_stint_segments WHERE possession_id = 4")
    with pytest.raises(onoff.OnOffMartError, match="no stint segment"):
        onoff.build(con)
    assert con.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'marts' AND table_name = 'player_onoff_season'").fetchone()[0] == 0


def test_points_not_conserved_fails(con):
    con.execute("UPDATE core.possessions SET points = 5 WHERE possession_id = 1")
    with pytest.raises(onoff.OnOffMartError, match="points not conserved"):
        onoff.build(con)


def test_offense_team_must_be_home_or_away(con):
    con.execute("UPDATE core.possessions SET offense_team_id = 9 WHERE possession_id = 1")
    with pytest.raises(onoff.OnOffMartError, match="neither home nor away"):
        onoff.build(con)


def test_mixed_rules_versions_fail(con):
    con.execute("UPDATE core.possessions SET rules_profile = 'custom' WHERE possession_id = 1")
    with pytest.raises(onoff.OnOffMartError, match="rules versions"):
        onoff.build(con)


def test_rebuild_replaces_the_tables(con):
    onoff.build(con)
    out = onoff.build(con)
    assert out["player_rows"] == 11 and con.execute("SELECT count(*) FROM marts.player_onoff_season").fetchone()[0] == 11
