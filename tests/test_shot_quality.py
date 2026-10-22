import pandas as pd

from nba_platform.validate import shot_quality as sq


def test_shot_type_groups():
    g = sq._type_group(pd.Series(["Driving Layup Shot", "Jump Shot", "Slam Dunk Shot", "Tip Shot", "Hook Shot", None]))
    assert g.tolist() == ["layup", "jump shot", "dunk", "tip", "hook", "other"]


def test_shot_profile_counts_zero_coordinates():
    s = pd.DataFrame({"LOC_X": [0, 0, 10, 50], "LOC_Y": [0, 0, 100, 200], "SHOT_DISTANCE": [0, 0, 10, 20],
                      "ACTION_TYPE": ["Layup Shot", "Jump Shot", "Jump Shot", "Jump Shot"],
                      "SHOT_TYPE": ["2PT Field Goal"] * 4})
    p = sq.profile(s)
    assert p["xy_zero"] == 0.5 and p["jump_at_0ft"] == 0.25 and p["shots"] == 4



def test_profile_counts_non_rim_shots_at_zero():
    s = pd.DataFrame({"LOC_X": [0, 0, 0, 10], "LOC_Y": [0, 0, 0, 100], "SHOT_DISTANCE": [0, 0, 0, 10],
                      "ACTION_TYPE": ["Layup Shot", "Jump Shot", "Dunk Shot", "Jump Shot"],
                      "SHOT_TYPE": ["2PT Field Goal", "3PT Field Goal", "2PT Field Goal", "2PT Field Goal"]})
    p = sq.profile(s)
    assert p["n_xy_zero"] == 3 and p["xy0_jump"] == 1 and p["xy0_3pt"] == 1 and p["xy0_dist_gt0"] == 0
    assert abs(p["xy0_rim_types"] - 2 / 3) < 1e-9


def test_write_flags_keeps_flags_outside_shots():
    from nba_platform import db
    c = db.connect(":memory:")
    c.execute("""INSERT INTO core.games (game_id, season, season_end_year, season_type, home_team_id, away_team_id, source)
                 VALUES ('0029600001', '1996-97', 1997, 'regular', 1, 2, 't'), ('0021000001', '2010-11', 2011, 'regular', 1, 2, 't')""")
    c.execute("""INSERT INTO core.shots (game_id, source_event_num, player_id, team_id, shot_type, action_type,
                 distance_ft, loc_x, loc_y, made, source) VALUES
                 ('0029600001', 1, 1, 1, '2PT Field Goal', 'Layup Shot', 0, 0, 0, true, 't'),
                 ('0029600001', 2, 1, 1, '3PT Field Goal', 'Jump Shot', 0, 0, 0, false, 't'),
                 ('0021000001', 3, 1, 1, '2PT Field Goal', 'Layup Shot', 1, 5, 5, true, 't')""")
    prof = pd.DataFrame({"season_end_year": [1997, 2011], "season_type": ["regular", "regular"], "xy_zero": [0.3, 0.0]})
    flags = sq.write_flags(c, prof, 0.05, {1997})
    assert flags == {"early_season_location_suspect": 2, "rim_location_imprecise": 2, "rim_location_suspect": 1}
    c.execute("DELETE FROM core.shots")  # a reload of shots ...
    assert c.execute("SELECT count(*) FROM core.shot_quality_flags").fetchone()[0] == 5  # ... keeps the flags
