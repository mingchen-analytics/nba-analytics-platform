import pandas as pd
import pytest

from nba_platform.staging import bigdataball as bdb
from nba_platform.staging import ramirobentes as rb
from nba_platform.validate import conditional_corrections as cc
from nba_platform.validate import duplicates
from nba_platform.validate import proposed_corrections as pc

from conftest import AWAY, HOME, raw_game


def _drop_corr(event_num=3):
    return pd.DataFrame([{"game_id": "0020400001", "source_event_num": str(event_num), "field": "__row__",
                          "old_value": "exact_duplicate", "new_value": "drop_one",
                          "reason": "source exact duplicate", "added_on": "2026-10-17"}])


def test_exact_duplicate_is_dropped_once():
    raw = raw_game()
    raw = pd.concat([raw, raw[raw["event_num"] == 3]], ignore_index=True)
    out, n = rb.apply_corrections(raw, _drop_corr())
    assert n == 1 and (out["event_num"] == 3).sum() == 1


def test_duplicate_differing_in_any_column_is_not_dropped():
    raw = raw_game()
    copy = raw[raw["event_num"] == 3].assign(player_ft="9 Someone")  # differs in one column
    raw = pd.concat([raw, copy], ignore_index=True)
    with pytest.raises(rb.StagingError, match="not allowed to differ"):
        rb.apply_corrections(raw, _drop_corr())


def test_duplicate_scan_flags_identical_and_non_identical():
    raw = raw_game()
    raw = pd.concat([raw, raw[raw["event_num"] == 3], raw[raw["event_num"] == 4].assign(player_ft="9 X")],
                    ignore_index=True)
    found = {d["event_num"]: d for d in duplicates.find_duplicates(raw, "f.parquet")}
    assert found[3]["all_columns_identical"] is True
    assert found[4]["all_columns_identical"] is False and found[4]["differing_columns"] == "player_ft"
    corr = cc.exact_duplicate_corrections(pd.DataFrame(found.values()), "2026-10-17")
    assert corr["source_event_num"].tolist() == [3] and corr["reason"].tolist() == ["source exact duplicate"]


def _bdb_game(raw, home_names):
    rows = []
    for r in raw[raw["msg_type"] != 99].itertuples(index=False):
        rows.append({"play_id": int(r.event_num), "period": int(r.period), "clock": r.clock,
                     "home_names": home_names, "away_names": [a.split(" ", 1)[1] for a in AWAY]})
    return pd.DataFrame(rows)


def _raw_missing():
    raw = raw_game()
    raw.loc[raw["event_num"] == 3, "lineup_home"] = "1 Home One, 2 Home Two, 3 Home Three, 4 Home Four, NA Home Fivé"
    return raw


def test_bigdataball_lineup_confirms_proposal():
    raw = _raw_missing()
    props = pd.DataFrame(pc.find_missing_ids(raw, "f.parquet"))
    check = cc.verify_with_bigdataball(raw, props, _bdb_game(raw, [h.split(" ", 1)[1] for h in HOME]))
    assert check["consistent"].all()


def test_bigdataball_lineup_mismatch_blocks_proposal():
    raw = _raw_missing()
    props = pd.DataFrame(pc.find_missing_ids(raw, "f.parquet"))
    other = ["Home One", "Home Two", "Home Three", "Home Four", "Somebody Else"]
    check = cc.verify_with_bigdataball(raw, props, _bdb_game(raw, other))
    assert not check["consistent"].any() and "not in the BigDataBall lineup" in check["problem"].iloc[0]


def test_bigdataball_reader_cleans_quirks(tmp_path):
    p = tmp_path / "[2014-10-28]-0021400001-ORL@NOP.csv"
    cols = ["game_id", "a1", "a2", "a3", "a4", "a5", "h1", "h2", "h3", "h4", "h5", "period",
            "away_score", "home_score", "remaining_time", "play_id", "event_type"]
    pd.DataFrame([['="0021400001"', "A", "B", "C", "D", "E", "F", "G", "H", "I", " J ", "1", "0", "0",
                   "00:11:41", "2", " miss "]], columns=cols).to_csv(p, index=False)
    assert bdb.game_files(tmp_path) == {"0021400001": p}
    g = bdb.read_game(p)
    assert g["game_id"].iloc[0] == "0021400001" and g["clock"].iloc[0] == "11:41"
    assert g["event_type"].iloc[0] == "miss" and g["home_names"].iloc[0][-1] == "J"


def test_normalize_name():
    assert bdb.normalize_name("J.J. Redick") == bdb.normalize_name("JJ Redick")
    assert bdb.normalize_name("Bojan Bogdanović") == "bojan bogdanovic"
