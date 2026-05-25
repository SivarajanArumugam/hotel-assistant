import pytest
from agent import session as session_module
from agent.session import (
    get_draft,
    update_draft,
    clear_draft,
    format_draft_for_prompt,
    get_missing_fields,
)


@pytest.fixture(autouse=True)
def reset_sessions():
    session_module._sessions.clear()
    yield
    session_module._sessions.clear()


def test_get_draft_new_session():
    draft = get_draft("new-session")
    assert draft == {}


def test_update_draft_allowed_fields():
    update_draft("s1", guest_name="Alice", check_in="2099-08-01")
    draft = get_draft("s1")
    assert draft["guest_name"] == "Alice"
    assert draft["check_in"] == "2099-08-01"


def test_update_draft_ignores_unknown_fields():
    update_draft("s2", unknown_field="value", guest_name="Bob")
    draft = get_draft("s2")
    assert "unknown_field" not in draft
    assert draft["guest_name"] == "Bob"


def test_clear_draft():
    update_draft("s3", guest_name="Carol", guest_email="carol@example.com")
    clear_draft("s3")
    draft = get_draft("s3")
    assert draft == {}


def test_format_draft_no_raw_email():
    update_draft("s4", guest_email="secret@example.com", guest_name="Dave")
    output = format_draft_for_prompt("s4")
    assert "secret@example.com" not in output


def test_format_draft_shows_collected_for_email():
    update_draft("s5", guest_email="user@example.com")
    output = format_draft_for_prompt("s5")
    assert "[collected]" in output


def test_get_missing_fields_all_missing():
    missing = get_missing_fields("empty-session")
    assert "guest name" in missing
    assert "email address" in missing
    assert "check-in date" in missing
    assert "check-out date" in missing
    assert len(missing) == 4


def test_get_missing_fields_partial():
    update_draft("s6", guest_name="Eve", guest_email="eve@example.com")
    missing = get_missing_fields("s6")
    assert "guest name" not in missing
    assert "email address" not in missing
    assert "check-in date" in missing
    assert "check-out date" in missing
