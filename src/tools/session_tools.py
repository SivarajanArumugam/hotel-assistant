import datetime
from typing import Optional, Tuple

from langchain.tools import tool
from langchain_groq import ChatGroq

from core.config import settings
from agent.session import (
    get_draft, get_draft_with_plaintext_email, clear_draft, update_draft, format_draft_for_prompt,
    open_lookup_gate, set_summary_shown, is_summary_shown, clear_summary_shown,
)
from db.operations import create_booking

_DATE_PARSE_PROMPT = """Today is {today} ({weekday}).
The user wants to book a hotel and said: "{expression}"

Extract the check-in and check-out dates. Reply with ONLY this exact format — nothing else:
check_in=YYYY-MM-DD
check_out=YYYY-MM-DD

If only one date is mentioned, use UNKNOWN for the other.
If the expression is not a date at all, reply: ERROR"""


def _llm_parse_dates(expression: str) -> Tuple[Optional[datetime.date], Optional[datetime.date]]:
    today = datetime.date.today()
    prompt = _DATE_PARSE_PROMPT.format(
        today=today.strftime("%Y-%m-%d"),
        weekday=today.strftime("%A"),
        expression=expression,
    )
    llm = ChatGroq(model=settings.llm_model, api_key=settings.groq_api_key, temperature=0)
    response = llm.invoke(prompt).content.strip()

    if response.startswith("ERROR"):
        return None, None

    check_in = check_out = None
    for line in response.splitlines():
        if line.startswith("check_in="):
            val = line.split("=", 1)[1].strip()
            if val != "UNKNOWN":
                try:
                    check_in = datetime.date.fromisoformat(val)
                except ValueError:
                    pass
        elif line.startswith("check_out="):
            val = line.split("=", 1)[1].strip()
            if val != "UNKNOWN":
                try:
                    check_out = datetime.date.fromisoformat(val)
                except ValueError:
                    pass
    return check_in, check_out


def make_session_tools(session_id: str) -> list:
    """Returns session-aware tools for the agent."""

    # Fix 3: get_today tool — agent must use this for any date context
    @tool
    def get_today(placeholder: str) -> str:
        """
        Return today's date and day name. Call this tool whenever you need to know
        today's date — for example when the user asks what day it is, or before
        interpreting any date expression. Never rely on training data for the current date.
        placeholder: pass any string, e.g. "today".
        """
        today = datetime.date.today()
        return f"Today is {today.strftime('%Y-%m-%d')} ({today.strftime('%A')})."

    # Option 3: start_new_booking — entry point for all new booking requests
    @tool
    def start_new_booking(placeholder: str) -> str:
        """
        Call this tool FIRST when the user wants to make a NEW hotel reservation.
        Triggers: "book a room", "I want to stay", "reserve a room", "make a booking",
        "I need a room", "book for [dates]", or any intent to create a new reservation.
        NEVER call this for viewing, cancelling, or modifying an existing booking.
        After calling this tool, begin collecting: guest name, email, check-in date,
        check-out date, and room type — one question at a time.
        placeholder: pass any string, e.g. "start".
        """
        return (
            "NEW BOOKING STARTED. Now ask the user for their details one at a time: "
            "start with their full name. Do NOT ask for a Booking ID — the user does not have one yet."
        )

    # Option 1+2: renamed to lookup_existing_reservation — only for view/cancel/modify
    @tool
    def lookup_existing_reservation(placeholder: str) -> str:
        """
        ONLY for existing reservations. Call this when the user wants to VIEW, CANCEL,
        or MODIFY a reservation they already have.
        Triggers: "show my booking", "view my reservation", "cancel my booking",
        "modify my reservation", "change my booking details", "what is my booking".
        NEVER call this when the user wants to make a NEW booking or reserve a room.
        After calling this tool, ask: "Please provide your Booking ID and email address."
        Do NOT call view_reservation, cancel_reservation, or modify_reservation until
        the user replies with both values in their next message.
        placeholder: pass any string, e.g. "lookup".
        """
        open_lookup_gate(session_id)
        return (
            "LOOKUP GATE OPENED. Now ask the user exactly: "
            "'Please provide your Booking ID and email address.' "
            "Stop here. Do NOT call any reservation lookup tool until the user replies with both."
        )

    # Fix 2: show_booking_summary tool — must be called before create_reservation
    @tool
    def show_booking_summary(placeholder: str) -> str:
        """
        Present the complete booking summary to the user and request their confirmation.
        Call this tool ONLY when all five booking fields are collected and you are ready
        to ask the user to confirm. After this tool returns, present the summary to the
        user and STOP — do NOT call create_reservation in the same response.
        Only after the user replies with an explicit confirmation (yes/confirm/go ahead)
        in their NEXT message should you call create_reservation.
        placeholder: pass any string, e.g. "show".
        """
        draft = get_draft(session_id)
        required = ["guest_name", "guest_email", "check_in", "check_out", "room_type"]
        missing = [f for f in required if not draft.get(f)]
        if missing:
            return f"Cannot show summary — missing fields: {', '.join(missing)}. Collect them first."
        try:
            ci = datetime.date.fromisoformat(draft["check_in"])
            co = datetime.date.fromisoformat(draft["check_out"])
            nights = (co - ci).days
        except Exception:
            nights = "?"
        set_summary_shown(session_id)
        return (
            f"Please confirm your booking details:\n"
            f"- Name: {draft['guest_name']}\n"
            f"- Check-in: {draft['check_in']}\n"
            f"- Check-out: {draft['check_out']}\n"
            f"- Nights: {nights}\n"
            f"- Room type: {draft['room_type'].capitalize()}\n\n"
            f"Shall I confirm this booking? You can also change any detail before confirming."
        )

    @tool
    def parse_date_expression(expression: str) -> str:
        """
        Parse a natural language date or date range expression into concrete YYYY-MM-DD dates.
        Call this tool whenever the user provides dates in any format other than YYYY-MM-DD.
        Examples: "next monday", "coming weekend", "next monday to tuesday", "tomorrow",
          "in 3 days", "for 5 nights from Friday", "August 10", "next week", "3 nights from Friday".
        Returns the interpreted check_in and check_out in YYYY-MM-DD format,
        plus a human-readable confirmation string for the user to verify.
        Never call create_reservation or update_booking_draft without first
        confirming the parsed dates with the user.
        """
        check_in, check_out = _llm_parse_dates(expression)

        if check_in is None and check_out is None:
            return (
                f'I could not interpret "{expression}" as a date. '
                f'Please provide dates like "2026-06-01" or "Monday June 1 to Wednesday June 3".'
            )

        today = datetime.date.today()
        if check_in and check_in < today:
            return (
                f"The check-in date {check_in} appears to be in the past. "
                f"Please provide a future date."
            )
        if check_in and check_out and check_out <= check_in:
            return (
                f"Check-out ({check_out}) must be after check-in ({check_in}). "
                f"Please clarify your dates."
            )

        if check_in and check_out:
            nights = (check_out - check_in).days
            return (
                f"Interpreted dates:\n"
                f"  Check-in:  {check_in}  ({check_in.strftime('%A')})\n"
                f"  Check-out: {check_out}  ({check_out.strftime('%A')})\n"
                f"  Nights:    {nights}\n\n"
                f"Please confirm these dates are correct before I save them."
            )

        return (
            f"Interpreted dates:\n"
            f"  Check-in:  {check_in}  ({check_in.strftime('%A')})\n"
            f"  Check-out: not determined\n\n"
            f"Please confirm the check-in date and provide the check-out date."
        )

    @tool
    def update_booking_draft(field_update: str) -> str:
        """
        Update a single field in the current booking draft.
        field_update: a single string with the field name and value separated by a space.
        Format: "<field_name> <value>"
        Examples:
          "check_in 2026-05-28"
          "check_out 2026-05-29"
          "guest_name Siva"
          "guest_email siva@gmail.com"
          "room_type standard"
        field_name must be one of: guest_name, guest_email, check_in, check_out, room_type.
        Always pass as one string — do NOT use separate parameters.
        """
        ALLOWED_FIELDS = {"guest_name", "guest_email", "check_in", "check_out", "room_type"}

        parts = field_update.strip().split(maxsplit=1)
        if len(parts) < 2:
            return (
                f"Invalid format. Use '<field_name> <value>', "
                f"e.g. 'check_in 2026-05-28' or 'guest_name Siva'."
            )
        field_name, new_value = parts[0].strip(), parts[1].strip()

        if field_name not in ALLOWED_FIELDS:
            return (
                f"'{field_name}' is not a valid booking field. "
                f"Allowed fields: {', '.join(sorted(ALLOWED_FIELDS))}"
            )

        if field_name == "room_type" and new_value.lower().strip() not in ("standard", "deluxe"):
            return "Invalid room type. Please choose 'standard' or 'deluxe'."

        update_draft(session_id, **{field_name: new_value})
        clear_summary_shown(session_id)  # force re-confirmation if details change
        summary = format_draft_for_prompt(session_id)
        return f"Updated {field_name} successfully.\n\nCurrent booking summary:\n{summary}"

    @tool
    def create_reservation(confirmation: str) -> str:
        """
        Create the hotel reservation using the booking draft collected so far.
        Call this ONLY after the user has explicitly confirmed all booking details
        with a "yes", "confirm", "book it", "go ahead", or equivalent affirmation.
        confirmation: pass the word "confirm".
        Reads guest_name, guest_email, check_in, check_out, room_type from the
        session draft automatically — do NOT pass them as parameters.
        """
        if not is_summary_shown(session_id):
            return (
                "BLOCKED: You must call show_booking_summary first and present it to the user. "
                "Only after the user explicitly confirms in their reply may you call create_reservation."
            )
        draft = get_draft(session_id)
        required = ["guest_name", "guest_email", "check_in", "check_out", "room_type"]
        missing = [f for f in required if not draft.get(f)]
        if missing:
            return f"Missing fields in booking draft: {', '.join(missing)}. Collect them before confirming."
        try:
            plain_draft = get_draft_with_plaintext_email(session_id)
            result = create_booking(
                plain_draft["guest_name"], plain_draft["guest_email"],
                plain_draft["check_in"], plain_draft["check_out"], plain_draft["room_type"]
            )
            clear_draft(session_id)  # also clears summary flag via clear_summary_shown
            return (
                f"Reservation confirmed!\n"
                f"Booking ID: {result['booking_id']}\n"
                f"Guest: {result['guest_name']}\n"
                f"Check-in: {result['check_in']}\n"
                f"Check-out: {result['check_out']}\n"
                f"Room type: {result['room_type'].capitalize()}\n"
                f"Status: Confirmed\n\n"
                f"Please save your Booking ID — you will need it along with your email "
                f"to view or cancel this reservation."
            )
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"An error occurred while creating the reservation: {e}"

    return {
        "get_today": get_today,
        "start_new_booking": start_new_booking,
        "lookup_existing_reservation": lookup_existing_reservation,
        "show_booking_summary": show_booking_summary,
        "parse_date_expression": parse_date_expression,
        "update_booking_draft": update_booking_draft,
        "create_reservation": create_reservation,
    }
