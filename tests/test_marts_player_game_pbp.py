"""PBP box score on the tiny fixture game (conftest.raw_game): HOM 3, AWY 2."""

import pytest

from nba_platform import db, load
from nba_platform.marts import player_game_pbp as pgp
from nba_platform.staging import ramirobentes as rb

from conftest import raw_game, shotdetail_for


@pytest.fixture
def con(tmp_path):
    c = db.connect(":memory:")
    raw = raw_game()
    shots = shotdetail_for(raw)
    xref = rb.derive_team_xref(raw, shots, 2005)
    load.load_pbp_season(c, rb.stage(raw, xref, 2005, "regular"), xref, rb.SOURCE, 2005, "regular", out_dir=tmp_path)
    yield c
    c.close()


def _rows(con):
    pgp.build(con)
    df = con.execute("SELECT * FROM marts.player_game_pbp").df()
    return df.set_index("player_id")


def test_counting_stats(con):
    r = _rows(con)
    assert r.loc[11, ["pts", "fgm", "fga"]].tolist() == [2, 1, 1]
    assert r.loc[2, ["pts", "fgm", "fga"]].tolist() == [0, 0, 1]
    assert r.loc[3, ["pts", "ftm", "fta"]].tolist() == [2, 2, 2]
    assert r.loc[1, ["pts", "ftm", "fta"]].tolist() == [1, 1, 1]
    assert r.loc[12, "pf"] == 1
    assert r["reb"].sum() == 0  # the only rebound is a team rebound (no player)


def test_points_sum_to_final_score(con):
    r = _rows(con)
    home = con.execute("SELECT home_team_id FROM core.games").fetchone()[0]
    assert r[r.team_id == home]["pts"].sum() == 3 and r[r.team_id != home]["pts"].sum() == 2


def test_plus_minus_uses_lineup_on_each_event(con):
    r = _rows(con)
    # sub 5 -> 6 between the two free throws: the second FT is credited to the post-sub lineup
    assert r.loc[5, "plus_minus"] == -1 and r.loc[6, "plus_minus"] == 2 and r.loc[1, "plus_minus"] == 1
    assert r.loc[11, "plus_minus"] == -1


def test_seconds_on_court(con):
    r = _rows(con)
    assert r.loc[5, "secs_played"] == 60 and r.loc[6, "secs_played"] == 47 * 60 and r.loc[1, "secs_played"] == 48 * 60


def test_stealer_is_player2_or_player3(con):
    """Steal role differs by era (player2 up to 2015-16, player3 in 2016-17 -> 2024-25)."""
    con.execute("UPDATE core.events SET event_type = 'turnover', player1_id = 11, player2_id = 2, player3_id = NULL "
                "WHERE event_seq = (SELECT min(event_seq) FROM core.events WHERE event_type = 'shot_missed')")
    assert _rows(con).loc[2, "stl"] == 1
    con.execute("UPDATE core.events SET player2_id = NULL, player3_id = 2 WHERE event_type = 'turnover'")
    r = _rows(con)
    assert r.loc[2, "stl"] == 1 and r.loc[11, "tov"] == 1
