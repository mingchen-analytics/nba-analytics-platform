import datetime

import pandas as pd
import pytest

from nba_platform import db, known_gaps, load
from nba_platform.staging import ramirobentes as rb
from nba_platform.validate import box_minutes, checks

from conftest import raw_game, shotdetail_for


@pytest.fixture
def con(tmp_path, monkeypatch):
    monkeypatch.setattr(box_minutes, "load_box_minutes", lambda y, t: None)
    c = db.connect(":memory:")
    raw = raw_game()
    xref = rb.derive_team_xref(raw, shotdetail_for(raw), 2005)
    load.load_pbp_season(c, rb.stage(raw, xref, 2005, "regular"), xref, rb.SOURCE, 2005, "regular", out_dir=tmp_path)
    yield c
    c.close()


def _gaps(monkeypatch, rows):
    monkeypatch.setattr(known_gaps, "read_known_gaps", lambda: pd.DataFrame(rows))


def _box_row(gid):
    return {"game_id": gid, "season": "2004-05", "season_end_year": 2005, "season_type": "regular",
            "game_date": datetime.date(2005, 1, 1), "home_team_id": 1610612701, "away_team_id": 1610612702,
            "home_score": 100, "away_score": 90, "num_periods": None, "source": "nba_api_box",
            "pbp_missing": True, "known_issue": "pbp_missing"}


def test_pbp_missing_game_is_added_from_box_and_flagged(con, monkeypatch):
    _gaps(monkeypatch, [{"game_id": "0020400999", "season_end_year": 2005, "season_type": "regular",
                         "issue": "pbp_missing", "reason": "test", "added_on": "2026-10-18"}])
    monkeypatch.setattr(known_gaps, "box_game_row", lambda g, y, t: _box_row(g))
    assert known_gaps.apply(con, 2005, "regular") == []
    row = con.execute("SELECT pbp_missing, source, home_score FROM core.games WHERE game_id = '0020400999'").fetchone()
    assert row == (True, "nba_api_box", 100)
    # the game without events must not break the event-based checks
    assert checks.check_2_points_equal_score(con, 2005, "regular").status == "pass"
    assert checks.check_6_player_seconds(con, 2005, "regular").status == "pass"
    r1 = checks.check_1_game_count(con, 2005, "regular")
    assert r1.detail["known_gaps_pbp_missing"] == ["0020400999"]
    # re-applying is idempotent
    assert known_gaps.apply(con, 2005, "regular") == []
    assert con.execute("SELECT count(*) FROM core.known_gaps").fetchone()[0] == 1


def test_score_conflict_is_reported_as_known(con, monkeypatch):
    con.execute("UPDATE core.games SET home_score = home_score + 1 WHERE game_id = '0020400001'")
    assert checks.check_2_points_equal_score(con, 2005, "regular").status == "fail"
    _gaps(monkeypatch, [{"game_id": "0020400001", "season_end_year": 2005, "season_type": "regular",
                         "issue": "source_score_conflict", "reason": "test", "added_on": "2026-10-18"}])
    known_gaps.apply(con, 2005, "regular")
    assert con.execute("SELECT known_issue FROM core.games WHERE game_id = '0020400001'").fetchone()[0] == "source_score_conflict"
    r = checks.check_2_points_equal_score(con, 2005, "regular")
    assert r.status == "known" and r.detail["known_gaps"] == ["0020400001"]


def test_pbp_missing_without_box_is_a_problem_not_an_insert(con, monkeypatch):
    _gaps(monkeypatch, [{"game_id": "0020400999", "season_end_year": 2005, "season_type": "regular",
                         "issue": "pbp_missing", "reason": "test", "added_on": "2026-10-18"}])
    monkeypatch.setattr(known_gaps, "box_game_row", lambda g, y, t: None)
    problems = known_gaps.apply(con, 2005, "regular")
    assert problems and con.execute("SELECT count(*) FROM core.games WHERE game_id = '0020400999'").fetchone()[0] == 0


def test_known_gaps_csv_is_well_formed():
    g = known_gaps.read_known_gaps()
    assert set(["game_id", "season_end_year", "season_type", "issue", "reason", "added_on"]) <= set(g.columns)
    assert g["game_id"].str.len().eq(10).all() and not g.duplicated(["game_id", "issue"]).any()
