import hashlib
import secrets
import datetime
import logging
from typing import Optional
from db.models import SessionLocal, Guest, Booking
from core.crypto import encrypt, decrypt

logger = logging.getLogger(__name__)


def _hash_email(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


def create_booking(guest_name: str, guest_email: str, check_in: str, check_out: str, room_type: str = "standard") -> dict:
    try:
        ci = datetime.date.fromisoformat(check_in)
        co = datetime.date.fromisoformat(check_out)
    except ValueError:
        raise ValueError("Invalid date format. Use YYYY-MM-DD.")

    if co <= ci:
        raise ValueError("Check-out date must be after check-in date.")

    if ci < datetime.date.today():
        raise ValueError("Check-in date cannot be in the past.")

    email_hash = _hash_email(guest_email)

    with SessionLocal() as session:
        guest = session.query(Guest).filter_by(email_hash=email_hash).first()
        if not guest:
            guest = Guest(name=encrypt(guest_name), email_hash=email_hash)
            session.add(guest)
            session.flush()

        room_type = room_type.lower().strip()
        if room_type not in ("standard", "deluxe"):
            raise ValueError("Invalid room type. Choose 'standard' or 'deluxe'.")

        booking = Booking(
            id=secrets.token_urlsafe(6),
            guest_id=guest.id,
            check_in=check_in,
            check_out=check_out,
            room_type=room_type,
            status="confirmed",
        )
        session.add(booking)
        session.commit()
        session.refresh(booking)
        session.refresh(guest)

        logger.info("Booking created: booking_id=%s room_type=%s check_in=%s check_out=%s",
                    booking.id, booking.room_type, check_in, check_out)
        return {
            "booking_id": booking.id,
            "guest_name": guest_name,
            "check_in": booking.check_in,
            "check_out": booking.check_out,
            "room_type": booking.room_type,
            "status": booking.status,
        }


def get_booking(booking_id: str, guest_email: str) -> Optional[dict]:
    email_hash = _hash_email(guest_email)

    with SessionLocal() as session:
        booking = (
            session.query(Booking)
            .join(Guest, Booking.guest_id == Guest.id)
            .filter(Booking.id == booking_id, Guest.email_hash == email_hash)
            .first()
        )
        if not booking:
            logger.info("Booking lookup failed: booking_id=%s", booking_id)
            return None

        guest = session.query(Guest).filter_by(id=booking.guest_id).first()
        try:
            guest_name = decrypt(guest.name)
        except Exception:
            guest_name = guest.name
        return {
            "booking_id": booking.id,
            "guest_name": guest_name,
            "check_in": booking.check_in,
            "check_out": booking.check_out,
            "room_type": booking.room_type,
            "status": booking.status,
        }


def purge_old_bookings(days: int = 365) -> int:
    """Anonymise bookings whose check-out is older than `days` days.

    Sets the guest name to '[anonymised]' rather than deleting records,
    preserving the booking row for audit purposes.
    Returns the number of records anonymised.
    """
    cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    with SessionLocal() as session:
        old_bookings = session.query(Booking).filter(Booking.check_out < cutoff).all()
        guest_ids = {b.guest_id for b in old_bookings}
        count = 0
        for guest_id in guest_ids:
            guest = session.query(Guest).filter_by(id=guest_id).first()
            if guest and guest.name != "[anonymised]":
                guest.name = "[anonymised]"
                count += 1
        session.commit()
    logger.info("Purged PII for %d guests with check-out before %s", count, cutoff)
    return count


def modify_booking(booking_id: str, guest_email: str, **changes) -> Optional[dict]:
    """Cancel old booking and create a new one with updated fields. Atomic."""
    old = get_booking(booking_id, guest_email)
    if old is None:
        return None
    allowed = {"guest_name", "guest_email", "check_in", "check_out", "room_type"}
    merged = {
        "guest_name": old["guest_name"],
        "guest_email": guest_email,
        "check_in": old["check_in"],
        "check_out": old["check_out"],
        "room_type": old["room_type"],
    }
    merged.update({k: v for k, v in changes.items() if k in allowed})
    comparable_fields = {"guest_name", "check_in", "check_out", "room_type"}
    if all(merged.get(f) == old.get(f) for f in comparable_fields):
        return {"no_change": True, "booking": old}
    cancelled = cancel_booking(booking_id, guest_email)
    if not cancelled:
        return None
    return create_booking(**merged)


def cancel_booking(booking_id: str, guest_email: str) -> bool:
    email_hash = _hash_email(guest_email)

    with SessionLocal() as session:
        booking = (
            session.query(Booking)
            .join(Guest, Booking.guest_id == Guest.id)
            .filter(
                Booking.id == booking_id,
                Guest.email_hash == email_hash,
                Booking.status == "confirmed",
            )
            .first()
        )
        if not booking:
            return False

        booking.status = "cancelled"
        session.commit()
        logger.info("Booking cancelled: booking_id=%s", booking_id)
        return True
