"""Repair of the shared check id 111."""

import json
from datetime import datetime

from nba_platform import db
from nba_platform.validate import fix_check_ids as fx

POSSESSION = "possession points + FTs outside possessions = final score"


def test_possession_rows_move_to_112_and_known_gaps_are_rewritten():
    c = db.connect(":memory:")
    c.execute("INSERT INTO core.known_gaps (game_id, season_end_year, season_type, issue, reason) VALUES ('G9', 2025, 'playoffs', 'pbp_missing', 'test')")
    now = datetime.now()
    for season_type in ("regular", "playoffs"):
        c.execute("INSERT INTO validation.results VALUES (?, 2025, ?, 111, ?, 'hard', 'pass', 10, 0, '{}')", [now, season_type, POSSESSION])
    out = fx.fix(c)
    assert out == {"possession_rows_moved_to_112": 2, "known_gap_rows_written": 2, "seasons": 2}
    rows = c.execute("SELECT season_type, check_id, status FROM validation.results ORDER BY season_type, check_id").fetchall()
    assert rows == [("playoffs", 111, "known"), ("playoffs", 112, "pass"), ("regular", 111, "pass"), ("regular", 112, "pass")]
    detail = c.execute("SELECT detail FROM validation.results WHERE season_type = 'playoffs' AND check_id = 111").fetchone()[0]
    assert json.loads(detail)["gaps"] == {"G9": "pbp_missing"}
    assert fx.fix(c) == {"possession_rows_moved_to_112": 0, "known_gap_rows_written": 0, "seasons": 2}   # repeating changes nothing
