"""Shooting marts on hand-made shots: 3 players, 2 teams, one flagged shot, one shot without a zone."""

import pytest

from nba_platform import db
from nba_platform.marts import shot_zones as sz

RULES = {"dashboard": {"shot_percentile_min_season_fga": 4, "shot_percentile_min_zone_fga": 2}}


def _shot(con, n, player, team, zone, made):
    con.execute("INSERT INTO core.shots (game_id, source_event_num, player_id, team_id, shot_zone_basic, made, source) "
                "VALUES ('0020400001', ?, ?, ?, ?, ?, 't')", [n, player, team, zone, made])


@pytest.fixture
def con():
    c = db.connect(":memory:")
    c.execute("INSERT INTO core.games (game_id, season, season_end_year, season_type, home_team_id, away_team_id, source) "
              "VALUES ('0020400001', '2004-05', 2005, 'regular', 1, 2, 't')")
    n = 0
    # player 10 (team 1): RA 2/2, mid 0/2 ; player 11 (team 1): RA 1/2, mid 1/2 ; player 20 (team 2): RA 0/2 + 2 unknown (1 made)
    for player, team, zone, made in [(10, 1, "Restricted Area", True), (10, 1, "Restricted Area", True), (10, 1, "Mid-Range", False),
                                     (10, 1, "Mid-Range", False), (11, 1, "Restricted Area", True), (11, 1, "Restricted Area", False),
                                     (11, 1, "Mid-Range", True), (11, 1, "Mid-Range", False), (20, 2, "Restricted Area", False),
                                     (20, 2, "Restricted Area", False), (20, 2, None, True), (20, 2, None, False)]:
        n += 1
        _shot(c, n, player, team, zone, made)
    c.execute("INSERT INTO core.shot_quality_flags VALUES ('0020400001', 1, 'rim_location_suspect')")
    yield c
    c.close()


def test_every_shot_is_counted_once(con):
    out = sz.build(con, RULES)
    assert out["shots_in_player_zones"] == out["shots_in_core"] == 12


def test_league_and_unknown_zone(con):
    sz.build(con, RULES)
    ra = con.execute("SELECT fga, fgm, fg_pct FROM marts.shot_zones_league WHERE zone = 'Restricted Area'").fetchone()
    assert ra == (6, 3, 0.5)
    assert con.execute("SELECT fga FROM marts.shot_zones_league WHERE zone = 'Unknown'").fetchone() == (2,)


def test_team_offense_and_defense(con):
    sz.build(con, RULES)
    off = con.execute("SELECT fga, fgm FROM marts.shot_zones_team WHERE team_id = 1 AND side = 'offense' AND zone = 'Mid-Range'").fetchone()
    dfn = con.execute("SELECT fga, fgm FROM marts.shot_zones_team WHERE team_id = 2 AND side = 'defense' AND zone = 'Mid-Range'").fetchone()
    assert off == (4, 1) and dfn == (4, 1)  # team 2 defended team 1's four mid-range shots


def test_player_percentiles_and_flag_share(con):
    sz.build(con, RULES)
    q = lambda p, z, col: con.execute(f"SELECT {col} FROM marts.shot_zones_player WHERE player_id = ? AND zone = ?", [p, z]).fetchone()[0]
    # Restricted Area accuracy 1.0 / 0.5 / 0.0 -> percentiles 100 / 50 / 0
    assert [q(p, "Restricted Area", "fg_pct_percentile") for p in (10, 11, 20)] == [100.0, 50.0, 0.0]
    assert [q(p, "Mid-Range", "fg_pct_percentile") for p in (10, 11)] == [0.0, 100.0]
    assert q(10, "Restricted Area", "flagged_share") == 0.5 and q(11, "Restricted Area", "flagged_share") == 0.0
    assert q(10, "Mid-Range", "freq") == 0.5 and q(20, "Unknown", "league_fg_pct") == 0.5


def test_thresholds_leave_small_samples_without_percentile(con):
    sz.build(con, {"dashboard": {"shot_percentile_min_season_fga": 5, "shot_percentile_min_zone_fga": 2}})
    assert con.execute("SELECT count(fg_pct_percentile) + count(freq_percentile) FROM marts.shot_zones_player").fetchone()[0] == 0
