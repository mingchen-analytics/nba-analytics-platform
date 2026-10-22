"""Load the tiny fixture game into an in-memory DuckDB and run every validation check."""

import pandas as pd
import pytest

from nba_platform import db, load
from nba_platform.staging import ramirobentes as rb
from nba_platform.validate import checks

from conftest import raw_game, shotdetail_for


def _load(con, raw, tmp_path, before_commit=None):
    shots = shotdetail_for(raw)
    xref = rb.derive_team_xref(raw, shots, 2005)
    staged = rb.stage(raw, xref, 2005, "regular")
    load.load_pbp_season(con, staged, xref, rb.SOURCE, 2005, "regular",
                         before_commit=before_commit, out_dir=tmp_path)
    return staged


@pytest.fixture(autouse=True)
def no_box_cache(monkeypatch):
    """Unit tests must not read the real nba_api cache (tests that need box data pass it)."""
    from nba_platform.validate import box_minutes
    monkeypatch.setattr(box_minutes, "load_box_minutes", lambda y, t: None)


@pytest.fixture
def con():
    c = db.connect(":memory:")
    yield c
    c.close()


def test_load_counts_and_reference_tables(con, tmp_path):
    staged = _load(con, raw_game(), tmp_path)
    assert con.sql("SELECT count(*) FROM core.games").fetchone()[0] == 1
    assert con.sql("SELECT count(*) FROM core.events").fetchone()[0] == len(staged.events)
    assert con.sql("SELECT count(*) FROM staging.event_lineups").fetchone()[0] == len(staged.events)
    assert con.sql("SELECT count(*) FROM core.teams").fetchone()[0] == 2
    assert con.sql("SELECT count(*) FROM core.players").fetchone()[0] == 11
    assert con.sql("SELECT stint_id, possession_id FROM core.events WHERE stint_id IS NOT NULL "
                   "OR possession_id IS NOT NULL").fetchall() == []


def test_reload_is_idempotent(con, tmp_path):
    _load(con, raw_game(), tmp_path)
    _load(con, raw_game(), tmp_path)
    assert con.sql("SELECT count(*) FROM core.games").fetchone()[0] == 1
    assert con.sql("SELECT count(*) FROM core.events").fetchone()[0] == len(raw_game()) - 1


def test_all_checks_pass_on_clean_game(con, tmp_path):
    _load(con, raw_game(), tmp_path)
    # check 1 needs a full schedule; check 5 needs box scores (tested separately)
    results = [c(con, 2005, "regular") for c in checks.PBP_HARD_CHECKS + checks.PBP_WARNING_CHECKS
               if c not in (checks.check_1_game_count, checks.check_5_minutes_vs_box)]
    by_id = {r.check_id: r.status for r in results}
    assert set(by_id.values()) == {"pass"}, by_id


def test_check_1_counts_games(con, tmp_path):
    _load(con, raw_game(), tmp_path)
    r = checks.check_1_game_count(con, 2005, "regular")
    assert r.status == "fail" and r.detail["games"] == 1 and r.detail["expected"] == 1230


def test_expected_regular_season_games():
    assert checks.expected_regular_season_games(2005) == 1230
    assert checks.expected_regular_season_games(2004) == 1189
    assert checks.expected_regular_season_games(1999) == 725
    assert checks.expected_regular_season_games(2021) == 1080


def test_check_2_detects_score_mismatch(con, tmp_path):
    raw = raw_game()
    raw.loc[raw["event_num"] == 2, "shot_pts"] = 3.0  # points no longer add up to the final score
    _load(con, raw, tmp_path)
    r = checks.check_2_points_equal_score(con, 2005, "regular")
    assert r.status == "fail" and r.n_failed == 1


def test_check_3_detects_four_players(con, tmp_path):
    raw = raw_game()
    raw.loc[raw["event_num"] == 3, "lineup_away"] = "11 Away One, 12 Away Two, 13 Away Three, 14 Away Four"
    _load(con, raw, tmp_path)
    r = checks.check_3_five_players(con, 2005, "regular")
    assert r.status == "fail" and r.n_failed == 1 and r.level == "warning"


def test_check_104_duplicate_player_is_hard_and_rolls_back(con, tmp_path):
    raw = raw_game()
    raw.loc[raw["event_num"] == 3, "lineup_away"] = "11 Away One, 11 Away One, 13 Away Three, 14 Away Four, 15 Away Five"

    def hard(c):
        r = checks.check_104_no_duplicate_player_in_lineup(c, 2005, "regular")
        assert r.level == "hard"
        if r.status == "fail":
            raise RuntimeError("hard fail")

    with pytest.raises(RuntimeError, match="hard fail"):
        _load(con, raw, tmp_path, before_commit=hard)
    assert con.sql("SELECT count(*) FROM core.events").fetchone()[0] == 0  # nothing loaded


def test_check_4_detects_inconsistent_sub(con, tmp_path):
    raw = raw_game()
    # Sub row says 6 enters for 5, but the lineup on the sub row still has 5.
    raw.loc[raw["event_num"] == 7, "lineup_home"] = "1 Home One, 2 Home Two, 3 Home Three, 4 Home Four, 5 Home Five"
    _load(con, raw, tmp_path)
    r = checks.check_4_substitutions(con, 2005, "regular")
    assert r.status == "fail" and r.n_failed == 1


def test_check_6_detects_missing_time(con, tmp_path):
    raw = raw_game()
    raw.loc[raw["event_num"] == 3, "lineup_home"] = "1 Home One, 2 Home Two, 3 Home Three, 4 Home Four"
    _load(con, raw, tmp_path)
    r = checks.check_6_player_seconds(con, 2005, "regular")
    assert r.status == "fail"


def test_check_105_time_out_of_range(con, tmp_path):
    _load(con, raw_game(), tmp_path)
    con.execute("UPDATE core.events SET period = 9 WHERE event_seq = 3")
    r = checks.check_105_game_time_in_range(con, 2005, "regular")
    assert r.status == "fail" and r.level == "hard"


def test_check_102_duplicate_keys(con, tmp_path):
    _load(con, raw_game(), tmp_path)
    con.execute("INSERT INTO core.events SELECT * FROM core.events WHERE event_seq = 3")
    assert checks.check_102_unique_event_keys(con, 2005, "regular").status == "fail"


def test_check_106_row_inflation(con, tmp_path):
    staged = _load(con, raw_game(), tmp_path)
    ok = checks.check_106_no_row_inflation(con, 2005, "regular", {"games": 1, "events": len(staged.events)})
    assert ok.status == "pass"
    con.execute("INSERT INTO staging.event_lineups SELECT * FROM staging.event_lineups WHERE event_seq = 3")
    bad = checks.check_106_no_row_inflation(con, 2005, "regular", {"games": 1, "events": len(staged.events)})
    assert bad.status == "fail" and "lineups" in bad.detail["diff"]


def test_check_9_unresolved_player(con, tmp_path):
    _load(con, raw_game(), tmp_path)
    con.execute("UPDATE core.events SET player1_id = 424242 WHERE event_seq = 3")
    r = checks.check_9_ids_resolve(con, 2005, "regular")
    assert r.status == "fail" and r.detail["players"] == [424242]


def test_playoff_series_check(monkeypatch):
    monkeypatch.setattr(checks, "PLAYOFF_SERIES", 1)  # the fixture has one series
    c = db.connect(":memory:")
    # Round 1 series 0 (best of 7 from 2003): team 1 wins 4-1.
    winners = [1, 1, 2, 1, 1]
    for i, w in enumerate(winners, start=1):
        c.execute("INSERT INTO core.games (game_id, season, season_end_year, season_type, game_date, home_team_id, away_team_id, home_score, away_score, num_periods, source) VALUES (?, '2004-05', 2005, 'playoffs', ?, 1, 2, ?, ?, 4, 'test')",
                  [f"00404001{0}{i}", f"2005-04-{20 + i}", 100 if w == 1 else 90, 90 if w == 1 else 100])
    assert checks.check_1_game_count(c, 2005, "playoffs").status == "pass"
    c.execute("DELETE FROM core.games WHERE game_id = '0040400105'")  # series now 3-1: incomplete
    assert checks.check_1_game_count(c, 2005, "playoffs").status == "fail"


def test_playoff_series_game_after_clincher(monkeypatch):
    monkeypatch.setattr(checks, "PLAYOFF_SERIES", 1)
    c = db.connect(":memory:")
    for i, w in enumerate([1, 1, 1, 1, 2], start=1):  # a 5th game after a 4-0 sweep
        c.execute("INSERT INTO core.games (game_id, season, season_end_year, season_type, game_date, home_team_id, away_team_id, home_score, away_score, num_periods, source) VALUES (?, '2004-05', 2005, 'playoffs', ?, 1, 2, ?, ?, 4, 'test')",
                  [f"004040010{i}", f"2005-04-{20 + i}", 100 if w == 1 else 90, 90 if w == 1 else 100])
    r = checks.check_1_game_count(c, 2005, "playoffs")
    assert r.status == "fail" and "after clincher" in r.detail["bad_series"][0]["problem"]


def test_playoff_series_best_of_five_first_round_before_2003(monkeypatch):
    monkeypatch.setattr(checks, "PLAYOFF_SERIES", 1)
    c = db.connect(":memory:")
    for i, w in enumerate([1, 2, 1, 1], start=1):  # 3-1 in a best-of-5 (1997-98 first round)
        c.execute("INSERT INTO core.games (game_id, season, season_end_year, season_type, game_date, home_team_id, away_team_id, home_score, away_score, num_periods, source) VALUES (?, '1997-98', 1998, 'playoffs', ?, 1, 2, ?, ?, 4, 'test')",
                  [f"004970000{i}", f"1998-04-{20 + i}", 100 if w == 1 else 90, 90 if w == 1 else 100])
    assert checks.check_1_game_count(c, 1998, "playoffs").status == "pass"


def _box(overrides=None):
    mins = {1: 48, 2: 48, 3: 48, 4: 48, 5: 1, 6: 47, 11: 48, 12: 48, 13: 48, 14: 48, 15: 48}
    mins.update(overrides or {})
    return pd.DataFrame({"game_id": "0020400001", "player_id": list(mins), "team_id": 0,
                         "box_min": [float(v) for v in mins.values()]})


RULES = {"validation": {"minutes_rounding_tolerance": 1.0, "minutes_large_diff": 5.0}}


def test_check_5_minutes_match_box(con, tmp_path):
    _load(con, raw_game(), tmp_path)
    r = checks.check_5_minutes_vs_box(con, 2005, "regular", box=_box(), rules=RULES)
    assert r.status == "pass" and r.n_checked == 11 and r.level == "warning"


def test_check_5_reports_large_difference_and_missing_players(con, tmp_path):
    _load(con, raw_game(), tmp_path)
    box = _box({6: 40.0})
    box = box[box["player_id"] != 15]  # player 15 played but is missing from the box score
    r = checks.check_5_minutes_vs_box(con, 2005, "regular", box=box, rules=RULES)
    assert r.status == "fail"
    assert r.detail["over_tolerance"] == 1 and r.detail["pbp_only_player_games"] == 1
    assert r.detail["largest_diff_games"][0]["max_diff_min"] == 7.0


def test_check_5_skips_without_cache(con, tmp_path):
    _load(con, raw_game(), tmp_path)
    assert checks.check_5_minutes_vs_box(con, 1900, "regular", rules=RULES).status == "skip"


def test_check_1_compares_box_score_schedule(con, tmp_path, monkeypatch):
    from nba_platform.validate import box_minutes
    _load(con, raw_game(), tmp_path)
    box = _box().assign(game_id="0020400001")
    extra = box.iloc[[0]].assign(game_id="0020409999")  # a game the box score has and we do not
    monkeypatch.setattr(box_minutes, "load_box_minutes", lambda y, t: pd.concat([box, extra]))
    r = checks.check_1_game_count(con, 2005, "regular")
    assert r.detail["box_score_schedule"]["missing_from_ours"] == ["0020409999"]
    assert r.status == "fail"


def test_playoff_load_keeps_regular_season_team_xref(con, tmp_path):
    raw = raw_game()
    _load(con, raw, tmp_path)  # regular season: HOM + AWY
    n_before = con.sql("SELECT count(*) FROM core.team_xref").fetchone()[0]
    po = raw_game("0040400101")
    po["season_type"] = "playoffs"
    po = po[po["team_abb"].isna() | (po["team_abb"] == "HOM") | po["msg_type"].isin([1, 2])]
    xref = rb.derive_team_xref(po, shotdetail_for(po), 2005)
    staged = rb.stage(po, xref, 2005, "playoffs")
    load.load_pbp_season(con, staged, xref.iloc[:1], rb.SOURCE, 2005, "playoffs", out_dir=tmp_path / "po")
    assert con.sql("SELECT count(*) FROM core.team_xref").fetchone()[0] == n_before  # nothing dropped
