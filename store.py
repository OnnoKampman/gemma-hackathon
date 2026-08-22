"""Shared state. Single demo pair, in memory. Deliberately not a database."""

CAREGIVER_CHAT_ID = None
SENIOR_CHAT_ID = None

# "onboarding" -> "awaiting_senior" -> "senior_intro" -> "suggesting" -> "followup"
PHASE = "onboarding"

CONSENT_AT = None      # the caregiver attests the senior agreed to be contacted
DRAFT_INTRO = None     # first message, shown to the caregiver before it is sent

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

SUGGESTIONS = []       # [{"event_id", "type", "rationale_text"}], ranked
OFFER_INDEX = 0        # which of the three is on the table right now
DECLINED = []          # event ids they've said no to this conversation
CONFIRMED_EVENT = None
FEEDBACK = {}

FOLLOWUP_STEP = "did_go"   # which question the follow-up is on
MEMORY = ""                # rolling narrative summary, feeds the next cycle
NUDGED = False             # one gentle nudge per follow-up, then drop it

# Escalation counters (spec §8). Cheap to keep, and they are what the
# hackathon build is meant to demo -- the distress trigger lives in senior_chat.
CYCLES_NO_RESPONSE = 0
CYCLES_ALL_DECLINED = 0

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
