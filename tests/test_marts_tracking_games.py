"""Single-game tracking mart on hand-made reference boxes."""

import pytest

from nba_platform import db
from nba_platform.marts import tracking_games as tg

RULES = {"dashboard": {"tracking_game_max_plausible_speed_mph": 6.0, "tracking_game_min_secs": 300}}


@pytest.fixture
def con():
    c = db.connect(":memory:")
    c.execute("CREATE SCHEMA IF NOT EXISTS reference")
    tcols = ", ".join(f"{x} DOUBLE" for x in tg.TRACKING_COLS)
    hcols = ", ".join(f"{x} DOUBLE" for x in tg.HUSTLE_COLS)
    c.execute(f"CREATE TABLE reference.nba_box_tracking (game_id TEXT, team_id INTEGER, person_id INTEGER, secs_played DOUBLE, {tcols})")
    c.execute(f"CREATE TABLE reference.nba_box_hustle (game_id TEXT, team_id INTEGER, person_id INTEGER, secs_played DOUBLE, {hcols})")
    c.execute("INSERT INTO core.games VALUES ('G1', '2024-25', 2025, 'regular', NULL, 1, 2, 0, 0, 4, 't', FALSE, NULL), "
              "('G2', '2024-25', 2025, 'regular', NULL, 1, 2, 0, 0, 4, 't', FALSE, NULL)")
    c.execute("INSERT INTO core.players VALUES (7, 'Seven', ['Seven']), (8, 'Eight', ['Eight'])")
    c.execute("INSERT INTO reference.nba_box_tracking (game_id, team_id, person_id, secs_played, distance, speed, touches) VALUES "
              "('G1', 1, 7, 1800, 2.5, 4.3, 50), ('G1', 2, 8, 120, 0.3, 7.5, 3), ('G2', 1, 7, 1500, 30.0, 150.0, 40), ('G2', 2, 8, 1600, 2.1, 4.1, 30)")
    c.execute("INSERT INTO reference.nba_box_hustle (game_id, team_id, person_id, secs_played, deflections) VALUES ('G1', 1, 7, 1800, 3)")
    yield c
    c.close()


def test_one_row_per_player_and_game_with_hustle_joined(con):
    out = tg.build(con, RULES)
    assert out == {"rows": 4, "games": 2, "suspect_games": 1, "dnp_rows": 0}
    row = con.execute("SELECT has_tracking, has_hustle, touches, deflections FROM marts.player_game_tracking WHERE game_id = 'G1' AND player_id = 7").fetchone()
    assert row == (True, True, 50.0, 3.0)
    assert con.execute("SELECT deflections FROM marts.player_game_tracking WHERE game_id = 'G2' AND player_id = 8").fetchone()[0] is None


def test_a_game_is_flagged_as_a_whole_and_short_stints_do_not_flag(con):
    tg.build(con, RULES)
    flags = dict(con.execute("SELECT game_id || '-' || player_id, movement_suspect FROM marts.player_game_tracking").fetchall())
    assert flags == {"G1-7": False, "G1-8": False, "G2-7": True, "G2-8": True}   # 7.5 mph in 120 s does not flag G1


def test_unknown_player_and_duplicates_fail(con):
    con.execute("INSERT INTO reference.nba_box_tracking (game_id, team_id, person_id, secs_played) VALUES ('G1', 1, 7, 10)")
    with pytest.raises(tg.TrackingGamesError, match="duplicate"):
        tg.build(con, RULES)
    con.execute("DELETE FROM reference.nba_box_tracking WHERE secs_played = 10")
    con.execute("INSERT INTO reference.nba_box_hustle (game_id, team_id, person_id, secs_played) VALUES ('G2', 1, 99, 10)")
    with pytest.raises(tg.TrackingGamesError, match="not in core.players"):
        tg.build(con, RULES)


def test_game_missing_from_core_fails(con):
    con.execute("INSERT INTO reference.nba_box_hustle (game_id, team_id, person_id, secs_played) VALUES ('G9', 1, 7, 10)")
    with pytest.raises(tg.TrackingGamesError, match="not in core.games"):
        tg.build(con, RULES)


def test_did_not_play_rows_are_left_out_and_counted_even_for_unknown_players(con):
    con.execute("INSERT INTO reference.nba_box_tracking (game_id, team_id, person_id, secs_played) VALUES ('G1', 1, 99, 0), ('G2', 2, 8, NULL)")
    con.execute("DELETE FROM reference.nba_box_tracking WHERE game_id = 'G2' AND person_id = 8 AND secs_played = 1600")
    out = tg.build(con, RULES)
    assert out["dnp_rows"] == 2 and out["rows"] == 3
