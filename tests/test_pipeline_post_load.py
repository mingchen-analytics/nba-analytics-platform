from nba_platform import db, pipeline
from nba_platform.validate import bdb_crosscheck, shot_quality


def test_post_load_runs_both_steps_and_records_failures(monkeypatch):
    con = db.connect(":memory:")
    calls = []
    monkeypatch.setattr(shot_quality, "run", lambda c: calls.append("shots"))

    def boom(c):
        calls.append("bdb")
        raise RuntimeError("no files")

    monkeypatch.setattr(bdb_crosscheck, "run", boom)
    pipeline.post_load(con)  # must not raise
    assert calls == ["shots", "bdb"]
    rows = con.execute("SELECT check_name, status FROM validation.results WHERE season_type = 'post_load'").fetchall()
    assert rows == [("post-load step failed: BigDataBall cross-check", "fail")]
    # a later successful run clears the old failure
    monkeypatch.setattr(bdb_crosscheck, "run", lambda c: calls.append("bdb ok"))
    pipeline.post_load(con)
    assert con.execute("SELECT count(*) FROM validation.results WHERE season_type = 'post_load'").fetchone()[0] == 0


def test_run_all_calls_post_load(monkeypatch):
    con = db.connect(":memory:")
    called = []
    monkeypatch.setattr(pipeline, "run_season", lambda c, y, t: pipeline.SeasonOutcome(y, t, "loaded", []))
    monkeypatch.setattr(pipeline, "post_load", lambda c: called.append(True))
    monkeypatch.setattr(pipeline.report, "write_season_report", lambda c: None)
    pipeline.run_all(con, [2005])
    assert called == [True]
