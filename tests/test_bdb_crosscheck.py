import pandas as pd

from nba_platform.validate import bdb_crosscheck as bc


def test_bdb_xref_name_then_lineup_rule():
    id_names = {1: {"a one"}, 2: {"b two"}, 3: {"c three"}, 4: {"d four"}, 5: {"e five"}}
    names = ["a one", "b two", "c three", "d four", "nickname five"]  # 5th name differs from our name
    aligned = pd.DataFrame({"names": [names] * 12, "ids": [[1, 2, 3, 4, 5]] * 12, "team_id": [10] * 12})
    xref, unmatched = bc.build_xref(aligned, id_names)
    assert xref["a one"] == (1, "name")
    assert xref["nickname five"] == (5, "lineup") and unmatched == {}


def test_bdb_xref_does_not_guess_with_few_or_ambiguous_votes():
    id_names = {1: {"a one"}, 2: {"b two"}, 3: {"c three"}, 4: {"d four"}, 5: {"e five"}, 6: {"f six"}}
    rows = [{"names": ["a one", "b two", "c three", "x", "y"], "ids": [1, 2, 3, 5, 6], "team_id": 10}] * 20
    xref, unmatched = bc.build_xref(pd.DataFrame(rows), id_names)
    assert "x" not in xref and "y" not in xref and set(unmatched) == {"x", "y"}

