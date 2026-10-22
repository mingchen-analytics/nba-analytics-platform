"""rebuild.py: a failing step is recorded and the run goes on; the summary report reads the checks."""

import pytest

from nba_platform import build_core, db, load, rebuild
from nba_platform.staging import ramirobentes as rb
from nba_platform.validate import possession_summary

from conftest import raw_game, shotdetail_for


def test_a_failing_step_is_recorded_and_does_not_stop_the_run(capsys):
    results = []
    rebuild._step("good", lambda: {"rows": 1}, results)
    rebuild._step("bad", lambda: 1 / 0, results)
    rebuild._step("after", lambda: "still runs", results)
    assert [(n, s) for n, s, _, _ in results] == [("good", "ok"), ("bad", "error"), ("after", "ok")]
    assert "ZeroDivisionError" in results[1][3] and "[ERROR] bad" in capsys.readouterr().out


@pytest.fixture
def con(tmp_path):
    c = db.connect(":memory:")
    raw = raw_game()
    xref = rb.derive_team_xref(raw, shotdetail_for(raw), 2005)
    load.load_pbp_season(c, rb.stage(raw, xref, 2005, "regular"), xref, rb.SOURCE, 2005, "regular", out_dir=tmp_path)
    yield c
    c.close()


def test_loaded_seasons_and_the_summary_report(con, tmp_path, monkeypatch):
    assert build_core.loaded_seasons(con) == [(2005, "regular")]
    monkeypatch.setattr(db, "PROJECT_ROOT", tmp_path)
    (tmp_path / "docs" / "validation").mkdir(parents=True)
    runs = build_core.run_all(con, "possessions", build_core.PROFILE)
    assert [r["status"] for r in runs] == ["ok"] and runs[0]["stints"] > 0
    assert con.execute("SELECT count(*) FROM core.stints").fetchone()[0] == runs[0]["stints"]
    assert con.execute("SELECT count(*) FROM core.events WHERE stint_id IS NULL").fetchone()[0] == 0
    out = tmp_path / "summary.md"
    assert possession_summary.write_report(con, out) == 1
    text = out.read_text(encoding="utf-8")
    assert "| 2004-05 | regular |" in text and "| pass |" in text
