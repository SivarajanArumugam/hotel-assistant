from langchain.tools import tool
from db.operations import get_booking, cancel_booking, modify_booking
from agent.session import is_lookup_gate_open, close_lookup_gate


@tool
def view_reservation(booking_reference: str) -> str:
    """
    Retrieve the details of an existing hotel reservation.
    booking_reference: a single string containing the booking ID and the guest's
    email address separated by a space, e.g. "8LvA8a71 siva@gmail.com".
    Always pass both values together as one string — do NOT use separate parameters.
    """
    parts = booking_reference.strip().split()
    if len(parts) < 2:
        return (
            "Please provide both your booking ID and email address separated by a space, "
            "e.g. '8LvA8a71 siva@gmail.com'."
        )
    booking_id = parts[0]
    guest_email = parts[-1]

    try:
        result = get_booking(booking_id, guest_email)
        if result is None:
            return (
                "No reservation found matching that booking ID and email address. "
                "Please check your details and try again."
            )
        return (
            f"Reservation Details:\n"
            f"Booking ID: {result['booking_id']}\n"
            f"Guest: {result['guest_name']}\n"
            f"Check-in: {result['check_in']}\n"
            f"Check-out: {result['check_out']}\n"
            f"Room type: {result['room_type'].capitalize()}\n"
            f"Status: {result['status'].capitalize()}"
        )
    except Exception as e:
        return f"An error occurred while retrieving the reservation: {e}"


@tool
def cancel_reservation(booking_reference: str) -> str:
    """
    Cancel an existing hotel reservation.
    booking_reference: a single string containing the booking ID and the guest's
    email address separated by a space, e.g. "8LvA8a71 siva@gmail.com".
    Always pass both values together as one string — do NOT use separate parameters.
    Only confirmed reservations can be cancelled.
    """
    parts = booking_reference.strip().split()
    if len(parts) < 2:
        return (
            "Please provide both your booking ID and email address separated by a space, "
            "e.g. '8LvA8a71 siva@gmail.com'."
        )
    booking_id = parts[0]
    guest_email = parts[-1]

    try:
        success = cancel_booking(booking_id, guest_email)
        if success:
            return f"Your reservation {booking_id} has been successfully cancelled."
        return (
            "Unable to cancel. No active reservation found matching that booking ID and email."
        )
    except Exception as e:
        return f"An error occurred while cancelling the reservation: {e}"


@tool
def modify_reservation(modification_reference: str) -> str:
    """
    Modify a confirmed reservation by cancelling it and creating a new one with updated fields.
    modification_reference: a single string with booking_id, email, then alternating field/value pairs.
    Allowed fields: room_type, check_in, check_out, guest_name.
    Example: "8LvA8a71 siva@gmail.com room_type deluxe"
    Example: "8LvA8a71 siva@gmail.com check_in 2026-06-05 check_out 2026-06-07"
    Always pass as one string — do NOT use separate parameters.
    """
    parts = modification_reference.strip().split()
    if len(parts) < 4 or len(parts) % 2 != 0:
        return (
            "Invalid format. Provide: booking_id email field1 value1 [field2 value2 ...]\n"
            "Example: '8LvA8a71 siva@gmail.com room_type deluxe'"
        )
    booking_id = parts[0]
    guest_email = parts[1]
    changes = dict(zip(parts[2::2], parts[3::2]))

    try:
        result = modify_booking(booking_id, guest_email, **changes)
        if result is None:
            return (
                "Could not modify booking. Check your Booking ID and email address, "
                "or the booking may already be cancelled."
            )
        if result.get("no_change"):
            b = result["booking"]
            return (
                "No changes were made — your booking details are already up to date.\n"
                f"Booking ID: {b['booking_id']}\n"
                f"Guest: {b['guest_name']}\n"
                f"Check-in: {b['check_in']}\n"
                f"Check-out: {b['check_out']}\n"
                f"Room type: {b['room_type'].capitalize()}\n"
                f"Status: {b['status'].capitalize()}"
            )
        return (
            f"Booking modified successfully.\n"
            f"New Booking ID: {result['booking_id']}\n"
            f"Guest: {result['guest_name']}\n"
            f"Check-in: {result['check_in']}\n"
            f"Check-out: {result['check_out']}\n"
            f"Room type: {result['room_type'].capitalize()}\n"
            f"Status: {result['status'].capitalize()}"
        )
    except Exception as e:
        return f"An error occurred while modifying the reservation: {e}"


def make_reservation_tools(session_id: str) -> list:
    """Returns session-aware view/cancel/modify tools that enforce the lookup gate."""

    @tool
    def view_reservation(booking_reference: str) -> str:
        """
        Retrieve the details of an existing hotel reservation.
        booking_reference: a single string containing the booking ID and the guest's
        email address separated by a space, e.g. "8LvA8a71 siva@gmail.com".
        Always pass both values together as one string — do NOT use separate parameters.
        You MUST call open_booking_lookup before calling this tool.
        """
        if not is_lookup_gate_open(session_id):
            return (
                "ACCESS DENIED: You must call open_booking_lookup first, then ask the user "
                "to provide their Booking ID and email address fresh before calling this tool."
            )
        parts = booking_reference.strip().split()
        if len(parts) < 2:
            return (
                "Please provide both your booking ID and email address separated by a space, "
                "e.g. '8LvA8a71 siva@gmail.com'."
            )
        booking_id = parts[0]
        guest_email = parts[-1]
        try:
            result = get_booking(booking_id, guest_email)
            if result is None:
                return (
                    "Those details did not match any active reservation. "
                    "Please double-check your Booking ID and email address and try again."
                )
            close_lookup_gate(session_id)
            return (
                f"Reservation Details:\n"
                f"Booking ID: {result['booking_id']}\n"
                f"Guest: {result['guest_name']}\n"
                f"Check-in: {result['check_in']}\n"
                f"Check-out: {result['check_out']}\n"
                f"Room type: {result['room_type'].capitalize()}\n"
                f"Status: {result['status'].capitalize()}"
            )
        except Exception as e:
            return f"An error occurred while retrieving the reservation: {e}"

    @tool
    def cancel_reservation(booking_reference: str) -> str:
        """
        Cancel an existing hotel reservation.
        booking_reference: a single string containing the booking ID and the guest's
        email address separated by a space, e.g. "8LvA8a71 siva@gmail.com".
        Always pass both values together as one string — do NOT use separate parameters.
        Only confirmed reservations can be cancelled.
        You MUST call open_booking_lookup before calling this tool.
        """
        if not is_lookup_gate_open(session_id):
            return (
                "ACCESS DENIED: You must call open_booking_lookup first, then ask the user "
                "to provide their Booking ID and email address fresh before calling this tool."
            )
        parts = booking_reference.strip().split()
        if len(parts) < 2:
            return (
                "Please provide both your booking ID and email address separated by a space, "
                "e.g. '8LvA8a71 siva@gmail.com'."
            )
        booking_id = parts[0]
        guest_email = parts[-1]
        try:
            success = cancel_booking(booking_id, guest_email)
            if not success:
                return (
                    "Those details did not match any active reservation. "
                    "Please double-check your Booking ID and email address and try again."
                )
            close_lookup_gate(session_id)
            return f"Your reservation {booking_id} has been successfully cancelled."
        except Exception as e:
            return f"An error occurred while cancelling the reservation: {e}"

    @tool
    def modify_reservation(modification_reference: str) -> str:
        """
        Modify a confirmed reservation by cancelling it and creating a new one with updated fields.
        modification_reference: a single string with booking_id, email, then alternating field/value pairs.
        Allowed fields: room_type, check_in, check_out, guest_name.
        Example: "8LvA8a71 siva@gmail.com room_type deluxe"
        Example: "8LvA8a71 siva@gmail.com check_in 2026-06-05 check_out 2026-06-07"
        Always pass as one string — do NOT use separate parameters.
        You MUST call open_booking_lookup before calling this tool.
        """
        if not is_lookup_gate_open(session_id):
            return (
                "ACCESS DENIED: You must call open_booking_lookup first, then ask the user "
                "to provide their Booking ID and email address fresh before calling this tool."
            )
        parts = modification_reference.strip().split()
        if len(parts) < 4 or len(parts) % 2 != 0:
            return (
                "Invalid format. Provide: booking_id email field1 value1 [field2 value2 ...]\n"
                "Example: '8LvA8a71 siva@gmail.com room_type deluxe'"
            )
        booking_id = parts[0]
        guest_email = parts[1]
        changes = dict(zip(parts[2::2], parts[3::2]))
        try:
            result = modify_booking(booking_id, guest_email, **changes)
            if result is None:
                return (
                    "Those details did not match any active reservation. "
                    "Please double-check your Booking ID and email address and try again."
                )
            close_lookup_gate(session_id)
            if result.get("no_change"):
                b = result["booking"]
                return (
                    "No changes were made — your booking details are already up to date.\n"
                    f"Booking ID: {b['booking_id']}\n"
                    f"Guest: {b['guest_name']}\n"
                    f"Check-in: {b['check_in']}\n"
                    f"Check-out: {b['check_out']}\n"
                    f"Room type: {b['room_type'].capitalize()}\n"
                    f"Status: {b['status'].capitalize()}"
                )
            return (
                f"Booking modified successfully.\n"
                f"New Booking ID: {result['booking_id']}\n"
                f"Guest: {result['guest_name']}\n"
                f"Check-in: {result['check_in']}\n"
                f"Check-out: {result['check_out']}\n"
                f"Room type: {result['room_type'].capitalize()}\n"
                f"Status: {result['status'].capitalize()}"
            )
        except Exception as e:
            return f"An error occurred while modifying the reservation: {e}"

    return [view_reservation, cancel_reservation, modify_reservation]
