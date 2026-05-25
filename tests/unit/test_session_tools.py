import datetime
import pytest

from agent import session as session_module
from tools.session_tools import make_session_tools

SESSION_ID = "test-session"


@pytest.fixture(autouse=True)
def reset_session():
    session_module._sessions.clear()
    yield
    session_module._sessions.clear()


@pytest.fixture
def tools():
    return make_session_tools(SESSION_ID)


@pytest.fixture
def parse_date(tools):
    return tools[0]


@pytest.fixture
def update_draft_tool(tools):
    return tools[1]


def _invoke(tool, input_str):
    return tool.invoke(input_str)


def test_next_week(parse_date):
    result = _invoke(parse_date, "next week")
    today = datetime.date.today()
    days_ahead = (0 - today.weekday()) % 7 or 7
    monday = today + datetime.timedelta(days=days_ahead)
    sunday = monday + datetime.timedelta(days=6)
    assert monday.strftime("%Y-%m-%d") in result
    assert sunday.strftime("%Y-%m-%d") in result


def test_next_week_fully(parse_date):
    result = _invoke(parse_date, "next week fully")
    today = datetime.date.today()
    days_ahead = (0 - today.weekday()) % 7 or 7
    monday = today + datetime.timedelta(days=days_ahead)
    sunday = monday + datetime.timedelta(days=6)
    assert monday.strftime("%Y-%m-%d") in result
    assert sunday.strftime("%Y-%m-%d") in result


def test_this_weekend(parse_date):
    result = _invoke(parse_date, "this weekend")
    today = datetime.date.today()
    days_ahead = (5 - today.weekday()) % 7 or 7
    saturday = today + datetime.timedelta(days=days_ahead)
    sunday = saturday + datetime.timedelta(days=1)
    assert saturday.strftime("%Y-%m-%d") in result
    assert sunday.strftime("%Y-%m-%d") in result


def test_tomorrow(parse_date):
    result = _invoke(parse_date, "tomorrow")
    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    assert tomorrow in result
    assert "not determined" in result


def test_july_21_to_july_23(parse_date):
    result = _invoke(parse_date, "July 21 to July 23")
    assert "07-21" in result or "-07-21" in result or "21" in result
    assert "07-23" in result or "-07-23" in result or "23" in result


def test_for_3_nights_from_friday(parse_date):
    result = _invoke(parse_date, "for 3 nights from Friday")
    today = datetime.date.today()
    days = (4 - today.weekday()) % 7 or 7
    friday = today + datetime.timedelta(days=days)
    checkout = friday + datetime.timedelta(days=3)
    assert friday.strftime("%Y-%m-%d") in result
    assert checkout.strftime("%Y-%m-%d") in result


def test_in_5_days(parse_date):
    result = _invoke(parse_date, "in 5 days")
    expected = (datetime.date.today() + datetime.timedelta(days=5)).strftime("%Y-%m-%d")
    assert expected in result


def test_next_7_days(parse_date):
    result = _invoke(parse_date, "next 7 days")
    today = datetime.date.today()
    checkout = today + datetime.timedelta(days=7)
    assert today.strftime("%Y-%m-%d") in result
    assert checkout.strftime("%Y-%m-%d") in result


def test_unparseable_input(parse_date):
    result = _invoke(parse_date, "xyzzy")
    assert "could not interpret" in result.lower() or "I could not interpret" in result


def test_update_booking_draft_check_in(update_draft_tool):
    result = _invoke(update_draft_tool, {"field_name": "check_in", "new_value": "2099-05-01"})
    assert "check_in" in result
    assert "Updated" in result


def test_update_booking_draft_guest_name(update_draft_tool):
    result = _invoke(update_draft_tool, {"field_name": "guest_name", "new_value": "Frank"})
    assert "Frank" in result
    assert "Updated" in result


def test_update_booking_draft_invalid_field(update_draft_tool):
    result = _invoke(update_draft_tool, {"field_name": "room_type", "new_value": "suite"})
    assert "not a valid booking field" in result


def test_update_booking_draft_email_not_in_return(update_draft_tool):
    result = _invoke(update_draft_tool, {"field_name": "guest_email", "new_value": "secret@example.com"})
    assert "secret@example.com" not in result
