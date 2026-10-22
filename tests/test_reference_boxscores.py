import json

import pytest

from nba_platform import db
from nba_platform.reference import boxscores as bx


def _box(top, players):
    return {"meta": {}, top: {"gameId": "0042500101", "homeTeamId": 1, "awayTeamId": 2,
                              "homeTeam": {"teamId": 1, "players": players}, "awayTeam": {"teamId": 2, "players": []}}}


P = {"personId": 7, "position": "G", "comment": "", "statistics": {"minutes": "33:18", "distance": 2.5, "touches": 60}}


@pytest.mark.parametrize("value, secs", [("33:18", 1998), ("PT33M18.00S", 1998), ("0:00", 0), ("", None), (None, None)])
def test_minutes_to_secs(value, secs):
    assert bx.minutes_to_secs(value) == secs


def test_minutes_unparseable_fails():
    with pytest.raises(ValueError):
        bx.minutes_to_secs("33 minutes")


def test_flatten_one_row_per_player():
    rows = bx.flatten(_box("boxScorePlayerTrack", [P]), "2025-26")
    assert len(rows) == 1
    r = rows[0]
    assert (r["game_id"], r["season_type"], r["team_id"], r["is_home"], r["person_id"]) == ("0042500101", "playoffs", 1, True, 7)
    assert r["secs_played"] == 1998 and r["distance"] == 2.5 and r["touches"] == 60 and r["comment"] is None


def test_empty_shell_is_counted_not_loaded(tmp_path):
    (tmp_path / "box_tracking" / "2025-26").mkdir(parents=True)
    (tmp_path / "box_hustle" / "2015-16").mkdir(parents=True)
    (tmp_path / "box_tracking" / "2025-26" / "0042500101.json").write_text(json.dumps(_box("boxScorePlayerTrack", [P])))
    (tmp_path / "box_hustle" / "2015-16" / "0021500001.json").write_text(json.dumps(_box("boxScoreHustle", [])))
    con = db.connect(":memory:")
    out = bx.load_all(con, raw_dir=tmp_path)
    assert out["nba_box_tracking"] == {"files": 1, "empty_shells": 0, "player_rows": 1, "games": 1}
    assert out["nba_box_hustle"]["empty_shells"] == 1 and out["nba_box_hustle"]["player_rows"] == 0
    assert con.execute("SELECT count(*) FROM reference.nba_box_tracking").fetchone()[0] == 1
