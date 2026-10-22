import io
import tarfile

import pandas as pd
import pytest

from nba_platform.staging import ramirobentes as rb
from nba_platform.validate import duplicate_verification as dv

from conftest import raw_game


def _corr(kind="derived_only_duplicate"):
    return pd.DataFrame([{"game_id": "0020400001", "source_event_num": "3", "field": "__row__",
                          "old_value": kind, "new_value": "drop_one", "reason": dv.REASON, "added_on": "2026-10-18"}])


def test_derived_only_duplicate_is_dropped():
    raw = raw_game()
    raw = pd.concat([raw, raw[raw["event_num"] == 3].assign(player_ft="9 Other", poss_home=1.0)], ignore_index=True)
    out, n = rb.apply_corrections(raw, _corr())
    assert n == 1 and (out["event_num"] == 3).sum() == 1


def test_duplicate_differing_in_an_nba_field_is_not_dropped():
    raw = raw_game()
    raw = pd.concat([raw, raw[raw["event_num"] == 3].assign(clock="11:19")], ignore_index=True)
    with pytest.raises(rb.StagingError, match="not allowed to differ"):
        rb.apply_corrections(raw, _corr())


def _scan(differing):
    return pd.DataFrame([{"file": "pbp_regular_2005.parquet", "game_id": "0020400001", "event_num": 3,
                          "n_rows": 2, "msg_type": 6, "act_type": 1, "all_columns_identical": False,
                          "differing_columns": differing}])


@pytest.mark.parametrize("differing, official, apply", [
    ("player_ft poss_home", 1, True),     # both conditions hold
    ("player_ft clock", 1, False),        # (a) fails: an NBA field differs
    ("player_ft", 2, False),              # (b) fails: official PBP also has it twice
    ("player_ft", None, False),           # (b) cannot be checked: no official file
])
def test_verify_needs_both_conditions(monkeypatch, differing, official, apply):
    monkeypatch.setattr(dv, "official_count", lambda *a: official)
    assert bool(dv.verify(_scan(differing))["apply"].iloc[0]) is apply


def test_official_count_reads_nbastats(tmp_path, monkeypatch):
    csv = b"GAME_ID,EVENTNUM\n20400001,3\n20400001,4\n20400001,4\n"
    folder = tmp_path / "shufinskiy"
    folder.mkdir()
    with tarfile.open(folder / "nbastats_2004.tar.xz", "w:xz") as tar:
        info = tarfile.TarInfo("nbastats_2004.csv")
        info.size = len(csv)
        tar.addfile(info, io.BytesIO(csv))
    monkeypatch.setattr(dv, "RAW_DIR", tmp_path)
    assert dv.official_count("0020400001", 3, 2005, "regular") == 1
    assert dv.official_count("0020400001", 4, 2005, "regular") == 2
    assert dv.official_count("0020400001", 9, 2005, "regular") == 0
