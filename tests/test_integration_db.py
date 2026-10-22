"""Checks against the real database, opened read-only. Skipped when it has not been built."""

import duckdb
import pytest

from nba_platform.db import DB_PATH

pytestmark = pytest.mark.skipif(not DB_PATH.exists(), reason="database not built (see nba_platform.db.DB_PATH)")


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(str(DB_PATH), read_only=True)
    yield c
    c.close()


def test_2004_05_regular_loaded(con):
    games, events = con.execute("""
        SELECT count(DISTINCT g.game_id), count(*) FROM core.games g JOIN core.events e USING (game_id)
        WHERE g.season_end_year = 2005 AND g.season_type = 'regular'""").fetchone()
    assert games == 1230
    assert events == 559_067


def test_2004_05_regular_validation_has_no_failures(con):
    rows = con.execute("""
        SELECT check_id, status FROM validation.results
        WHERE season_end_year = 2005 AND season_type = 'regular'""").fetchall()
    status = dict(rows)
    for cid in (1, 2, 3, 4, 6, 9, 102, 104, 105, 106):
        assert status.get(cid) == "pass", (cid, status.get(cid))
    # check 5 runs against the cached box scores; 2004-05 box minutes are "balanced", so it
    # reports a warning (docs/validation/minutes_vs_box.md) — it must have run, not skipped
    level5 = con.execute("""SELECT level, status FROM validation.results WHERE check_id = 5
                            AND season_end_year = 2005 AND season_type = 'regular'""").fetchone()
    assert level5 is not None and level5[0] == "warning" and level5[1] in ("pass", "fail")


def test_known_game_0020400027(con):
    row = con.execute("""
        SELECT h.abbreviation, a.abbreviation, home_score, away_score
        FROM core.games g JOIN core.teams h ON h.team_id = g.home_team_id
        JOIN core.teams a ON a.team_id = g.away_team_id WHERE game_id = '0020400027'""").fetchone()
    assert row == ("LAL", "SAS", 96, 105)


def test_possession_ids_are_all_or_nothing_per_season_and_match_possessions(con):
    """build_core --step possessions fills a whole season at once (2026-10-21: 2004-05 regular season)."""
    rows = con.execute("""SELECT g.season_end_year, g.season_type, count(*) FILTER (e.possession_id IS NOT NULL) AS with_p,
                                 count(*) FILTER (e.possession_id IS NULL AND e.event_type = 'free_throw'
                                                  AND (e.is_technical_ft OR e.is_between_possessions_ft)) AS ft_outside,
                                 count(*) AS n
                          FROM core.events e JOIN core.games g USING (game_id) GROUP BY ALL""").fetchall()
    for _, _, with_p, ft_outside, n in rows:
        assert with_p == 0 or with_p + ft_outside == n
    orphans = con.execute("""SELECT count(*) FROM core.events e LEFT JOIN core.possessions p USING (game_id, possession_id)
                             WHERE e.possession_id IS NOT NULL AND p.possession_id IS NULL""").fetchone()[0]
    assert orphans == 0


def test_stint_ids_are_all_or_nothing_per_season_and_match_stints(con):
    """build_core fills a whole season at once (2026-10-21: 2004-05 regular season)."""
    rows = con.execute("""SELECT g.season_end_year, g.season_type, count(*) AS n, count(e.stint_id) AS with_stint
                          FROM core.events e JOIN core.games g USING (game_id) GROUP BY ALL""").fetchall()
    assert all(w in (0, n) for _, _, n, w in rows)
    orphans = con.execute("""SELECT count(*) FROM core.events e LEFT JOIN core.stints s USING (game_id, stint_id)
                             WHERE e.stint_id IS NOT NULL AND s.stint_id IS NULL""").fetchone()[0]
    assert orphans == 0


def test_2004_05_shots(con):
    n, with_xy = con.execute("""
        SELECT count(*), count(loc_x) FROM core.shots s JOIN core.games g USING (game_id)
        WHERE g.season_end_year = 2005 AND g.season_type = 'regular'""").fetchone()
    assert n == 197_626 and with_xy == n
    assert con.execute("SELECT count(*) FROM core.shots WHERE game_id = '0020400027'").fetchone()[0] == 158


def test_hard_failed_seasons_have_no_partial_data(con):
    rows = con.execute("""
        SELECT r.season_end_year, r.season_type, count(g.game_id)
        FROM (SELECT DISTINCT season_end_year, season_type FROM validation.results
              WHERE level = 'hard' AND status = 'fail' AND check_id NOT IN (107, 108)) r
        LEFT JOIN core.games g USING (season_end_year, season_type)
        GROUP BY ALL""").fetchall()
    assert all(n == 0 for _, _, n in rows), rows


def test_loaded_regular_seasons_have_expected_game_counts(con):
    from nba_platform.validate.checks import expected_regular_season_games
    rows = con.execute("""SELECT season_end_year, count(*) FROM core.games
                          WHERE season_type = 'regular' GROUP BY 1""").fetchall()
    for y, n in rows:
        assert n == expected_regular_season_games(y), (y, n)


def test_shot_quality_flags_never_drop_shots(con):
    flags = dict(con.execute("SELECT flag, count(*) FROM core.shot_quality_flags GROUP BY 1").fetchall())
    assert set(flags) <= {"rim_location_imprecise", "rim_location_suspect", "early_season_location_suspect"}
    assert flags.get("rim_location_imprecise", 0) > 0
    # every flagged shot exists; every early-season shot is flagged
    orphan = con.execute("""SELECT count(*) FROM core.shot_quality_flags f
                            ANTI JOIN core.shots s USING (game_id, source_event_num)""").fetchone()[0]
    early_unflagged = con.execute("""
        SELECT count(*) FROM core.shots s JOIN core.games g USING (game_id)
        WHERE g.season_end_year <= 2000 AND NOT EXISTS (
            SELECT 1 FROM core.shot_quality_flags f WHERE f.game_id = s.game_id
            AND f.source_event_num = s.source_event_num AND f.flag = 'early_season_location_suspect')""").fetchone()[0]
    assert orphan == 0 and early_unflagged == 0
    total = con.execute("SELECT count(*) FROM core.shots").fetchone()[0]
    fga = con.execute("SELECT count(*) FROM core.events WHERE event_type IN ('shot_made', 'shot_missed')").fetchone()[0]
    assert abs(total - fga) / fga < 0.001  # flags only: shots still match FGA events


def test_reference_pbpstats_loaded_and_separate(con):
    n, seasons, poss_2005 = con.execute("""
        SELECT count(*), count(DISTINCT (season_end_year, season_type)),
               count(*) FILTER (season_end_year = 2005 AND season_type = 'regular')
        FROM reference.pbpstats_possessions""").fetchone()
    assert seasons == 50 and poss_2005 == 226_220
    # reference data never feeds our tables: our possessions are built from our events only
    assert con.execute("SELECT count(*) FROM core.possessions").fetchone()[0] != poss_2005
