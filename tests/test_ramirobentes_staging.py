import pandas as pd
import pytest

from nba_platform.staging import ramirobentes as rb


def _stage(raw, shotdetail, corrections=None):
    xref = rb.derive_team_xref(raw, shotdetail, 2005)
    return rb.stage(raw, xref, 2005, "regular", corrections), xref


# ----------------------------------------------------------------- parsing helpers


def test_parse_player_keys_splits_id_and_name_and_keeps_null():
    out = rb.parse_player_keys(pd.Series(["1477 Bruce Bowen", None, "2 Nenê"]))
    assert out["player_id"].tolist()[0] == 1477
    assert pd.isna(out["player_id"].iloc[1])
    assert out["name"].tolist()[2] == "Nenê"


@pytest.mark.parametrize("bad", ["Bruce Bowen", "1477", "1477Bruce", " 1477 Bruce"])
def test_parse_player_keys_fails_loudly(bad):
    with pytest.raises(rb.StagingError):
        rb.parse_player_keys(pd.Series([bad]))


def test_parse_lineups_keeps_source_order_and_empty_for_null():
    ids, keys = rb.parse_lineups(pd.Series(["5 E, 1 A, 3 C", None]))
    assert ids.tolist() == [[5, 1, 3], []]
    assert set(keys["name"]) == {"A", "C", "E"}


def test_parse_lineups_fails_on_name_with_comma():
    # A comma inside a name would produce a fragment that is not 'ID Name'.
    with pytest.raises(rb.StagingError):
        rb.parse_lineups(pd.Series(["1 Smith, Jr., 2 B"]))


@pytest.mark.parametrize(
    "period, clock, expected",
    [(1, "12:00", 0), (1, "11:45", 15), (4, "00:00", 2880), (5, "05:00", 2880), (5, "00:00", 3180),
     (7, "02:30", 3480 + 150), (2, "0:45.5", 720 + 720 - 45.5)],
)
def test_clock_to_secs_elapsed(period, clock, expected):
    out = rb.clock_to_secs_elapsed(pd.Series([float(period)]), pd.Series([clock]))
    assert out.iloc[0] == pytest.approx(expected)


def test_clock_unparseable_fails():
    with pytest.raises(rb.StagingError):
        rb.clock_to_secs_elapsed(pd.Series([1.0]), pd.Series(["PT11M45.00S"]))


def test_map_team_abbr_unknown_fails():
    with pytest.raises(rb.StagingError):
        rb.map_team_abbr(pd.Series(["LAL", "XXX"]), {"LAL": 1}, "team_abb")


# ----------------------------------------------------------------- team xref


def test_team_xref_maps_each_abbreviation_once(raw, shotdetail):
    xref = rb.derive_team_xref(raw, shotdetail, 2005)
    assert dict(zip(xref["source_team_key"], xref["team_id"])) == {"HOM": 1610612701, "AWY": 1610612702}
    assert set(xref["method"]) == {"auto"}


def test_team_xref_fails_when_abbreviation_has_two_ids(raw, shotdetail):
    shotdetail.loc[shotdetail.index[0], "TEAM_ID"] = 999
    extra = shotdetail.iloc[[0]].assign(TEAM_ID=1610612702, GAME_EVENT_ID=3)  # AWY now -> 2 ids
    with pytest.raises(rb.StagingError):
        rb.derive_team_xref(raw, pd.concat([shotdetail, extra]), 2005)


def test_team_xref_fails_when_team_has_no_shot(raw, shotdetail):
    with pytest.raises(rb.StagingError, match="no shotdetail match"):
        rb.derive_team_xref(raw, shotdetail[shotdetail["TEAM_ID"] == 1610612701], 2005)


# ----------------------------------------------------------------- stage


def test_stage_games(raw, shotdetail):
    staged, _ = _stage(raw, shotdetail)
    g = staged.games.iloc[0]
    assert (g.game_id, g.season, g.season_end_year, g.season_type) == ("0020400001", "2004-05", 2005, "regular")
    assert (g.home_team_id, g.away_team_id, g.home_score, g.away_score, g.num_periods) == (
        1610612701, 1610612702, 3, 2, 4)


def test_stage_excludes_and_counts_synthetic_rows(raw, shotdetail):
    staged, _ = _stage(raw, shotdetail)
    assert staged.n_synthetic_rows == 1
    assert len(staged.events) == len(raw) - 1
    assert 9999 not in staged.events["source_event_num"].tolist()


def test_stage_synthetic_row_with_real_event_num_fails(raw, shotdetail):
    raw.loc[raw["msg_type"] == 99, "event_num"] = 50.0
    with pytest.raises(rb.StagingError, match="synthetic"):
        _stage(raw, shotdetail)


def test_stage_event_seq_is_dense_and_follows_number_event(raw, shotdetail):
    staged, _ = _stage(raw, shotdetail)
    assert staged.events["event_seq"].tolist() == list(range(1, len(staged.events) + 1))
    assert staged.events["source_event_num"].is_monotonic_increasing


def test_stage_event_types_points_and_players(raw, shotdetail):
    staged, _ = _stage(raw, shotdetail)
    e = staged.events.set_index("source_event_num")
    assert e.loc[2, "event_type"] == "shot_made" and e.loc[2, "points"] == 2
    assert e.loc[3, "event_type"] == "shot_missed" and e.loc[3, "points"] == 0
    assert e.loc[6, "event_type"] == "free_throw" and e.loc[6, "event_subtype"] == 11
    assert e.loc[7, "event_type"] == "substitution"
    assert (e.loc[7, "player1_id"], e.loc[7, "player2_id"]) == (5, 6)
    assert pd.isna(e.loc[4, "player1_id"]) and e.loc[4, "team_id"] == 1610612702  # team rebound
    assert pd.isna(e.loc[0, "team_id"])  # period start
    assert staged.events.groupby("team_id")["points"].sum().to_dict() == {1610612701: 3, 1610612702: 2}


def _xref_then_mutate(raw, shotdetail, row, col, value):
    xref = rb.derive_team_xref(raw, shotdetail, 2005)
    raw.loc[raw["event_num"] == row, col] = value
    return xref


def test_stage_unknown_msg_type_fails(raw, shotdetail):
    xref = _xref_then_mutate(raw, shotdetail, 4, "msg_type", 42.0)
    with pytest.raises(rb.StagingError, match="msg_type"):
        rb.stage(raw, xref, 2005, "regular")


def test_stage_unknown_team_fails(raw, shotdetail):
    xref = _xref_then_mutate(raw, shotdetail, 4, "team_abb", "ZZZ")
    with pytest.raises(rb.StagingError, match="unmapped team"):
        rb.stage(raw, xref, 2005, "regular")


def test_team_xref_fails_on_abbreviation_without_shots(raw, shotdetail):
    raw.loc[raw["event_num"] == 4, "team_abb"] = "ZZZ"
    with pytest.raises(rb.StagingError, match="no shotdetail match"):
        rb.derive_team_xref(raw, shotdetail, 2005)


def test_stage_wrong_season_fails(raw, shotdetail):
    xref = rb.derive_team_xref(raw, shotdetail, 2005)
    with pytest.raises(rb.StagingError, match="season"):
        rb.stage(raw, xref, 2006, "regular")


def test_stage_duplicate_event_num_fails(raw, shotdetail):
    xref = _xref_then_mutate(raw, shotdetail, 5, "event_num", 4.0)
    with pytest.raises(rb.StagingError, match="event_num"):
        rb.stage(raw, xref, 2005, "regular")


def test_stage_lineups_are_source_lineups(raw, shotdetail):
    staged, _ = _stage(raw, shotdetail)
    lu = staged.lineups.set_index(staged.events["source_event_num"])
    assert lu.loc[6, "home_player_ids"] == [1, 2, 3, 4, 5]
    # ramirobentes shows the post-sub lineup on the sub row itself (docs/decisions.md)
    assert lu.loc[7, "home_player_ids"] == [1, 2, 3, 4, 6]
    assert lu.loc[7, "away_player_ids"] == [11, 12, 13, 14, 15]


def test_stage_player_names(raw, shotdetail):
    staged, _ = _stage(raw, shotdetail)
    names = dict(zip(staged.player_names["player_id"], staged.player_names["name"]))
    assert names[6] == "Home Six" and names[15] == "Away Five"
    assert set(staged.player_names["source_player_key"]) >= {"6 Home Six", "11 Away One"}


# ----------------------------------------------------------------- corrections


def _corr(**kw):
    base = dict(game_id="0020400001", source_event_num="3", field="player1_name",
                old_value="2 Home Two", new_value="3 Home Three", reason="test", added_on="2026-10-16")
    base.update(kw)
    return pd.DataFrame([base])


def test_correction_is_applied_in_staging(raw, shotdetail):
    staged, _ = _stage(raw, shotdetail, _corr())
    assert staged.n_corrections_applied == 1
    assert staged.events.set_index("source_event_num").loc[3, "player1_id"] == 3
    assert raw.loc[raw["event_num"] == 3, "player1_name"].iloc[0] == "2 Home Two"  # raw untouched


def test_correction_with_wrong_old_value_fails(raw, shotdetail):
    with pytest.raises(rb.StagingError, match="old_value"):
        _stage(raw, shotdetail, _corr(old_value="9 Nobody"))


def test_correction_numeric_field(raw, shotdetail):
    staged, _ = _stage(raw, shotdetail, _corr(field="shot_pts", source_event_num="2", old_value="2", new_value="3"))
    assert staged.events.set_index("source_event_num").loc[2, "points"] == 3


def test_correction_for_other_game_is_ignored(raw, shotdetail):
    staged, _ = _stage(raw, shotdetail, _corr(game_id="0029999999"))
    assert staged.n_corrections_applied == 0


def test_stage_number_event_tie_is_ordered_by_event_num_and_reported(raw, shotdetail):
    xref = rb.derive_team_xref(raw, shotdetail, 2005)
    # event_num 6 and 7 now share number_event 7 (seen in older seasons); put 7 first in the file
    raw.loc[raw["event_num"] == 7, "number_event"] = 7.0
    raw = raw.iloc[[0, 1, 2, 3, 4, 5, 7, 6] + list(range(8, len(raw)))].reset_index(drop=True)
    staged = rb.stage(raw, xref, 2005, "regular")
    e = staged.events
    seq = dict(zip(e["source_event_num"], e["event_seq"]))
    assert seq[6] < seq[7]
    assert sorted(staged.order_ties["event_num"].tolist()) == [6.0, 7.0]


def test_team_xref_dominant_share_tolerates_join_noise(raw, shotdetail):
    # 200 HOM shots joined, 1 of them to another TEAM_ID: mapping stays, noise is counted.
    extra = []
    for i in range(199):
        extra.append({**shotdetail.iloc[1].to_dict(), "GAME_EVENT_ID": 1000 + i})
    noisy = shotdetail.iloc[[1]].assign(GAME_EVENT_ID=2000, TEAM_ID=1610612799, TEAM_NAME="Other")
    sd = pd.concat([shotdetail, pd.DataFrame(extra), noisy], ignore_index=True)
    rows = [raw] + [raw[raw["event_num"] == 3].assign(event_num=float(1000 + i), number_event=100.0 + i)
                    for i in range(199)]
    rows.append(raw[raw["event_num"] == 3].assign(event_num=2000.0, number_event=400.0))
    big = pd.concat(rows, ignore_index=True)
    xref = rb.derive_team_xref(big, sd, 2005)
    hom = xref.set_index("source_team_key").loc["HOM"]
    assert hom["team_id"] == 1610612701 and hom["n_conflicting"] == 1 and hom["n_joined_shots"] == 200
