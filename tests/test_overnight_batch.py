import importlib.util
from datetime import datetime, timedelta
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("overnight_batch", Path(__file__).parents[1] / "scripts" / "overnight_batch.py")
ob = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ob)


class Boom:
    def __init__(self, **kw):
        raise TimeoutError("read timed out")


def test_cooldowns_then_stop(tmp_path, monkeypatch):
    monkeypatch.setattr(ob, "NBA_DIR", tmp_path)
    monkeypatch.setattr(ob.time, "sleep", lambda s: None)
    slept = []
    monkeypatch.setattr(ob, "_sleep_until", lambda t: slept.append(t))
    nba = ob.Nba(deadline=datetime.now() + timedelta(hours=10))
    for i in range(5 * 4):
        try:
            nba.get("x", "2025-26", f"n{i}", Boom)
        except ob.NbaStopped:
            break
    assert len(nba.cooldowns) == 3 and len(slept) == 3 and nba.stopped  # 45, 90, 90 min, then stop
    with pytest.raises(ob.NbaStopped):
        nba.get("x", "2025-26", "after", Boom)


def test_cooldown_past_deadline_stops(tmp_path, monkeypatch):
    monkeypatch.setattr(ob, "NBA_DIR", tmp_path)
    monkeypatch.setattr(ob.time, "sleep", lambda s: None)
    nba = ob.Nba(deadline=datetime.now() + timedelta(minutes=10))
    for i in range(5):
        nba.get("x", "2025-26", f"n{i}", Boom)
    assert nba.stopped and nba.cooldowns == []


class Ok:
    def __init__(self, **kw):
        pass

    def get_dict(self):
        return {"resultSets": []}


def test_planned_rest_every_n_requests(tmp_path, monkeypatch):
    monkeypatch.setattr(ob, "NBA_DIR", tmp_path)
    monkeypatch.setattr(ob, "record_in_manifest", lambda *a, **k: None)
    monkeypatch.setattr(ob.time, "sleep", lambda s: None)
    rests = []
    monkeypatch.setattr(ob, "_sleep_until", lambda t: rests.append(t))
    nba = ob.Nba(deadline=datetime.now() + timedelta(hours=10))
    nba.REST_EVERY = 3
    for i in range(7):
        nba.get("x", "s", f"n{i}", Ok)
    assert len(nba.rests) == 2 and len(rests) == 2  # after request 3 and 6


def test_task_c_loads_regular_and_playoff_matchups(tmp_path, monkeypatch):
    import io
    import tarfile
    from types import SimpleNamespace

    from nba_platform import db

    def fake_download(url, dest):
        csv = b"game_id,team_id\n41700101,1\n" if "_po_" in dest.name else b"game_id,team_id\n21700001,1\n"
        dest.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(dest, "w:xz") as tar:
            info = tarfile.TarInfo(dest.name.replace(".tar.xz", ".csv"))
            info.size = len(csv)
            tar.addfile(info, io.BytesIO(csv))
        return "downloaded"

    monkeypatch.setattr(ob, "fetch_shufinskiy_index", lambda: {"matchups_2024": "u1", "matchups_po_2024": "u2"})
    monkeypatch.setattr(ob, "download", fake_download)
    monkeypatch.setattr(ob, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(ob, "STAGING_DIR", tmp_path / "staging")
    con = db.connect(":memory:")
    res = ob.task_c(con, SimpleNamespace(trial=True))
    rows = con.execute("SELECT season_type, season_end_year, count(*) FROM reference.matchups GROUP BY ALL ORDER BY 1").fetchall()
    assert rows == [("playoffs", 2025, 1), ("regular", 2025, 1)]
    assert res["numbers"]["rows"] == 2


def test_parse_deadline_time_of_day_and_full_date():
    now = datetime(2026, 10, 23, 13, 0)
    assert ob.parse_deadline("21:30", now) == datetime(2026, 10, 23, 21, 30)
    assert ob.parse_deadline("08:00", now) == datetime(2026, 10, 24, 8, 0)             # already past today: tomorrow
    assert ob.parse_deadline("2026-10-24 21:30", now) == datetime(2026, 10, 24, 21, 30)  # exact moment
