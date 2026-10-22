"""Box marts on a tiny hand-made official box (two teams, two games, one traded player)."""

import pytest

from nba_platform import db
from nba_platform.marts import box_marts as bm

STATS = ["min", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "oreb", "dreb", "reb", "ast", "stl", "blk", "tov", "pf", "pts", "plus_minus"]


def _box(con, game_id, player_id, team_id, **kw):
    row = {s: 0.0 for s in STATS} | kw
    con.execute(f"INSERT INTO reference.nba_player_box (game_id, season_end_year, season_type, player_id, team_id, {', '.join(STATS)}) "
                f"VALUES (?, 2005, 'regular', ?, ?, {', '.join('?' * len(STATS))})", [game_id, player_id, team_id, *row.values()])


@pytest.fixture
def con():
    c = db.connect(":memory:")
    c.execute("CREATE SCHEMA IF NOT EXISTS reference")
    c.execute(f"CREATE TABLE reference.nba_player_box (game_id TEXT, season_end_year INTEGER, season_type TEXT, player_id INTEGER, team_id INTEGER, "
              f"{', '.join(s + ' DOUBLE' for s in STATS)})")
    c.execute("CREATE TABLE reference.nba_team_possessions (GAME_ID TEXT, TEAM_ID INTEGER, POSS DOUBLE, PACE DOUBLE)")
    c.execute("CREATE SCHEMA IF NOT EXISTS marts")
    c.execute("CREATE TABLE marts.player_game_pbp (game_id TEXT, player_id INTEGER, secs_played DOUBLE)")
    for gid, day, hs, as_ in (("0020400001", "2004-11-02", 100, 90), ("0020400002", "2004-11-04", 80, 85)):
        c.execute("INSERT INTO core.games (game_id, season, season_end_year, season_type, game_date, home_team_id, away_team_id, "
                  "home_score, away_score, source) VALUES (?, '2004-05', 2005, 'regular', ?, 1, 2, ?, ?, 't')", [gid, day, hs, as_])
    # game 1: team 1 = 60 + 40, team 2 = 90; game 2: player 7 now plays for team 2 (80 / 85)
    _box(c, "0020400001", 7, 1, min=30, fga=10, fgm=5, fg3a=4, fg3m=2, fta=4, ftm=3, pts=60, reb=4, ast=2)
    _box(c, "0020400001", 8, 1, min=20, pts=40)
    _box(c, "0020400001", 9, 2, min=48, pts=90)
    _box(c, "0020400002", 7, 2, min=36, pts=85, fga=20, fgm=10, fta=0)
    _box(c, "0020400002", 8, 1, min=36, pts=80)
    c.execute("INSERT INTO marts.player_game_pbp VALUES ('0020400001', 7, 1800)")
    c.execute("INSERT INTO reference.nba_team_possessions VALUES ('0020400001', 1, 95, 90), ('0020400001', 2, 96, 90)")
    yield c
    c.close()


def test_counts_and_points_check(con):
    out = bm.build(con)
    assert out["marts.player_game"] == 5 and out["marts.team_game"] == 4 and out["games_points_differ_from_score"] == 0


def test_player_game_context(con):
    bm.build(con)
    r = con.execute("SELECT is_home, won, opponent_team_id, pbp_secs_played, game_date FROM marts.player_game "
                    "WHERE game_id = '0020400002' AND player_id = 7").fetchone()
    assert r[0] is False and r[1] is True and r[2] == 1 and r[3] is None and str(r[4]) == "2004-11-04"


def test_player_season_one_row_per_team_for_a_traded_player(con):
    bm.build(con)
    rows = con.execute("SELECT team_id, games, pts, ppg, ts_pct FROM marts.player_season WHERE player_id = 7 ORDER BY team_id").fetchall()
    assert [(r[0], r[1], r[2]) for r in rows] == [(1, 1, 60.0), (2, 1, 85.0)]
    assert rows[0][3] == 60.0 and rows[0][4] == pytest.approx(60 / (2 * (10 + 0.44 * 4)))
    assert con.execute("SELECT fg3_pct, ft_pct FROM marts.player_season WHERE player_id = 8").fetchone() == (None, None)


def test_team_game_and_season(con):
    bm.build(con)
    assert con.execute("SELECT pts, opponent_pts, poss_official, won FROM marts.team_game WHERE game_id = '0020400001' AND team_id = 1").fetchone() == (100.0, 90.0, 95.0, True)
    t = con.execute("SELECT games, wins, losses, pts, opponent_pts, games_with_poss_official, ortg_official_poss, drtg_official_poss "
                    "FROM marts.team_season WHERE team_id = 1").fetchone()
    assert t[:6] == (2, 1, 1, 180.0, 175.0, 1)
    assert t[6] == pytest.approx(100 * 100 / 95) and t[7] == pytest.approx(100 * 90 / 95)


def test_points_that_do_not_add_up_are_counted(con):
    con.execute("UPDATE reference.nba_player_box SET pts = 61 WHERE game_id = '0020400001' AND player_id = 7")
    assert bm.build(con)["games_points_differ_from_score"] == 1
