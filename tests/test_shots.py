import pandas as pd
import pytest

from nba_platform import db, load
from nba_platform.staging import ramirobentes as rb
from nba_platform.staging import shufinskiy as sh
from nba_platform.validate import checks

from conftest import raw_game, shotdetail_for


def test_stage_shots_layout():
    shots = sh.stage_shots(shotdetail_for(raw_game()))
    assert list(shots.columns) == ["game_id", "source_event_num", "player_id", "team_id", "shot_type",
                                   "action_type", "shot_zone_basic", "shot_zone_area", "shot_zone_range",
                                   "distance_ft", "loc_x", "loc_y", "made", "source"]
    assert shots["made"].tolist() == [True, False]
    assert set(shots["source"]) == {"shufinskiy"}


def test_stage_shots_null_key_fails():
    sd = shotdetail_for(raw_game())
    sd.loc[sd.index[0], "PLAYER_ID"] = None
    with pytest.raises(sh.ShotStagingError):
        sh.stage_shots(sd)


def test_read_shotdetail_restores_leading_zeros(tmp_path):
    import io
    import tarfile
    csv = b"GAME_ID,GAME_EVENT_ID\n20400027,2\n"
    path = tmp_path / "shotdetail_2004.tar.xz"
    with tarfile.open(path, "w:xz") as tar:
        info = tarfile.TarInfo("shotdetail_2004.csv")
        info.size = len(csv)
        tar.addfile(info, io.BytesIO(csv))
    assert sh.read_shotdetail(path)["GAME_ID"].tolist() == ["0020400027"]


@pytest.fixture
def loaded(tmp_path):
    con = db.connect(":memory:")
    raw = raw_game()
    sd = shotdetail_for(raw)
    xref = rb.derive_team_xref(raw, sd, 2005)
    staged = rb.stage(raw, xref, 2005, "regular")
    load.load_pbp_season(con, staged, xref, rb.SOURCE, 2005, "regular", out_dir=tmp_path)
    yield con, sd, tmp_path
    con.close()


def test_shot_join_passes(loaded):
    con, sd, tmp = loaded
    load.load_shots_season(con, sh.stage_shots(sd), "shufinskiy", 2005, "regular", out_dir=tmp)
    r = checks.check_10_shot_join(con, 2005, "regular")
    assert r.status == "pass" and r.detail["join_rate_xy"] == 1.0
    assert checks.check_107_shots_unique_and_complete(con, 2005, "regular", 2, 0).status == "pass"


def test_shot_join_missing_coordinates_is_warning(loaded):
    con, sd, tmp = loaded
    sd = sd.copy()
    sd["LOC_X"] = None
    load.load_shots_season(con, sh.stage_shots(sd), "shufinskiy", 2005, "regular", out_dir=tmp)
    r = checks.check_10_shot_join(con, 2005, "regular")
    assert r.status == "fail" and r.level == "warning" and r.detail["with_xy"] == 0


def test_shot_disagreeing_with_event_is_reported(loaded):
    con, sd, tmp = loaded
    sd = sd.copy()
    sd["SHOT_MADE_FLAG"] = 1  # the missed shot is now "made" in the shot source
    load.load_shots_season(con, sh.stage_shots(sd), "shufinskiy", 2005, "regular", out_dir=tmp)
    r = checks.check_10_shot_join(con, 2005, "regular")
    assert r.status == "fail" and r.detail["joined_but_disagree"] == 1


def test_duplicate_shot_rolls_back(loaded):
    con, sd, tmp = loaded
    shots = sh.stage_shots(pd.concat([sd, sd.iloc[[0]]]))

    def hard(c):
        if checks.check_107_shots_unique_and_complete(c, 2005, "regular", len(shots), 0).status == "fail":
            raise RuntimeError("hard fail")

    with pytest.raises(RuntimeError):
        load.load_shots_season(con, shots, "shufinskiy", 2005, "regular", before_commit=hard, out_dir=tmp)
    assert con.sql("SELECT count(*) FROM core.shots").fetchone()[0] == 0
