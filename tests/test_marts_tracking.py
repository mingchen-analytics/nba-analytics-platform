"""Tracking mart on a tiny hand-made reference.nba_tracking / nba_hustle."""

import pytest

from nba_platform import db
from nba_platform.marts import tracking as tr


def _src_cols(hustle: bool) -> list[str]:
    return sorted({c for _, m, c, _ in tr.columns() if (m == "hustle") == hustle for c in [c.upper()]})


@pytest.fixture
def con():
    c = db.connect(":memory:")
    c.execute("CREATE SCHEMA IF NOT EXISTS reference")
    tcols = ", ".join(f"{x} DOUBLE" for x in _src_cols(False) + ["GP", "MIN"])
    c.execute(f"CREATE TABLE reference.nba_tracking (season TEXT, season_type TEXT, request_param_1 TEXT, PLAYER_ID INTEGER, TEAM_ID INTEGER, {tcols})")
    hcols = ", ".join(f"{x} DOUBLE" for x in _src_cols(True))
    c.execute(f"CREATE TABLE reference.nba_hustle (season TEXT, season_type TEXT, request_param_1 TEXT, PLAYER_ID INTEGER, TEAM_ID INTEGER, G INTEGER, {hcols})")
    c.execute("INSERT INTO core.players VALUES (7, 'Seven', ['Seven']), (8, 'Eight', ['Eight'])")
    # player 7: two measures on team 1; player 8 traded (teams 1 and 2); the Possessions row carries GP / MIN
    c.execute("INSERT INTO reference.nba_tracking (season, season_type, request_param_1, PLAYER_ID, TEAM_ID, GP, MIN, TOUCHES) "
              "VALUES ('2024-25', 'regular', 'Possessions', 7, 1, 70, 2100, 3000), ('2024-25', 'regular', 'Possessions', 8, 1, 20, 400, 500), "
              "('2024-25', 'regular', 'Possessions', 8, 2, 30, 900, 800)")
    c.execute("INSERT INTO reference.nba_tracking (season, season_type, request_param_1, PLAYER_ID, TEAM_ID, GP, DIST_MILES, AVG_SPEED) "
              "VALUES ('2024-25', 'regular', 'SpeedDistance', 7, 1, 70, 180.5, 4.2)")
    c.execute("INSERT INTO reference.nba_hustle (season, season_type, request_param_1, PLAYER_ID, TEAM_ID, G, DEFLECTIONS) "
              "VALUES ('2024-25', 'regular', 'player', 7, 1, 69, 120)")
    yield c
    c.close()


def test_column_names_are_unique_and_known():
    names = [c for _, _, c, _ in tr.columns()]
    assert len(names) == len(set(names)) and {k for _, _, _, k in tr.columns()} == {"count", "rate"}


def test_flattens_measures_into_one_row_per_key(con):
    out = tr.build(con)
    assert out == {"rows": 3, "with_tracking": 3, "with_hustle": 1, "movement_suspect": 0}
    row = con.execute("SELECT gp, min, touches, dist_miles, avg_speed, deflections, hustle_gp FROM marts.player_tracking_season "
                      "WHERE player_id = 7").fetchone()
    assert row == (70, 2100.0, 3000.0, 180.5, 4.2, 120.0, 69)
    traded = con.execute("SELECT team_id, gp FROM marts.player_tracking_season WHERE player_id = 8 ORDER BY team_id").fetchall()
    assert traded == [(1, 20), (2, 30)]


def test_missing_hustle_is_null_not_zero(con):
    tr.build(con)
    assert con.execute("SELECT deflections, hustle_gp FROM marts.player_tracking_season WHERE player_id = 8 AND team_id = 1").fetchone() == (None, None)


def test_unknown_player_fails(con):
    con.execute("INSERT INTO reference.nba_tracking (season, season_type, request_param_1, PLAYER_ID, TEAM_ID, GP) VALUES ('2024-25', 'regular', 'Possessions', 99, 1, 1)")
    with pytest.raises(tr.TrackingMartError, match="not in core.players"):
        tr.build(con)


def test_hustle_only_row_is_kept(con):
    con.execute("INSERT INTO reference.nba_hustle (season, season_type, request_param_1, PLAYER_ID, TEAM_ID, G, DEFLECTIONS) VALUES ('2023-24', 'playoffs', 'player', 8, 3, 5, 9)")
    out = tr.build(con)
    assert out["with_hustle"] == 2 and out["rows"] == 4
    assert con.execute("SELECT gp, deflections FROM marts.player_tracking_season WHERE team_id = 3").fetchone() == (None, 9.0)


def test_missing_source_column_fails(con):
    con.execute("ALTER TABLE reference.nba_tracking DROP COLUMN DIST_MILES")
    with pytest.raises(tr.TrackingMartError, match="missing"):
        tr.build(con)


def test_thread_setting_is_restored(con):
    before = con.execute("SELECT current_setting('threads')").fetchone()[0]
    tr.build(con)
    assert con.execute("SELECT current_setting('threads')").fetchone()[0] == before


def test_implausible_average_speed_is_flagged_not_dropped(con):
    con.execute("UPDATE reference.nba_tracking SET AVG_SPEED = 15.4 WHERE request_param_1 = 'SpeedDistance' AND PLAYER_ID = 7")
    out = tr.build(con, {"dashboard": {"tracking_max_plausible_avg_speed_mph": 5.5}})
    assert out["rows"] == 3 and out["movement_suspect"] == 1
    assert con.execute("SELECT movement_suspect, avg_speed FROM marts.player_tracking_season WHERE player_id = 7").fetchone() == (True, 15.4)
    assert con.execute("SELECT count(*) FROM marts.player_tracking_season WHERE movement_suspect IS NOT TRUE").fetchone()[0] == 2  # NULL speed is not flagged


def test_small_samples_are_not_flagged(con):
    """Player 8 (400 min): fine; a 40-minute sample with a high average speed is not a defect."""
    con.execute("UPDATE reference.nba_tracking SET MIN = 40 WHERE PLAYER_ID = 8 AND request_param_1 = 'Possessions'")
    con.execute("INSERT INTO reference.nba_tracking (season, season_type, request_param_1, PLAYER_ID, TEAM_ID, GP, AVG_SPEED) "
                "VALUES ('2024-25', 'regular', 'SpeedDistance', 8, 1, 20, 7.0)")
    out = tr.build(con, {"dashboard": {"tracking_max_plausible_avg_speed_mph": 5.5, "tracking_suspect_min_minutes": 100}})
    assert out["movement_suspect"] == 0
