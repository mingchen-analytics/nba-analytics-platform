"""RAPM prototype: design matrix, grouped cross-validation, recovery of known effects, loader and mart."""

import numpy as np
import pandas as pd
import pytest
from sklearn.model_selection import GroupKFold

from nba_platform import db
from nba_platform.metrics import rapm

CFG = {"credit": "end_lineup", "exclude_end_of_period_heave": True, "exclude_garbage_time": True, "min_possessions_for_own_column": 1,
       "cv_folds": 4, "alpha_log10_start": 0.0, "alpha_log10_stop": 4.0, "alpha_grid_size": 9, "max_grid_extensions": 2, "seed": 7,
       "split_half_min_possessions": 1}


def _simulate(n_players=30, n_poss=60_000, seed=1, signal=0.04, home=0.03, noise=1.0):
    rng = np.random.default_rng(seed)
    o, d = rng.normal(0, signal, n_players), rng.normal(0, signal, n_players)
    ids = np.arange(101, 101 + n_players)
    rows = []
    for _ in range(n_poss):
        ten = rng.permutation(n_players)[:10]
        rows.append(ten)
    ten = np.array(rows)
    is_home = rng.random(n_poss) < 0.5
    y = 1.05 + o[ten[:, :5]].sum(1) + d[ten[:, 5:]].sum(1) + home * is_home + rng.normal(0, noise, n_poss)
    obs = pd.DataFrame({"game_id": [f"G{i // 100}" for i in range(n_poss)], "points": y, "offense_is_home": is_home})
    for i in range(5):
        obs[rapm.OFF_COLS[i]], obs[rapm.DEF_COLS[i]] = ids[ten[:, i]], ids[ten[:, 5 + i]]
    return obs, pd.DataFrame({"player_id": ids, "o": o, "d": d})


def _obs(rows):
    return pd.DataFrame(rows, columns=["game_id", "points", "offense_is_home", *rapm.OFF_COLS, *rapm.DEF_COLS])


def test_bucket_players_pools_the_low_possession_players():
    obs = _obs([("G1", 2, True, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10)] * 3 + [("G2", 0, False, 1, 2, 3, 4, 11, 6, 7, 8, 9, 10)])
    p = rapm.bucket_players(obs, 4).set_index("player_id")
    assert p.loc[1, "off_poss"] == 4 and p.loc[6, "def_poss"] == 4 and p.loc[11, "off_poss"] == 1
    assert p["own_column"].to_dict() == {1: True, 2: True, 3: True, 4: True, 5: False, 6: True, 7: True, 8: True, 9: True, 10: True, 11: False}


def test_design_matrix_columns_replacement_sums_and_home():
    obs = _obs([("G1", 2, True, 1, 2, 90, 91, 92, 6, 7, 8, 9, 93), ("G2", 0, False, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10)])
    x, names = rapm.design_matrix(obs, np.array([1, 2, 6]))
    assert x.shape == (2, 2 * 3 + 3) and names[-3:] == ["off:replacement", "def:replacement", "home_court"]
    row = x.toarray()[0]
    assert row[names.index("off:1")] == 1 and row[names.index("off:2")] == 1 and row[names.index("def:6")] == 1
    assert row[names.index("off:replacement")] == 3 and row[names.index("def:replacement")] == 4   # 90-92 off; 7, 8, 9, 93 def
    assert row[names.index("home_court")] == 1 and x.toarray()[1][names.index("home_court")] == 0
    assert x.toarray()[1][names.index("off:replacement")] == 3                                      # 3, 4, 5 have no own column


def test_known_effects_are_recovered_and_defense_sign_is_good_when_positive():
    obs, truth = _simulate()
    res = rapm.fit(obs, CFG)
    m = res["players"].merge(truth, on="player_id")
    assert m["o_rapm"].corr(m["o"]) > 0.8 and m["d_rapm"].corr(-m["d"]) > 0.8   # true d is points allowed: bad when positive
    assert abs(res["home_points_per100"] - 3.0) < 1.5 and abs(res["intercept_per100"] - 105.0) < 3.0
    assert res["cv"]["baseline_mse"] > res["cv"]["table"]["mean_mse"].min()      # the model beats predicting the mean


def test_cross_validation_never_splits_a_game():
    obs, _ = _simulate(n_poss=4_000)
    groups = obs["game_id"].to_numpy()
    for tr, te in GroupKFold(n_splits=4, shuffle=True, random_state=7).split(obs, groups=groups):
        assert not set(groups[tr]) & set(groups[te])


def test_grid_is_extended_when_the_best_penalty_sits_at_the_edge():
    rng = np.random.default_rng(3)
    obs, _ = _simulate(n_poss=20_000, signal=0.0)           # no signal at all: the best penalty is the largest one
    x, _ = rapm.design_matrix(obs, np.arange(101, 131))
    cv = rapm.cv_alpha(x, obs["points"].to_numpy(), obs["game_id"].to_numpy(), CFG)
    assert cv["extensions"] >= 1 and cv["alpha"] > 1e4 * 0.99
    assert (cv["table"]["alpha"].diff().dropna() > 0).all()


def test_split_half_returns_a_correlation_for_players_in_both_halves():
    obs, _ = _simulate(n_poss=40_000)
    half = rapm.split_half(obs, CFG, alpha=300.0)
    assert half["players"] == 30 and half["r_rapm"] > 0.3


@pytest.fixture
def con():
    c = db.connect(":memory:")
    for g in range(1, 7):
        gid = f"G{g}"
        c.execute("INSERT INTO core.games VALUES (?, '2024-25', 2025, 'regular', NULL, 1, 2, 0, 0, 4, 't', FALSE, NULL)", [gid])
        c.execute("INSERT INTO core.stints VALUES (?, 1, 1, 0, 100, 1, 20, 'period_start', 5, 11, 12, 13, 14, 15, 21, 22, 23, 24, 25, 'v1')", [gid])
        for pid, off, pts, heave, garbage in ((1, 1, 2, False, False), (2, 2, 0, True, False), (3, 1, 3, False, True), (4, 2, 1, False, False)):
            c.execute("INSERT INTO core.possessions (game_id, possession_id, offense_team_id, defense_team_id, period, start_secs, end_secs, "
                      "start_event_seq, end_event_seq, start_type, end_type, points, num_chances, secs_remaining_period_at_start, "
                      "secs_remaining_game_at_start, is_end_of_period_heave, is_garbage_time, is_after_timeout, rules_version, rules_profile) "
                      "VALUES (?, ?, ?, ?, 1, 0, 0, 1, 1, 's', 'e', ?, 1, 0, 0, ?, ?, FALSE, 'v1', 'pbpstats_compat')",
                      [gid, pid, off, 3 - off, pts, heave, garbage])
            c.execute("INSERT INTO core.possession_stint_segments VALUES (?, ?, 1, 1, 1, 1, 0, 0)", [gid, pid])
    yield c
    c.close()


def test_loader_applies_the_exclusions_and_orients_offense_and_defense(con):
    both = rapm.load_possessions(con, [(2025, "regular")], CFG)
    assert len(both) == 12 and sorted(both["points"].unique()) == [1, 2]            # heave (0 pts) and garbage (3 pts) out
    row = both[both["points"] == 2].iloc[0]
    assert (row["off_1"], row["def_1"], bool(row["offense_is_home"])) == (11, 21, True)
    row = both[both["points"] == 1].iloc[0]
    assert (row["off_1"], row["def_1"], bool(row["offense_is_home"])) == (21, 11, False)
    assert len(rapm.load_possessions(con, [(2025, "regular")], {**CFG, "exclude_garbage_time": False})) == 18
    assert len(rapm.load_possessions(con, [(2025, "regular")], {**CFG, "exclude_end_of_period_heave": False, "exclude_garbage_time": False})) == 24
    with pytest.raises(rapm.RapmError, match="no possessions"):
        rapm.load_possessions(con, [(2019, "regular")], CFG)


def test_build_writes_the_mart_replaces_a_window_and_records_the_choices(con):
    cfg = {**CFG, "cv_folds": 3}
    out = rapm.build(con, [(2025, "regular")], cfg)
    assert out["window"] == "2024-25 regular" and out["players"] == 10 and out["observations"] == 12
    row = con.execute("SELECT credit_method, exclude_end_of_period_heave, exclude_garbage_time, rules_version, rules_profile "
                      "FROM marts.player_rapm LIMIT 1").fetchone()
    assert row == ("end_lineup", True, True, "v1", "pbpstats_compat")
    rapm.build(con, [(2025, "regular")], cfg)
    assert con.execute("SELECT count(*) FROM marts.player_rapm").fetchone()[0] == 10   # replaced, not appended


def test_window_ids():
    assert rapm.window_id([(2025, "regular")]) == "2024-25 regular"
    assert rapm.window_id([(2024, "regular"), (2025, "regular"), (2023, "regular")]) == "2022-23 + 2023-24 + 2024-25 regular"
    assert rapm.window_id([(2025, "regular"), (2025, "playoffs")]) == "2024-25 regular, 2024-25 playoffs"


def test_mixed_rules_versions_fail(con):
    con.execute("UPDATE core.possessions SET rules_profile = 'custom' WHERE game_id = 'G1' AND possession_id = 1")
    with pytest.raises(rapm.RapmError, match="rules versions"):
        rapm.build(con, [(2025, "regular")], {**CFG, "cv_folds": 3})


def test_bootstrap_standard_errors_are_positive_reproducible_and_grow_with_noise():
    quiet, _ = _simulate(n_poss=20_000, noise=0.5, seed=4)
    loud, _ = _simulate(n_poss=20_000, noise=2.0, seed=4)
    a = rapm.fit(quiet, CFG, alpha=300.0, bootstrap=12)["players"]
    b = rapm.fit(loud, CFG, alpha=300.0, bootstrap=12)["players"]
    assert {"o_se", "d_se", "rapm_se"} <= set(a.columns) and (a["rapm_se"] > 0).all()
    assert b["rapm_se"].mean() > 2 * a["rapm_se"].mean()                      # four times the noise variance
    again = rapm.fit(quiet, CFG, alpha=300.0, bootstrap=12)["players"]
    assert np.allclose(a["rapm_se"], again["rapm_se"])                         # same seed, same resamples
    assert "rapm_se" not in rapm.fit(quiet, CFG, alpha=300.0)["players"].columns


def test_mart_keeps_the_standard_errors_and_adds_the_columns_to_an_older_table(con):
    con.execute("CREATE SCHEMA IF NOT EXISTS marts")
    con.execute("CREATE TABLE marts.player_rapm (window_id TEXT NOT NULL, player_id INTEGER NOT NULL, off_poss INTEGER NOT NULL, def_poss INTEGER NOT NULL, "
                "o_rapm DOUBLE NOT NULL, d_rapm DOUBLE NOT NULL, rapm DOUBLE NOT NULL, alpha DOUBLE NOT NULL, n_obs INTEGER NOT NULL, "
                "home_points_per100 DOUBLE NOT NULL, credit_method TEXT NOT NULL, exclude_end_of_period_heave BOOLEAN NOT NULL, "
                "exclude_garbage_time BOOLEAN NOT NULL, min_possessions_for_own_column INTEGER NOT NULL, rules_version TEXT NOT NULL, "
                "rules_profile TEXT NOT NULL, PRIMARY KEY (window_id, player_id))")
    rapm.build(con, [(2025, "regular")], {**CFG, "cv_folds": 3, "bootstrap_samples": 5})
    assert con.execute("SELECT count(*) FILTER (rapm_se > 0), count(*) FROM marts.player_rapm").fetchone() == (10, 10)
    rapm.build(con, [(2025, "regular")], {**CFG, "cv_folds": 3, "bootstrap_samples": 0})
    assert con.execute("SELECT count(*) FILTER (rapm_se IS NULL) FROM marts.player_rapm").fetchone()[0] == 10   # NULL, never an invented 0


# ------------------------------------------------------------------ luck adjustment, variants, windows, forecast check

LUCK_CFG = {**CFG, "luck_adjustment": {"three_prior_attempts": 2, "ft_prior_attempts": 1}}


@pytest.fixture
def luck_con():
    """One game: possessions that exercise the adjustment (three-point makes and misses, a free throw, a two, an unknown shot type)."""
    c = db.connect(":memory:")
    c.execute("INSERT INTO core.games VALUES ('GA', '2024-25', 2025, 'regular', NULL, 1, 2, 0, 0, 4, 't', FALSE, NULL)")
    c.execute("INSERT INTO core.stints VALUES ('GA', 1, 1, 0, 100, 1, 20, 'period_start', 5, 11, 12, 13, 14, 15, 21, 22, 23, 24, 25, 'v1')")
    spec = [  # possession, offense team, points, event type, shooter, shooter's team, source_event_num, shot type (None = no row in core.shots)
        (1, 1, 3, "shot_made", 11, 1, 101, "3PT Field Goal"), (2, 2, 0, "shot_missed", 21, 2, 102, "3PT Field Goal"),
        (3, 1, 2, "shot_made", 12, 1, 103, "2PT Field Goal"), (4, 2, 1, "free_throw", 21, 2, 104, None),
        (5, 1, 3, "shot_made", 11, 1, 105, "3PT Field Goal"), (6, 1, 0, "shot_missed", 11, 1, 106, None)]
    for pid, off, pts, kind, shooter, team, num, shot_type in spec:
        c.execute("INSERT INTO core.possessions (game_id, possession_id, offense_team_id, defense_team_id, period, start_secs, end_secs, start_event_seq, "
                  "end_event_seq, start_type, end_type, points, num_chances, secs_remaining_period_at_start, secs_remaining_game_at_start, "
                  "is_end_of_period_heave, is_garbage_time, is_after_timeout, rules_version, rules_profile) "
                  "VALUES ('GA', ?, ?, ?, 1, 0, 0, 1, 1, 's', 'e', ?, 1, 100, 100, FALSE, FALSE, FALSE, 'v1', 'pbpstats_compat')", [pid, off, 3 - off, pts])
        c.execute("INSERT INTO core.possession_stint_segments VALUES ('GA', ?, 1, 1, 1, 1, 0, 0)", [pid])
        c.execute("INSERT INTO core.events (game_id, event_seq, source_event_num, period, secs_elapsed_game, team_id, event_type, player1_id, points, stint_id, "
                  "possession_id, source) VALUES ('GA', ?, ?, 1, 1, ?, ?, ?, ?, 1, ?, 't')", [pid, num, team, kind, shooter, pts, pid])
        if shot_type:
            c.execute("INSERT INTO core.shots (game_id, source_event_num, player_id, team_id, shot_type, made, source) VALUES ('GA', ?, ?, ?, ?, ?, 't')",
                      [num, shooter, team, shot_type, pts > 0])
    yield c
    c.close()


def test_luck_adjustment_replaces_the_result_of_three_point_attempts_and_free_throws_with_the_expected_one(luck_con):
    raw = rapm.load_possessions(luck_con, [(2025, "regular")], LUCK_CFG, luck=False)
    adj = rapm.load_possessions(luck_con, [(2025, "regular")], LUCK_CFG, luck=True)
    assert raw["points_adj"].tolist() == raw["points"].tolist() == [3, 0, 2, 1, 3, 0]            # without luck: the actual points
    league = 2 / 3                                                                                # 2 of 3 threes (the unknown-type shot is not counted)
    p11 = (2 + 2 * league) / (2 + 2)                                                              # shooter 11: 2 of 2, prior 2 attempts
    p21 = (0 + 2 * league) / (1 + 2)                                                              # shooter 21: 0 of 1
    expected = [3 * p11, 3 * p21, 2, 1, 3 * p11, 0]                                               # the two, the free throw (league 100 %) and the unknown type keep their result
    assert adj["points_adj"].tolist() == pytest.approx(expected)
    assert adj["points"].tolist() == [3, 0, 2, 1, 3, 0]                                           # the actual points stay


def test_expected_points_conserve_the_league_total_with_no_prior(luck_con):
    """A shooter's own rate without shrinkage gives back his actual total: the adjustment moves points between possessions, not into thin air."""
    cfg = {**CFG, "luck_adjustment": {"three_prior_attempts": 0, "ft_prior_attempts": 0}}
    adj = rapm.load_possessions(luck_con, [(2025, "regular")], cfg, luck=True)
    assert adj["points_adj"].sum() == pytest.approx(adj["points"].sum())


def test_an_unknown_variant_fails(luck_con):
    with pytest.raises(rapm.RapmError, match="unknown variant"):
        rapm.build(luck_con, [(2025, "regular")], LUCK_CFG, variant="bogus")


def test_windows_cover_every_season_and_every_trailing_three():
    w = rapm.windows(1997, 2000)
    assert [x for x in w if len(x) == 1] == [[(y, "regular")] for y in (1997, 1998, 1999, 2000)]
    assert [x for x in w if len(x) == 3] == [[(1997, "regular"), (1998, "regular"), (1999, "regular")], [(1998, "regular"), (1999, "regular"), (2000, "regular")]]


def test_fit_uses_the_chosen_outcome_column():
    obs, _ = _simulate(n_poss=20_000, signal=0.04, seed=11)
    obs["points_adj"] = obs["points"] + 5.0                                     # a constant shift moves only the intercept
    a = rapm.fit(obs, CFG, alpha=300.0, y_col="points")["players"]
    b = rapm.fit(obs, CFG, alpha=300.0, y_col="points_adj")["players"]
    assert np.allclose(a["rapm"], b["rapm"], atol=1e-6)
    flipped = obs.assign(points_adj=-obs["points"])
    c = rapm.fit(flipped, CFG, alpha=300.0, y_col="points_adj")["players"]
    assert np.allclose(c["o_rapm"], -a["o_rapm"], atol=1e-6)                    # a different outcome gives different ratings


def test_player_rapm_table_is_migrated_to_the_variant_key(con):
    con.execute("CREATE SCHEMA IF NOT EXISTS marts")
    con.execute("CREATE TABLE marts.player_rapm (window_id TEXT NOT NULL, player_id INTEGER NOT NULL, off_poss INTEGER NOT NULL, def_poss INTEGER NOT NULL, "
                "o_rapm DOUBLE NOT NULL, d_rapm DOUBLE NOT NULL, rapm DOUBLE NOT NULL, alpha DOUBLE NOT NULL, n_obs INTEGER NOT NULL, "
                "home_points_per100 DOUBLE NOT NULL, credit_method TEXT NOT NULL, exclude_end_of_period_heave BOOLEAN NOT NULL, "
                "exclude_garbage_time BOOLEAN NOT NULL, min_possessions_for_own_column INTEGER NOT NULL, rules_version TEXT NOT NULL, "
                "rules_profile TEXT NOT NULL, PRIMARY KEY (window_id, player_id))")
    con.execute("INSERT INTO marts.player_rapm VALUES ('w', 7, 10, 10, 1.0, 1.0, 2.0, 100.0, 5, 1.0, 'end_lineup', TRUE, TRUE, 1, 'v1', 'pbpstats_compat')")
    rapm._ensure_tables(con)
    assert con.execute("SELECT variant, rapm, window_id FROM marts.player_rapm").fetchall() == [("raw", 2.0, "w")]
    with pytest.raises(Exception):   # the key includes the variant: the same player of the same window exists once per variant, not twice
        con.execute("INSERT INTO marts.player_rapm (window_id, variant, player_id, off_poss, def_poss, o_rapm, d_rapm, rapm, alpha, n_obs, home_points_per100, "
                    "credit_method, exclude_end_of_period_heave, exclude_garbage_time, min_possessions_for_own_column, rules_version, rules_profile) "
                    "VALUES ('w', 'raw', 7, 1, 1, 0, 0, 0, 1, 1, 0, 'x', TRUE, TRUE, 1, 'v', 'p')")


def test_skill_measures_correlation_and_rescaled_error():
    actual = np.array([-4.0, -1.0, 0.0, 2.0, 5.0])
    s = rapm._skill(actual, actual * 0.5 + 1.0)            # perfectly informative, wrong scale
    assert s["r"] == pytest.approx(1.0) and s["rmse"] == pytest.approx(0.0, abs=1e-9) and s["slope"] == pytest.approx(2.0)
