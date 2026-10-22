import duckdb
import pytest

from nba_platform.rules import load_rules
from nba_platform.staging import ramirobentes as rb
from nba_platform.staging import shufinskiy as sh
from nba_platform.validate import phase3_prep as prep


def test_rules_yaml_has_decided_thresholds():
    r = load_rules()
    assert r["rules_version"]
    assert r["end_of_period"]["end_of_period_threshold_secs"] == 2
    assert r["substitution_credit"]["method"] is None  # open decision: must stay unset
    assert r["chances"]["boundaries"] == ["offensive_rebound"]
    assert r["garbage_time"]["retroactive_until_game_end"] is True
    gt = r["garbage_time"]
    assert gt["periods"] == [4] and gt["max_combined_starters_on_court"] == 2
    bands = [(b["secs_remaining_max"], b["secs_remaining_min"], b["min_margin"]) for b in gt["margin_thresholds"]]
    assert bands == [(720, 540, 25), (540, 360, 20), (360, 0, 10)]  # owner-checked CTG definition
    assert r["technical_ft"] == {"exclude_from_lineup_efficiency": True, "exclude_from_rapm": True}
    assert r["analysis"]["end_of_period_thresholds_to_compare"] == [2, 3, 5]
    # owner decisions 2026-10-21
    assert r["team_rebound_after_nonfinal_ft"] == "ignore"
    assert r["jump_ball"] == {"possession_change": "other_team_gains_control",
                              "control_team_from": "next_event_with_team", "new_chance": False}
    assert r["free_throws_between_possessions"]["treat_like_technical_ft"] is True
    assert r["after_timeout"] == {"window": "dead_ball_between_possessions", "any_team": True}
    assert r["event_order"] == "source"


def test_rules_yaml_requires_version(tmp_path):
    p = tmp_path / "rules.yaml"
    p.write_text("end_of_period: {end_of_period_threshold_secs: 2}\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_rules(p)


def test_clock_secs_sql():
    assert duckdb.sql(f"SELECT {prep._clock_secs(chr(39) + '11:45' + chr(39))}").fetchone()[0] == 705


have_2005 = (rb.raw_path(2005, "regular").exists()
             and sh.raw_path("pbpstats", 2005, "regular").exists())


@pytest.mark.skipif(not have_2005, reason="2004-05 raw files not downloaded")
def test_prep_facts_2004_05():
    rules = load_rules()
    con = duckdb.connect()
    prep.build(con, 2005, rules)
    f = prep.facts(con, 2005, rules)
    # ramirobentes possession flags and pbpstats possessions (reference numbers)
    assert f["n_rb_poss"] == 227_649
    assert f["n_ps_poss"] == 226_220
    assert len(f["per_game"]) == 1230
    trips, with_sub = f["trips"][0], f["trips"][1]
    assert trips > 20_000 and 0 < with_sub < trips
    assert list(f["eop"]["threshold_s"]) == [2, 3, 5]
    # more seconds -> at least as many possessions
    assert f["eop"]["rb_poss_starting_le_t"].is_monotonic_increasing
    gt_each, gt_retro, gt_all = f["gt"]
    # retroactive CTG flag is a subset of the per-possession condition
    assert 0 < gt_retro <= gt_each < gt_all
    agree, n = f["starters_agree"]
    assert n == gt_all and agree / n > 0.99  # our game-starter count vs the source column


@pytest.mark.skipif(not have_2005, reason="2004-05 raw files not downloaded")
def test_prep_writes_draft_and_csv(tmp_path, monkeypatch):
    monkeypatch.setattr(prep, "DOCS", tmp_path)
    rules = load_rules()
    con = duckdb.connect()
    prep.build(con, 2005, rules)
    f = prep.facts(con, 2005, rules)
    assert 0 < f["poss_with_sub"][0] < f["poss_with_sub"][1]
    md, csv = prep.write(f, 2005, rules)
    text = md.read_text(encoding="utf-8")
    for case in ("End-of-period", "Substitution during a possession", "Offensive rebound", "Flagrant",
                 "Technical free throws", "Team rebound", "Jump ball", "start type", "Garbage time"):
        assert case.lower() in text.lower(), case
    assert "**open**" in text  # the open rule is not decided by the draft
    assert sum(1 for _ in open(csv, encoding="utf-8")) == 1231


def test_rule_profiles_copy_then_deviate():
    compat = load_rules(profile="pbpstats_compat")
    custom = load_rules(profile="custom")
    assert compat["profile"] == "pbpstats_compat" and custom["profile"] == "custom"
    assert compat["substitution_credit"] == {"method": "pbpstats_hybrid",
                                             "possessions_to": "lineup_at_possession_end",
                                             "free_throw_points_to": "lineup_at_foul"}
    assert custom["substitution_credit"]["method"] is None  # still open in the owner's profile
    assert custom["technical_ft"]["exclude_from_lineup_efficiency"] is True
    # shared values are untouched by either profile
    assert compat["end_of_period"] == custom["end_of_period"] == load_rules()["end_of_period"]
    with pytest.raises(ValueError):
        load_rules(profile="nope")
