import pytest

from nba_platform.validate import proposed_corrections as pc

from conftest import raw_game


def test_normalize_removes_accents_and_case():
    assert pc.normalize("Bojan Bogdanović") == pc.normalize("bojan bogdanovic")


def _raw_with_missing_id():
    raw = raw_game()
    # one lineup entry lost its ID, but the same player appears with an ID elsewhere
    raw.loc[raw["event_num"] == 3, "lineup_home"] = "1 Home One, 2 Home Two, 3 Home Three, 4 Home Four, NA Home Fivé"
    return raw


def test_proposes_only_unique_name_match():
    found = pc.find_missing_ids(_raw_with_missing_id(), "f.parquet")
    assert len(found) == 1
    f = found[0]
    assert (f["field"], f["source_event_num"], f["lineup_position"], f["proposed_player_id"]) == ("lineup_home", 3, 4, 5)


def test_unknown_name_is_unresolved():
    raw = raw_game()
    raw.loc[raw["event_num"] == 3, "player1_name"] = "NA Nobody Known"
    f = pc.find_missing_ids(raw, "f.parquet")[0]
    assert f["proposed_player_id"] is None and f["n_candidates"] == 0


def test_to_corrections_rebuilds_full_values():
    raw = _raw_with_missing_id()
    corr = pc.to_corrections(raw, pc.find_missing_ids(raw, "f.parquet"), "test", "2026-10-17")
    row = corr.iloc[0]
    assert row["old_value"].endswith("NA Home Fivé")
    assert row["new_value"] == "1 Home One, 2 Home Two, 3 Home Three, 4 Home Four, 5 Home Fivé"


def test_to_corrections_refuses_unresolved():
    raw = raw_game()
    raw.loc[raw["event_num"] == 3, "player1_name"] = "NA Nobody Known"
    with pytest.raises(ValueError):
        pc.to_corrections(raw, pc.find_missing_ids(raw, "f.parquet"), "test", "2026-10-17")
