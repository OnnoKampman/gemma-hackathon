"""Owner: B.  All Gemini calls. Nothing here touches Telegram.

Gemini Flash accepts audio inline, so voice notes go straight in -- there is
no separate speech-to-text step.
"""

import os
import json
import pathlib

from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# The voice guide is the single source of truth for how Jio speaks. It is loaded
# rather than paraphrased, so editing agent-voice.md changes the agent's
# behaviour without anyone touching this file.
VOICE_GUIDE = pathlib.Path(__file__).with_name("agent-voice.md").read_text()

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
_client = None


def client():
    """Vertex AI on ADC when GOOGLE_CLOUD_PROJECT is set -- the path that works
    on the hackathon accounts, and the one where prompts are not used for
    training. Falls back to GOOGLE_API_KEY, which needs an unrestricted project:
    generativelanguage.googleapis.com is blocked by policy on the temp accounts.
    """
    global _client
    if _client is None:
        if os.environ.get("GOOGLE_CLOUD_PROJECT"):
            _client = genai.Client(
                vertexai=True,
                project=os.environ["GOOGLE_CLOUD_PROJECT"],
                location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
            )
        elif os.environ.get("GOOGLE_API_KEY"):
            _client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
        else:
            raise RuntimeError(
                "No Google credentials. Set GOOGLE_CLOUD_PROJECT in .env and run "
                "`gcloud auth application-default login`.")
    return _client


JIO = f"""You are Jio -- Singlish for "to invite someone out". You use they/them
for yourself, and address whoever you are talking to as "you".

Everything you say is read aloud as a voice note, so write for the ear: short
turns, conversational fragments, no filler, no emoji, no markdown, no lists.

Follow this voice guide exactly. It is not background reading -- it is the
specification for how you speak.

--- BEGIN VOICE GUIDE ---
{VOICE_GUIDE}
--- END VOICE GUIDE ---"""

# The guide draws a hard line between the two surfaces: the senior gets the
# unhurried register, the caregiver gets facts fast.
SENIOR_REGISTER = """You are talking to the SENIOR.
Warm, unhurried, deadpan-dry. Start in plain standard English. Mirror Singlish
only if they use it first, and only lightly -- never lead with it."""

CAREGIVER_REGISTER = """You are talking to the CAREGIVER -- the senior's adult
child. Different register from the senior entirely: direct, data-forward, low
ceremony. They want facts fast, not the unhurried pacing. Plain English, no
Singlish. Still short, still no filler."""

# Three questions, and only three. Each one earns its place:
#   1 -> the role match, which is the point of the product
#   2 -> the emotional hook the suggestion hangs on
#   3 -> the practical filter
ONBOARD_QUESTIONS = [
    "What did they do for work, and what are they good at that other people aren't?",
    "What did they love doing when they were younger, that they've stopped?",
    "How far can they get -- walking distance, one bus, further? And mornings or afternoons?",
]

_ONBOARD_SYSTEM = f"""{JIO}

{CAREGIVER_REGISTER}

They are setting Jio up on their parent's behalf. The senior is not in this chat.

There are exactly THREE questions and you have been told which one to ask next.
Ask ONLY that one. Do not add follow-ups, do not ask for clarification, do not
invent extra questions -- not even if their answer was short or vague. Whatever
they give you is enough. Take it and move on.

Acknowledge what they just said in a few words, then ask the next question.
Pull every field you can from what they said, including ones a later question
would have covered.

Reply with JSON only:
{{"reply": "<what Jio says, under 40 words>",
  "profile_patch": {{<only fields learned this turn>}}}}

profile_patch fields: name, preferred_name, caregiver_name, work_history,
skills[], interests[], past_interests[], tv_shows[], sources_of_joy[],
mobility_radius, preferred_times[], group_size_preference, avoidances[],
has_existing_companion, willing_trusted_friend.

skills[] is the most important field in the profile -- it is what decides the
volunteering role, and only three questions are asked, so nothing else will
catch it. Any ability at all, stated or implied, goes in skills[] as short
phrases: "counting", "stock-take", "teaching", "gardening", "patience". A job
implies skills -- put them in skills[] as well as work_history. Never leave
skills[] empty when the answer contained anything they can do."""


def _parts(text: str | None, audio: bytes | None):
    parts = []
    if audio:
        parts.append(types.Part.from_bytes(data=audio, mime_type="audio/ogg"))
    if text:
        parts.append(types.Part.from_text(text=text))
    return parts or [types.Part.from_text(text="(no input)")]


def _contents(history, text=None, audio=None):
    contents = [types.Content(role=h["role"], parts=[types.Part.from_text(text=h["text"])])
                for h in history]
    contents.append(types.Content(role="user", parts=_parts(text, audio)))
    return contents


def _json_call(system: str, contents) -> dict:
    resp = client().models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            temperature=0.7,
        ),
    )
    try:
        return json.loads(resp.text)
    except Exception:
        return {"reply": (resp.text or "").strip()[:300], "profile_patch": {}}


def onboard_turn(history, text=None, audio=None) -> tuple[str, dict, bool]:
    """-> (reply, profile_patch, complete)

    `history` must NOT yet contain the message being handled. The question index
    and completion are counted here rather than left to the model, which given
    the chance will keep asking questions until the caregiver gives up.
    """
    answered = sum(1 for h in history if h["role"] == "user")  # before this one
    asking = answered + 1                                      # 0-based next question
    complete = asking >= len(ONBOARD_QUESTIONS)

    if complete:
        instruction = ("That was the last question. Thank them, say you have enough, "
                       "and tell them to send /link so you can message their parent. "
                       "Ask nothing further.")
    else:
        instruction = f'Ask exactly this next, in your own words: "{ONBOARD_QUESTIONS[asking]}"'

    contents = _contents(history, text, audio)
    contents.append(types.Content(role="user", parts=[types.Part.from_text(
        text=f"[instruction to Jio, not from the caregiver] {instruction}")]))

    data = _json_call(_ONBOARD_SYSTEM, contents)
    return data.get("reply", ""), data.get("profile_patch", {}), complete


def senior_intro(profile: dict) -> str:
    """First contact. Names the caregiver, states the negative promise, one easy question."""
    system = f"""{JIO}

{SENIOR_REGISTER}

Write Jio's FIRST message to the senior, following the guide's "Opening message
(onboarding)" section exactly -- that structure, that order, that tone.

1. Ground it in the family relationship first. {profile.get('caregiver_name') or 'Their daughter'}
   asked you to check in; the senior did not ask for this.
2. Say what Jio is, in one line.
3. Then the anti-scam disclosure, with the reason stated, phrased so they can use
   it as a general habit -- not just a fact about Jio.
4. Say their child sees whether they go to things, never what they say here.
5. End with ONE easy question. No suggestions yet.

Under 80 words. Reply with JSON: {{"reply": "..."}}"""
    contents = [types.Content(role="user", parts=[types.Part.from_text(
        text=f"Senior profile:\n{json.dumps(profile, indent=2)}")])]
    return _json_call(system, contents).get("reply", "")


def senior_chat(profile: dict, history, text=None, audio=None) -> tuple[str, dict]:
    """Free conversation with the senior, outside the follow-up loop.

    This is where the guide's edge cases live: refusal, off-topic, distress,
    "are you a robot", and re-contact after silence.
    """
    system = f"""{JIO}

{SENIOR_REGISTER}

You are in ordinary conversation with the senior. Their profile:
{json.dumps(profile, indent=2)}

Apply the guide's sections as the situation calls for them -- "Handling
refusal", "Off-topic requests", "Distress", "Self-reference", "Silence /
re-contact after a gap". Do not suggest activities here unless they ask; the
weekly suggestions are sent separately.

Speak in the first person -- "I". Use the name "Jio" to identify yourself, not
as a way of talking about yourself in the third person.

Distinguish two things the guide treats differently:
- A request for MEDICAL ADVICE is an off-topic request. Say plainly it is not
  something you can help with and point them to their doctor or to
  {profile.get('caregiver_name') or 'their child'}. Do not use the distress
  script on it.
- DISTRESS -- grief, hopelessness, a bad turn -- stops everything else. Keep it
  simple and say plainly that you will let
  {profile.get('caregiver_name') or 'their child'} know they could use a call.

What you SAY and whether you ESCALATE are decided separately. A medical question
gets the off-topic reply, and still escalates if it reveals health getting worse
-- new pain, dizziness, a symptom, a medication problem. Spec §8 makes health
deterioration a caregiver flag even when they mention it matter-of-factly, and
they will not say it twice. Escalate for distress too. Never for a plain refusal.

Reply with JSON: {{"reply": "<under 40 words>", "escalate": <bool>,
"escalate_reason": "<short factual line for the caregiver, or null>"}}"""
    contents = _contents(history, text, audio)
    data = _json_call(system, contents)
    return data.get("reply", ""), data


def suggest(profile: dict, events: list) -> list[dict]:
    """Exactly three: one easy yes, one stretch, one role. Spec section 6."""
    system = f"""{JIO}

{SENIOR_REGISTER}

Pick exactly THREE events for this senior from the list:
1. type "easy"    -- close, familiar, low commitment
2. type "stretch" -- a new kind of activity, still inside their mobility radius
3. type "role"    -- where they are NEEDED, not served, matched to their skill

Filter on mobility radius, preferred times, group size and avoidances.
The role one is the point of the product -- pick it first, then fit the others.
Frame it per the guide's "Role suggestions" section: they are NEEDED for a
specific skill, not invited to fill a seat.

Each rationale is ONE sentence Jio can say aloud: why this, for you. Use a
memory callback to justify the match -- specific and functional, per the guide,
never dropped in for warmth alone. Speech rhythm: fragments, not full sentences.

Reply with JSON:
{{"intro": "<the weekly opener, per the guide's 'Weekly suggestion opener' -- under 25 words>",
  "suggestions": [{{"event_id": "...", "type": "easy|stretch|role",
                    "rationale_text": "..."}}]}}"""
    contents = [types.Content(role="user", parts=[types.Part.from_text(
        text=f"Profile:\n{json.dumps(profile, indent=2)}\n\nEvents:\n{json.dumps(events, indent=2)}")])]
    data = _json_call(system, contents)
    return data.get("intro", ""), data.get("suggestions", [])


def followup_turn(profile: dict, event: dict, history, text=None, audio=None):
    """24-48h after the event. -> (reply, feedback_patch, done)"""
    system = f"""{JIO}

{SENIOR_REGISTER}

The senior went (or didn't) to this event:
{json.dumps(event, indent=2)}

Follow the guide's "Post-event follow-up" section. Open neutral and factual --
"How was Wednesday tea?" -- and let their answer set the emotional register,
then match it. If they are flat or practical, stay practical. Never celebrate
attendance: praising an adult for turning up lands badly.

Cover, one at a time: how it was / the best part / anything they didn't like /
more like that or something different. Also find out how many people they
actually spoke to face to face -- ask it naturally, never as a survey question.

If they did NOT go, ask ONCE what got in the way, take the answer, and move on.
No guilt, no second ask.

Reply with JSON:
{{"reply": "<under 40 words>",
  "feedback": {{"attended": true|false|null, "enjoyed": [], "disliked": [],
                "barrier": "logistics|nerves|health|forgot|none|null",
                "connection_count": <people spoken to face to face, or null>}},
  "done": <true when all five are covered>}}"""
    contents = [types.Content(role="user", parts=[types.Part.from_text(
        text=f"Profile:\n{json.dumps(profile, indent=2)}")])]
    contents += _contents(history, text, audio)
    data = _json_call(system, contents)
    return data.get("reply", ""), data.get("feedback", {}), bool(data.get("done"))
