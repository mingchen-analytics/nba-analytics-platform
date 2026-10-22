"""Small hand-built raw inputs shaped like the real sources (no real data in the repo)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

HOME = ["1 Home One", "2 Home Two", "3 Home Three", "4 Home Four", "5 Home Five"]
AWAY = ["11 Away One", "12 Away Two", "13 Away Three", "14 Away Four", "15 Away Five"]
HOME_SUB = ["1 Home One", "2 Home Two", "3 Home Three", "4 Home Four", "6 Home Six"]


def _lu(players):
    return ", ".join(players)


def raw_game(game_id: str = "0020400001") -> pd.DataFrame:
    """One tiny 4-period game in the ramirobentes column layout.

    HOM (home) beats AWY 3-2. Includes a substitution (5 -> 6), a free throw trip,
    a team rebound, and one synthetic msg_type 99 row.
    """
    # (msg, act, period, clock, team, desc, p1, p2, hs, vs, shot_pts, home_lineup, number_event, event_num)
    H, A, S = _lu(HOME), _lu(AWAY), _lu(HOME_SUB)
    rows = [
        (12, 0, 1, "12:00", None, "Start of 1st Period", None, None, 0, 0, 0, H, 1, 0),
        (10, 0, 1, "12:00", "HOM", "Jump Ball", "1 Home One", "11 Away One", 0, 0, 0, H, 2, 1),
        (1, 1, 1, "11:40", "AWY", "Away One Jump Shot (2 PTS)", "11 Away One", None, 0, 2, 2, H, 3, 2),
        (2, 1, 1, "11:20", "HOM", "MISS Home Two Jump Shot", "2 Home Two", None, 0, 2, 0, H, 4, 3),
        (4, 0, 1, "11:18", "AWY", "Away Rebound", None, None, 0, 2, 0, H, 5, 4),
        (6, 2, 1, "11:00", "AWY", "Away Two S.FOUL", "12 Away Two", None, 0, 2, 0, H, 6, 5),
        (3, 11, 1, "11:00", "HOM", "Home Three Free Throw 1 of 2 (1 PTS)", "3 Home Three", None, 1, 2, 1, H, 7, 6),
        (8, 0, 1, "11:00", "HOM", "SUB: Home Six FOR Home Five", "5 Home Five", "6 Home Six", 1, 2, 0, S, 8, 7),
        (3, 12, 1, "11:00", "HOM", "Home Three Free Throw 2 of 2 (2 PTS)", "3 Home Three", None, 2, 2, 1, S, 9, 8),
        (13, 0, 1, "00:00", None, "End of 1st Period", None, None, 2, 2, 0, S, 10, 10),
        (99, 0, 1, "00:00", "HOM", "Last possession of quarter", None, None, 2, 2, 0, S, 10.5, 9999),
        (12, 0, 2, "12:00", None, "Start of 2nd Period", None, None, 2, 2, 0, S, 11, 11),
        (13, 0, 2, "00:00", None, "End of 2nd Period", None, None, 2, 2, 0, S, 12, 12),
        (12, 0, 3, "12:00", None, "Start of 3rd Period", None, None, 2, 2, 0, S, 13, 13),
        (13, 0, 3, "00:00", None, "End of 3rd Period", None, None, 2, 2, 0, S, 14, 14),
        (12, 0, 4, "12:00", None, "Start of 4th Period", None, None, 2, 2, 0, S, 15, 15),
        (3, 10, 4, "00:30", "HOM", "Home One Free Throw 1 of 1 (1 PTS)", "1 Home One", None, 3, 2, 1, S, 16, 16),
        (13, 0, 4, "00:00", None, "End of 4th Period", None, None, 3, 2, 0, S, 17, 17),
    ]
    df = pd.DataFrame(rows, columns=["msg_type", "act_type", "period", "clock", "team_abb", "description",
                                     "player1_name", "player2_name", "hs", "vs", "shot_pts", "lineup_home",
                                     "number_event", "event_num"])
    period = df["period"]
    mm = df["clock"].str.slice(0, 2).astype(int)
    ss = df["clock"].str.slice(3, 5).astype(int)
    df["secs_game"] = ((period - 1) * 720 + 720 - (mm * 60 + ss)).astype(float)
    df["lineup_away"] = A
    df["player3_name"] = None
    df["player_ft"] = np.where(df["msg_type"] == 3, df["player1_name"], None)
    df["season"] = 2005
    df["season_type"] = "regular"
    df["game_id"] = game_id
    df["game_date"] = pd.Timestamp("2004-11-02")
    df["team_home"] = "HOM"
    df["team_away"] = "AWY"
    for c in ["msg_type", "act_type", "period", "hs", "vs", "shot_pts", "number_event", "event_num"]:
        df[c] = df[c].astype(float)  # the real file stores these as DOUBLE
    for c in ["team_abb", "player1_name", "player2_name", "player3_name", "player_ft"]:
        df[c] = df[c].astype(object).where(df[c].notna(), None)
    return df


def shotdetail_for(raw: pd.DataFrame) -> pd.DataFrame:
    ids = {"HOM": (1610612701, "Home Team"), "AWY": (1610612702, "Away Team")}
    fga = raw[raw["msg_type"].isin([1, 2])]
    return pd.DataFrame({
        "GAME_ID": fga["game_id"].values,
        "GAME_EVENT_ID": fga["event_num"].astype(int).values,
        "PLAYER_ID": fga["player1_name"].str.split(" ").str[0].astype(int).values,
        "TEAM_ID": [ids[a][0] for a in fga["team_abb"]],
        "TEAM_NAME": [ids[a][1] for a in fga["team_abb"]],
        "SHOT_MADE_FLAG": (fga["msg_type"] == 1).astype(int).values,
        "SHOT_TYPE": "2PT Field Goal",
        "ACTION_TYPE": "Jump Shot",
        "SHOT_ZONE_BASIC": "Mid-Range",
        "SHOT_ZONE_AREA": "Center(C)",
        "SHOT_ZONE_RANGE": "16-24 ft.",
        "SHOT_DISTANCE": 18,
        "LOC_X": 10,
        "LOC_Y": 180,
    })


@pytest.fixture
def raw():
    return raw_game()


@pytest.fixture
def shotdetail(raw):
    return shotdetail_for(raw)
