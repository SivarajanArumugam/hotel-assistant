import pytest
from unittest.mock import patch

from agent import session as session_module
from tools.rag_tool import search_hotel_knowledge
from tools.reservation_tools import create_reservation, view_reservation, cancel_reservation
from tools.session_tools import make_session_tools

SESSION_ID = "integration-session"


@pytest.fixture(autouse=True)
def reset_session():
    session_module._sessions.clear()
    yield
    session_module._sessions.clear()


def test_search_hotel_knowledge_valid(in_memory_db):
    with patch("tools.rag_tool.retrieve_context", return_value="The hotel has a rooftop pool."):
        result = search_hotel_knowledge.invoke("pool")
    assert "rooftop pool" in result


def test_search_hotel_knowledge_rag_unavailable(in_memory_db):
    with patch("tools.rag_tool.retrieve_context", return_value="[RAG unavailable: connection error]"):
        result = search_hotel_knowledge.invoke("pool")
    assert "currently unavailable" in result


def test_create_reservation_success(in_memory_db):
    result = create_reservation.invoke({
        "guest_name": "Test Guest",
        "guest_email": "test@example.com",
        "check_in": "2099-03-01",
        "check_out": "2099-03-05",
    })
    assert "Reservation confirmed" in result
    assert "Booking ID" in result


def test_create_reservation_value_error(in_memory_db):
    result = create_reservation.invoke({
        "guest_name": "Test Guest",
        "guest_email": "test@example.com",
        "check_in": "2099-03-05",
        "check_out": "2099-03-01",
    })
    assert "Check-out date must be after check-in date" in result
    assert isinstance(result, str)


def test_view_reservation_success(in_memory_db):
    created = create_reservation.invoke({
        "guest_name": "View Guest",
        "guest_email": "view@example.com",
        "check_in": "2099-04-01",
        "check_out": "2099-04-05",
    })
    booking_id = [line.split(": ")[1] for line in created.split("\n") if line.startswith("Booking ID:")][0]
    result = view_reservation.invoke({"booking_id": booking_id, "guest_email": "view@example.com"})
    assert "View Guest" in result
    assert booking_id in result


def test_view_reservation_not_found(in_memory_db):
    result = view_reservation.invoke({"booking_id": "fake-id", "guest_email": "nobody@example.com"})
    assert "No reservation found" in result


def test_cancel_reservation_success(in_memory_db):
    created = create_reservation.invoke({
        "guest_name": "Cancel Guest",
        "guest_email": "cancel@example.com",
        "check_in": "2099-05-01",
        "check_out": "2099-05-05",
    })
    booking_id = [line.split(": ")[1] for line in created.split("\n") if line.startswith("Booking ID:")][0]
    result = cancel_reservation.invoke({"booking_id": booking_id, "guest_email": "cancel@example.com"})
    assert "successfully cancelled" in result


def test_cancel_reservation_not_found(in_memory_db):
    result = cancel_reservation.invoke({"booking_id": "fake-id", "guest_email": "nobody@example.com"})
    assert "Unable to cancel" in result


def test_update_then_create(in_memory_db):
    tools = make_session_tools(SESSION_ID)
    update_tool = tools[1]

    update_tool.invoke({"field_name": "check_in", "new_value": "2099-06-10"})
    update_tool.invoke({"field_name": "check_out", "new_value": "2099-06-15"})

    draft = session_module.get_draft(SESSION_ID)
    assert draft["check_in"] == "2099-06-10"

    result = create_reservation.invoke({
        "guest_name": "Draft Guest",
        "guest_email": "draft@example.com",
        "check_in": draft["check_in"],
        "check_out": draft["check_out"],
    })
    assert "Reservation confirmed" in result
    assert "2099-06-10" in result
