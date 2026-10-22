"""build_core writes stints and events.stint_id for a loaded season (in-memory DB, fixture game)."""

import pytest

from nba_platform import build_core, db, load
from nba_platform.staging import ramirobentes as rb

from conftest import raw_game, shotdetail_for


@pytest.fixture
def con(tmp_path):
    c = db.connect(":memory:")
    raw = raw_game()
    xref = rb.derive_team_xref(raw, shotdetail_for(raw), 2005)
    load.load_pbp_season(c, rb.stage(raw, xref, 2005, "regular"), xref, rb.SOURCE, 2005, "regular", out_dir=tmp_path)
    yield c
    c.close()


def test_stints_written_and_linked(con):
    out = build_core.run(con, 2005, "regular", "stints")
    assert out["games"] == 1 and out["events_without_stint"] == 0 and out["team_games_time_mismatch"] == 0
    assert con.execute("SELECT count(*) FROM core.events WHERE stint_id IS NULL").fetchone()[0] == 0
    rv = con.execute("SELECT DISTINCT rules_version FROM core.stints").fetchall()
    assert len(rv) == 1 and rv[0][0].startswith("2026-")


def test_rebuild_is_idempotent(con):
    a = build_core.run(con, 2005, "regular", "stints")
    b = build_core.run(con, 2005, "regular", "stints")
    assert a["stints"] == b["stints"] == con.execute("SELECT count(*) FROM core.stints").fetchone()[0]


def test_possessions_written_and_checked(con, tmp_path, monkeypatch):
    from nba_platform import db as dbm
    monkeypatch.setattr(dbm, "PROJECT_ROOT", tmp_path)
    (tmp_path / "docs" / "validation").mkdir(parents=True)
    out = build_core.run(con, 2005, "regular", "possessions")
    assert out["possessions"] > 0 and out["checks"][112] == ("pass", 0) and out["checks"][8][0] == "skip" and out["checks"][7][0] == "pass"
    pos = con.execute("SELECT count(*), count(DISTINCT rules_profile), min(rules_profile) FROM core.possessions").fetchone()
    assert pos[0] == out["possessions"] and pos[1:] == (1, "pbpstats_compat")
    # every event is in a possession or is a free throw outside one
    outside = con.execute("""SELECT count(*) FROM core.events WHERE possession_id IS NULL
                             AND NOT (event_type = 'free_throw' AND (is_technical_ft OR is_between_possessions_ft))""").fetchone()[0]
    assert outside == 0
    assert (tmp_path / "docs" / "validation" / "possession_check_2005_regular.md").exists()


def test_possessions_rebuild_is_idempotent(con, tmp_path, monkeypatch):
    from nba_platform import db as dbm
    monkeypatch.setattr(dbm, "PROJECT_ROOT", tmp_path)
    (tmp_path / "docs" / "validation").mkdir(parents=True)
    a = build_core.run(con, 2005, "regular", "possessions")["possessions"]
    b = build_core.run(con, 2005, "regular", "possessions")["possessions"]
    assert a == b == con.execute("SELECT count(*) FROM core.possessions").fetchone()[0]
