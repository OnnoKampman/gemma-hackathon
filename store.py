"""Shared state. Single demo pair, in memory. Deliberately not a database."""

CAREGIVER_CHAT_ID = None
SENIOR_CHAT_ID = None

# "onboarding" -> "awaiting_senior" -> "senior_intro" -> "suggesting" -> "followup"
PHASE = "onboarding"

PROFILE = {
    "name": None,
    "preferred_name": None,
    "caregiver_name": None,
    "work_history": None,
    "skills": [],
    "interests": [],
    "past_interests": [],
    "tv_shows": [],
    "sources_of_joy": [],
    "mobility_radius": None,
    "preferred_times": [],
    "group_size_preference": None,
    "avoidances": [],
    "has_existing_companion": None,
    "willing_trusted_friend": None,
}

ONBOARD_HISTORY = []   # [{"role": "user"|"model", "text": str}]
SENIOR_HISTORY = []

SUGGESTIONS = []       # [{"event_id", "type", "rationale_text", "status"}]
CONFIRMED_EVENT = None
FEEDBACK = {}

METRICS = {
    "connection_count_before": 1,
    "connection_count_after": 1,
    "zero_contact_days_before": 5,
    "zero_contact_days_after": 5,
    "role_held": False,
}


def profile_patch(patch: dict) -> None:
    """Merge a partial profile. Lists union, scalars overwrite when non-null."""
    for key, value in (patch or {}).items():
        if key not in PROFILE or value in (None, "", [], {}):
            continue
        if isinstance(PROFILE[key], list):
            for item in value if isinstance(value, list) else [value]:
                if item not in PROFILE[key]:
                    PROFILE[key].append(item)
        else:
            PROFILE[key] = value


def profile_filled() -> int:
    return sum(1 for v in PROFILE.values() if v not in (None, "", [], {}))


def role_for(chat_id: int) -> str | None:
    if chat_id == CAREGIVER_CHAT_ID:
        return "caregiver"
    if chat_id == SENIOR_CHAT_ID:
        return "senior"
    return None
