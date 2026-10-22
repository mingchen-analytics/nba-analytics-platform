"""Matchup mart on a hand-made reference.matchups (every column text, game ids without leading zeros)."""

import pytest

from nba_platform import db
from nba_platform.marts import matchups as mm


@pytest.fixture
def con():
    c = db.connect(":memory:")
    c.execute("CREATE SCHEMA IF NOT EXISTS reference")
    ref_cols = ["game_id", "team_id", "person_id", "matchups_person_id", "season_type"] + [ref for ref, _ in mm.NUMERIC.values()]
    c.execute(f"CREATE TABLE reference.matchups ({', '.join(x + ' VARCHAR' for x in dict.fromkeys(ref_cols))}, season_end_year BIGINT)")
    c.execute("INSERT INTO core.teams VALUES (1, 'AAA', 'Aaa'), (2, 'BBB', 'Bbb'), (3, 'CCC', 'Ccc')")
    c.execute("INSERT INTO core.players VALUES (7, 'Seven', ['Seven']), (8, 'Eight', ['Eight']), (9, 'Nine', ['Nine'])")
    c.execute("INSERT INTO core.games VALUES ('0021700001', '2017-18', 2018, 'regular', NULL, 1, 2, 0, 0, 4, 't', FALSE, NULL)")
    c.execute("INSERT INTO reference.matchups (game_id, team_id, person_id, matchups_person_id, season_type, season_end_year, matchup_minutes_sort, "
              "partial_possessions, percentage_defender_total_time, switches_on, player_points, matchup_field_goals_made, matchup_field_goals_attempted, "
              "shooting_fouls) VALUES "
              "('21700001', '1', '7', '8', 'regular', 2018, '566.6', '45.3', '0.612', '0', '13', '6', '9', '1'), "
              "('21700001', '1', '7', '9', 'regular', 2018, '35.7', '2.8', '0.081', '', '2', '1', '2', NULL)")
    yield c
    c.close()


def test_game_id_is_zero_padded_and_values_are_typed(con):
    out = mm.build(con)
    assert out["rows"] == 2 and out["games"] == 1
    row = con.execute("SELECT game_id, team_id, defender_id, offender_id, matchup_secs, partial_possessions, pct_defender_time, player_pts, fgm, fga "
                      "FROM marts.matchup_pairs WHERE offender_id = 8").fetchone()
    assert row == ("0021700001", 1, 7, 8, 566.6, 45.3, 0.612, 13, 6, 9)


def test_blank_and_missing_values_are_null_not_zero(con):
    mm.build(con)
    row = con.execute("SELECT switches_on, shooting_fouls, blocks FROM marts.matchup_pairs WHERE offender_id = 9").fetchone()
    assert row == (None, None, None)


def test_the_mart_has_the_primary_key_and_a_known_column_set(con):
    mm.build(con)
    cols = [r[0] for r in con.execute("DESCRIBE marts.matchup_pairs").fetchall()]
    assert cols[:6] == ["game_id", "season_end_year", "season_type", "team_id", "defender_id", "offender_id"] and set(mm.NUMERIC) <= set(cols)
    with pytest.raises(Exception):
        con.execute("INSERT INTO marts.matchup_pairs (game_id, season_end_year, season_type, team_id, defender_id, offender_id) "
                    "VALUES ('0021700001', 2018, 'regular', 1, 7, 8)")


@pytest.mark.parametrize("sql,message", [
    ("UPDATE reference.matchups SET game_id = '21799999'", "not in core.games"),
    ("UPDATE reference.matchups SET matchups_person_id = '99' WHERE matchups_person_id = '9'", "not in core.players"),
    ("UPDATE reference.matchups SET team_id = '3' WHERE matchups_person_id = '9'", "defender whose team did not play"),
    ("UPDATE reference.matchups SET team_id = '5'", "not in core.teams"),
    ("UPDATE reference.matchups SET matchups_person_id = '8'", "duplicate"),
    ("UPDATE reference.matchups SET player_points = 'x' WHERE matchups_person_id = '8'", "not a number"),
    ("UPDATE reference.matchups SET person_id = NULL WHERE matchups_person_id = '8'", "missing or non-numeric person_id"),
])
def test_bad_data_fails_loudly_and_rolls_back(con, sql, message):
    con.execute(sql)
    with pytest.raises(mm.MatchupMartError, match=message):
        mm.build(con)
    assert con.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'marts' AND table_name = 'matchup_pairs'").fetchone()[0] == 0


def test_rebuild_replaces_the_table(con):
    mm.build(con)
    assert mm.build(con)["rows"] == 2 and con.execute("SELECT count(*) FROM marts.matchup_pairs").fetchone()[0] == 2
