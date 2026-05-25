import time
from typing import Dict, List
from cryptography.fernet import Fernet
from core.config import settings

_sessions: Dict[str, dict] = {}
_session_timestamps: Dict[str, float] = {}
SESSION_TTL_SECONDS = 3600  # 1 hour

# Fix 1: Lookup gate — must be opened before view/cancel/modify tools run
_lookup_gates: Dict[str, float] = {}  # session_id -> timestamp when gate was opened
LOOKUP_GATE_TTL = 600  # 10 minutes

# Fix 2: Summary shown flag — must be set before create_reservation runs
_summary_flags: Dict[str, bool] = {}

_ALLOWED_FIELDS = {"guest_name", "guest_email", "check_in", "check_out", "room_type"}

_FIELD_LABELS = {
    "guest_name": "Guest name",
    "guest_email": "Email",
    "check_in": "Check-in",
    "check_out": "Check-out",
    "room_type": "Room type",
}

_MISSING_LABELS = {
    "guest_name": "guest name",
    "guest_email": "email address",
    "check_in": "check-in date",
    "check_out": "check-out date",
    "room_type": "room type (standard or deluxe)",
}


def _fernet() -> Fernet:
    return Fernet(settings.fernet_key.encode() if isinstance(settings.fernet_key, str) else settings.fernet_key)


def _encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def _decrypt(value: str) -> str:
    return _fernet().decrypt(value.encode()).decode()


def _expire_old_sessions() -> None:
    now = time.time()
    expired = [sid for sid, ts in _session_timestamps.items() if now - ts > SESSION_TTL_SECONDS]
    for sid in expired:
        _sessions.pop(sid, None)
        _session_timestamps.pop(sid, None)


def get_draft(session_id: str) -> dict:
    """Returns the current draft dict for this session. Creates empty if missing."""
    _expire_old_sessions()
    _session_timestamps[session_id] = time.time()
    if session_id not in _sessions:
        _sessions[session_id] = {}
    return _sessions[session_id]


def get_draft_with_plaintext_email(session_id: str) -> dict:
    """Returns draft with guest_email decrypted. Use only when passing to DB."""
    draft = dict(get_draft(session_id))
    if "guest_email" in draft:
        draft["guest_email"] = _decrypt(draft["guest_email"])
    return draft


def update_draft(session_id: str, **fields) -> None:
    """
    Merges the provided fields into the draft.
    Allowed field keys: guest_name, guest_email, check_in, check_out, room_type.
    guest_email is stored encrypted. Any other key is silently ignored.
    """
    draft = get_draft(session_id)
    for key, value in fields.items():
        if key in _ALLOWED_FIELDS:
            draft[key] = _encrypt(value) if key == "guest_email" else value


def clear_draft(session_id: str) -> None:
    """Clears all draft fields for this session."""
    _sessions[session_id] = {}
    _session_timestamps.pop(session_id, None)
    clear_summary_shown(session_id)


# --- Fix 1: Lookup gate ---

def open_lookup_gate(session_id: str) -> None:
    _lookup_gates[session_id] = time.time()


def is_lookup_gate_open(session_id: str) -> bool:
    ts = _lookup_gates.get(session_id)
    return ts is not None and (time.time() - ts) < LOOKUP_GATE_TTL


def close_lookup_gate(session_id: str) -> None:
    _lookup_gates.pop(session_id, None)


# --- Fix 2: Booking summary flag ---

def set_summary_shown(session_id: str) -> None:
    _summary_flags[session_id] = True


def is_summary_shown(session_id: str) -> bool:
    return _summary_flags.get(session_id, False)


def clear_summary_shown(session_id: str) -> None:
    _summary_flags[session_id] = False


def format_draft_for_prompt(session_id: str) -> str:
    """
    Returns a human-readable string describing what has been collected
    and what is still needed. Used to populate {draft_state} in the system prompt.
    Never includes the raw email value — uses '[collected]' instead.
    """
    draft = get_draft(session_id)
    if not draft:
        return "No booking in progress."

    lines = ["Booking in progress:"]
    for field in ("guest_name", "guest_email", "check_in", "check_out", "room_type"):
        label = _FIELD_LABELS[field]
        if field in draft:
            if field == "guest_email":
                lines.append(f"- {label}: [collected]  ✓")
            else:
                lines.append(f"- {label}: {draft[field]}  ✓")
        else:
            lines.append(f"- {label}: [not yet provided]")
    return "\n".join(lines)


def get_missing_fields(session_id: str) -> List[str]:
    """
    Returns a list of field names that have not yet been collected.
    Possible values in the list: 'guest name', 'email address',
    'check-in date', 'check-out date'.
    """
    draft = get_draft(session_id)
    missing = []
    for field in ("guest_name", "guest_email", "check_in", "check_out", "room_type"):
        if field not in draft:
            missing.append(_MISSING_LABELS[field])
    return missing
