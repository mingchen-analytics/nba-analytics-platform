import pandas as pd

from nba_platform.reference import pbpstats as ps


def test_pbpstats_possessions_group_event_rows():
    rows = []
    base = {"GAMEID": "20400001", "PERIOD": 1, "STARTSCOREDIFFERENTIAL": 0, "FG2A": 1, "FG2M": 1, "FG3A": 0,
            "FG3M": 0, "OFFENSIVEREBOUNDS": 0, "TURNOVERS": 0, "SHOOTINGFOULSDRAWN": 0,
            "NONSHOOTINGFOULSTHATRESULTEDINFTS": 0}
    rows.append({**base, "OPPONENT": "HOU", "STARTTIME": "12:00", "ENDTIME": "11:45", "STARTTYPE": "Off Dead Ball",
                 "EVENTS": "a\nb\n"})
    rows.append({**rows[0]})  # second event row of the same possession
    rows.append({**base, "OPPONENT": "DET", "STARTTIME": "11:45", "ENDTIME": "11:20", "STARTTYPE": "Off At Rim Make",
                 "EVENTS": None})  # possession with no events must still count
    p = ps.possessions(pd.DataFrame(rows), 2005, "regular")
    assert len(p) == 2
    assert p["game_id"].tolist() == ["0020400001", "0020400001"]
    assert p["possession_seq"].tolist() == [1, 2] and p["n_event_rows"].tolist() == [2, 1]
