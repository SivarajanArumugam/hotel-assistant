import re

NON_ASSISTANT_INTENTS = [
    r"\bwrite\s+(me\s+)?(a\s+)?(poem|story|essay|song|haiku|sonnet|limerick|rap|letter|speech|script|blog|article|paragraph|caption)\b",
    r"\bcompose\s+(a\s+)?(poem|song|story|essay|letter)\b",
    r"\btell\s+(me\s+)?a\s+(joke|story|fun\s+fact|riddle|pun)\b",
    r"\brecite\s+(a\s+)?(poem|quote)\b",
    r"\bsing\s+(a\s+)?(song|tune)\b",
    r"\btranslate\s+(this|to|into)\b",
    r"\bexplain\s+(the\s+)?(history|science|origin|philosophy|economics)\b",
    r"\bgive\s+(me\s+)?(a\s+)?(recipe|workout|diet|exercise|lesson)\b",
    r"\bwhat\s+is\s+the\s+(capital|population|currency|president|prime\s+minister)\b",
    r"\bwho\s+(is|was|invented|discovered|wrote|founded)\b",
    r"\b(solve|calculate|compute)\b.*\bequation\b",
    r"\bmath(ematic)?s?\b.*\b(solve|calculate|compute|equation)\b",
    r"\bcode\s+(a|for|in|this)\b",
    r"\b(debug|fix)\s+(my\s+)?(code|program|script|function)\b",
]

INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above|earlier)\s+instructions?",
    r"disregard\s+(all\s+)?(previous|prior|above|earlier)\s+instructions?",
    r"forget\s+(everything|all|previous|prior|your instructions)",
    r"you\s+are\s+now\s+",
    r"act\s+as\s+(if\s+you\s+are|a\s+|an\s+)",
    r"pretend\s+(you\s+are|to\s+be)",
    r"roleplay\s+as",
    r"new\s+persona",
    r"jailbreak",
    r"bypass\s+(your\s+)?(restrictions?|rules?|guidelines?|filters?)",
    r"override\s+(your\s+)?(instructions?|restrictions?|rules?)",
    r"system\s*prompt",
    r"reveal\s+(your\s+)?(instructions?|prompt|system)",
    r"print\s+(your\s+)?(instructions?|prompt|system)",
    r"show\s+me\s+(your\s+)?(instructions?|prompt|system|rules?)",
    r"what\s+(are\s+)?your\s+(instructions?|rules?|prompt)",
    r"developer\s+mode",
    r"<\s*script",
    r"\{\{.*?\}\}",
    r"__import__",
]

HOTEL_KEYWORDS = [
    # greetings — let the agent handle these naturally
    "hi", "hello", "hey", "good morning", "good afternoon", "good evening",
    "thanks", "thank you", "help",
    # conversation connectors — affirmations, negations, short replies
    "yes", "no", "yep", "nope", "ok", "okay", "sure", "confirm", "confirmed",
    "correct", "right", "that's right", "sounds good", "perfect", "great",
    "go ahead", "proceed", "done", "alright", "agreed",
    "hotel", "room", "book", "booking", "reservation", "check",
    "check-in", "check-out", "checkin", "checkout", "cancel",
    "food", "menu", "restaurant", "dining", "breakfast", "lunch", "dinner",
    "wifi", "parking", "pool", "gym", "spa", "amenity", "amenities",
    "policy", "policies", "price", "rate", "floor", "suite",
    "hygiene", "safety", "sanitize", "clean", "housekeeping",
    "reception", "concierge", "front desk", "staff", "service",
    "vegetarian", "vegan", "allergy", "dish", "meal",
    "guest", "stay", "night", "arrival", "departure",
    "refund", "payment", "charge", "fee", "id", "email", "name",
    "view", "show", "my booking", "view my", "cancel my",
]

_INJECTION_REFUSAL = (
    "I'm not able to process that request. I'm a hotel assistant and I can\n"
    "only help with hotel information and reservations."
)

_OFFTOPIC_REFUSAL = (
    "I can only assist with questions about the hotel and reservation management.\n"
    "For anything else, please contact our front desk directly."
)


def check_injection(user_input: str) -> tuple[bool, str]:
    """
    Returns (is_injection, refusal_message).
    If is_injection is True, return the refusal_message to the user directly.
    Do not pass the input to the agent.
    """
    lowered = user_input.lower()
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, lowered):
            return True, _INJECTION_REFUSAL
    return False, ""


def _has_non_assistant_intent(text: str) -> bool:
    t = text.lower()
    return any(re.search(p, t) for p in NON_ASSISTANT_INTENTS)


def is_off_topic(user_input: str, recent_context: str = "") -> tuple[bool, str]:
    """
    Returns (is_off_topic, refusal_message).
    Only call this if check_injection returned False.
    If is_off_topic is True, return the refusal_message to the user directly.
    Falls back to checking recent_context so pronoun follow-ups are allowed through.
    """
    if _has_non_assistant_intent(user_input):
        return True, _OFFTOPIC_REFUSAL

    lowered = user_input.lower()
    for keyword in HOTEL_KEYWORDS:
        if keyword in lowered:
            return False, ""
    if recent_context:
        lowered_ctx = recent_context.lower()
        for keyword in HOTEL_KEYWORDS:
            if keyword in lowered_ctx:
                return False, ""
    return True, _OFFTOPIC_REFUSAL
