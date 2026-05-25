import pytest
from db.operations import create_booking, get_booking, cancel_booking, _hash_email


def test_create_booking_success(in_memory_db, sample_booking_data):
    result = create_booking(**sample_booking_data)
    assert "booking_id" in result
    assert result["guest_name"] == sample_booking_data["guest_name"]
    assert result["check_in"] == sample_booking_data["check_in"]
    assert result["check_out"] == sample_booking_data["check_out"]
    assert result["status"] == "confirmed"


def test_create_booking_invalid_date_format(in_memory_db):
    with pytest.raises(ValueError, match="Invalid date format"):
        create_booking("Alice", "alice@example.com", "10-01-2099", "2099-01-15")


def test_create_booking_checkout_before_checkin(in_memory_db):
    with pytest.raises(ValueError, match="Check-out date must be after check-in date"):
        create_booking("Alice", "alice@example.com", "2099-01-15", "2099-01-10")


def test_create_booking_checkin_in_past(in_memory_db):
    with pytest.raises(ValueError, match="Check-in date cannot be in the past"):
        create_booking("Alice", "alice@example.com", "2000-01-01", "2000-01-05")


def test_get_booking_success(in_memory_db, sample_booking_data):
    created = create_booking(**sample_booking_data)
    result = get_booking(created["booking_id"], sample_booking_data["guest_email"])
    assert result is not None
    assert result["booking_id"] == created["booking_id"]
    assert result["guest_name"] == sample_booking_data["guest_name"]


def test_get_booking_wrong_email(in_memory_db, sample_booking_data):
    created = create_booking(**sample_booking_data)
    result = get_booking(created["booking_id"], "wrong@example.com")
    assert result is None


def test_get_booking_wrong_id(in_memory_db, sample_booking_data):
    create_booking(**sample_booking_data)
    result = get_booking("nonexistent-id", sample_booking_data["guest_email"])
    assert result is None


def test_cancel_booking_success(in_memory_db, sample_booking_data):
    created = create_booking(**sample_booking_data)
    success = cancel_booking(created["booking_id"], sample_booking_data["guest_email"])
    assert success is True
    result = get_booking(created["booking_id"], sample_booking_data["guest_email"])
    assert result["status"] == "cancelled"


def test_cancel_booking_wrong_email(in_memory_db, sample_booking_data):
    created = create_booking(**sample_booking_data)
    success = cancel_booking(created["booking_id"], "wrong@example.com")
    assert success is False


def test_cancel_booking_already_cancelled(in_memory_db, sample_booking_data):
    created = create_booking(**sample_booking_data)
    cancel_booking(created["booking_id"], sample_booking_data["guest_email"])
    success = cancel_booking(created["booking_id"], sample_booking_data["guest_email"])
    assert success is False


def test_raw_email_not_stored(in_memory_db, sample_booking_data):
    from db.models import Guest
    create_booking(**sample_booking_data)
    with in_memory_db() as session:
        guest = session.query(Guest).first()
        assert guest.email_hash != sample_booking_data["guest_email"]
        assert guest.email_hash == _hash_email(sample_booking_data["guest_email"])
