"""Headless run of the Streamlit data-health dashboard (read-only database)."""

from pathlib import Path

import pytest

from nba_platform.db import DB_PATH

APP = Path(__file__).resolve().parents[1] / "app" / "data_health.py"
pytestmark = pytest.mark.skipif(not DB_PATH.exists(), reason="database not built")


def test_dashboard_renders_without_errors():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(APP), default_timeout=120).run()
    assert not at.exception, at.exception
    assert at.title[0].value == "Data health"
    assert len(at.dataframe) >= 2  # season table + season detail
    at.radio[0].set_value("playoffs").run()
    assert not at.exception


def test_dashboard_opens_database_read_only():
    text = APP.read_text(encoding="utf-8")
    assert "read_only=True" in text and "INSERT" not in text.upper() and "UPDATE " not in text.upper()


REF_PAGE = APP.parent / "pages" / "1_Reference_data.py"


def test_reference_page_renders_without_errors():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(REF_PAGE), default_timeout=120).run()
    assert not at.exception, at.exception
    assert at.title[0].value == "Reference data"
    assert len(at.dataframe) >= 2
    at.radio[0].set_value("playoffs").run()
    assert not at.exception


def test_reference_page_is_read_only():
    text = REF_PAGE.read_text(encoding="utf-8").upper()
    assert "READ_ONLY=TRUE" in text
    assert not any(sql in text for sql in ("INSERT INTO", "UPDATE ", "DELETE FROM", "CREATE ", "DROP "))


GAMES_PAGE = APP.parent / "pages" / "2_Games.py"
PLAYERS_PAGE = APP.parent / "pages" / "3_Players.py"


def test_games_page_renders_a_box_score():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(GAMES_PAGE), default_timeout=120).run()
    assert not at.exception, at.exception
    assert at.title[0].value == "Games"
    assert len(at.dataframe) == 2  # away and home box score
    at.radio[0].set_value("playoffs").run()
    assert not at.exception, at.exception


def test_players_page_renders_leaderboard_and_game_log():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(PLAYERS_PAGE), default_timeout=120).run()
    assert not at.exception, at.exception
    assert at.title[0].value == "Players"
    assert len(at.dataframe) == 3  # leaderboard, seasons, game log
    at.radio[0].set_value("playoffs").run()
    assert not at.exception, at.exception


def test_layer1_pages_are_read_only_and_use_marts():
    for page in (GAMES_PAGE, PLAYERS_PAGE):
        text = page.read_text(encoding="utf-8").upper()
        assert "READ_ONLY=TRUE" in text
        assert not any(sql in text for sql in ("INSERT INTO", "UPDATE ", "DELETE FROM", "CREATE ", "DROP "))


TEAMS_PAGE = APP.parent / "pages" / "4_Teams.py"
SHOOTING_PAGE = APP.parent / "pages" / "5_Shooting.py"


def test_teams_page_renders_table_roster_and_results():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(TEAMS_PAGE), default_timeout=120).run()
    assert not at.exception, at.exception
    assert at.title[0].value == "Teams"
    assert len(at.dataframe) == 4  # season table, roster, shot mix, results
    at.radio[0].set_value("playoffs").run()
    assert not at.exception, at.exception


def test_shooting_page_renders_zones_and_chart():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(SHOOTING_PAGE), default_timeout=120).run()
    assert not at.exception, at.exception
    assert at.title[0].value == "Shooting"
    assert len(at.dataframe) == 1 and len(at.dataframe[0].value) >= 3
    at.radio[0].set_value("playoffs").run()
    assert not at.exception, at.exception


def test_team_and_shooting_pages_are_read_only():
    for page in (TEAMS_PAGE, SHOOTING_PAGE):
        text = page.read_text(encoding="utf-8").upper()
        assert "READ_ONLY=TRUE" in text
        assert not any(sql in text for sql in ("INSERT INTO", "UPDATE ", "DELETE FROM", "CREATE ", "DROP "))


TRACKING_PAGE = APP.parent / "pages" / "6_Tracking.py"


def test_tracking_page_renders_every_category_and_scale():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(TRACKING_PAGE), default_timeout=120).run()
    assert not at.exception, at.exception
    assert at.title[0].value == "Tracking"
    assert len(at.dataframe) == 2 and len(at.dataframe[0].value) > 50  # leaderboard, player history
    for group in at.selectbox[1].options:  # every category
        at.selectbox[1].select(group).run()
        assert not at.exception, (group, at.exception)
    for scale in ("Per game", "Per 36"):
        at.radio[1].set_value(scale).run()
        assert not at.exception, (scale, at.exception)
    at.radio[0].set_value("playoffs").run()
    assert not at.exception, at.exception


def test_tracking_page_is_read_only():
    text = TRACKING_PAGE.read_text(encoding="utf-8").upper()
    assert "READ_ONLY=TRUE" in text
    assert not any(sql in text for sql in ("INSERT INTO", "UPDATE ", "DELETE FROM", "CREATE ", "DROP "))
