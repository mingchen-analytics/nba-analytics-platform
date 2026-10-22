import json

import pandas as pd
import pytest

from nba_platform import db
from nba_platform.reference import player_box as pb

HEADERS = ["SEASON_ID", "PLAYER_ID", "PLAYER_NAME", "TEAM_ID", "TEAM_ABBREVIATION", "TEAM_NAME", "GAME_ID",
           "GAME_DATE", "MATCHUP", "WL", "MIN", "FGM", "FGA", "FG_PCT", "FG3M", "FG3A", "FG3_PCT", "FTM", "FTA",
           "FT_PCT", "OREB", "DREB", "REB", "AST", "STL", "BLK", "TOV", "PF", "PTS", "PLUS_MINUS",
           "FANTASY_PTS", "VIDEO_AVAILABLE"]


def _row(player_id, game_id=20400001, pts=10, fg3a=2):
    return ["22004", player_id, "X", 1610612701, "HOM", "Home", game_id, "2004-11-02", "HOM vs. AWY", "W", 30,
            4, 8, 0.5, 1, fg3a, 0.5, 1, 2, 0.5, 1, 3, 4, 5, 1, 0, 2, 3, pts, 7, 0, 1]


def _write(tmp_path, rows, name="leaguegamelog_P_2005_regular.json"):
    (tmp_path / name).write_text(json.dumps({"resultSets": [{"headers": HEADERS, "rowSet": rows}]}))


def _con_with_game():
    con = db.connect(":memory:")
    con.execute("""INSERT INTO core.games (game_id, season, season_end_year, season_type, home_team_id, away_team_id,
                   home_score, away_score, source) VALUES ('0020400001', '2004-05', 2005, 'regular', 1, 2, 3, 2, 't')""")
    con.execute("INSERT INTO core.players VALUES (7, 'Seven', ['Seven'])")
    return con


def test_read_gamelog_layout(tmp_path):
    _write(tmp_path, [_row(7, fg3a=None)])
    df = pb.read_gamelog(tmp_path / "leaguegamelog_P_2005_regular.json")
    r = df.iloc[0]
    assert (r["game_id"], r["season_end_year"], r["season_type"], r["player_id"]) == ("0020400001", 2005, "regular", 7)
    assert r["pts"] == 10 and r["plus_minus"] == 7 and r["fg3a"] is pd.NA
    assert "fantasy_pts" not in df.columns and "player_name" not in df.columns


def test_load_all_counts_unknown_players(tmp_path):
    _write(tmp_path, [_row(7), _row(8)])
    con = _con_with_game()
    out = pb.load_all(con, raw_dir=tmp_path)
    assert out == {"files": 1, "rows": 2, "games": 1, "players_not_in_core_players": 1}
    assert con.execute("SELECT count(*) FROM reference.nba_player_box").fetchone()[0] == 2


def test_duplicate_key_fails(tmp_path):
    _write(tmp_path, [_row(7), _row(7)])
    with pytest.raises(pb.PlayerBoxError, match="share"):
        pb.load_all(_con_with_game(), raw_dir=tmp_path)


def test_unknown_game_fails(tmp_path):
    _write(tmp_path, [_row(7, game_id=20400999)])
    with pytest.raises(pb.PlayerBoxError, match="not in core.games"):
        pb.load_all(_con_with_game(), raw_dir=tmp_path)
