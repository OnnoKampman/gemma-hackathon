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

# Onboarding runs until these are known, not for a fixed number of turns.
# Each one is load-bearing downstream; nothing else is asked for.
REQUIRED_FIELDS = {
    "name": "the senior's name -- what to call them",
    "caregiver_name": "the caregiver's own name, so Jio can open on the family relationship",
    "skills": "what they are good at -- decides the volunteering role, the point of the product",
    "past_interests": "what they loved and stopped doing -- the hook a suggestion hangs on",
    "mobility_radius": "how far they will travel: walking distance, one bus, or further",
    "preferred_times": "mornings or afternoons",
    "avoidances": "stairs, heat, loud rooms, certain days -- the safety filter",
}

OPENING_QUESTION = ("Tell me about them -- what did they do for work, and what are "
                    "they good at that other people aren't?")

# A caregiver who keeps giving vague answers must not be trapped in a loop.
MAX_ONBOARD_TURNS = 6

_ONBOARD_SYSTEM = f"""{JIO}

{CAREGIVER_REGISTER}

They are setting Jio up on their parent's behalf. The senior is not in this chat.

You are told which facts are still missing. Ask about them and nothing else.
Never ask about something already known. Never ask for detail you do not need.

Cover at most TWO missing things in one question, and only where they sit
together naturally ("How far can they get, and mornings or afternoons?"). This
should be over in about three exchanges -- a caregiver doing this on their lunch
break will abandon a long interview, and an abandoned onboarding means the
senior is never contacted at all.

Acknowledge what they just said in a few words, then ask. Pull every field you
can from their answer, including ones you had not asked about yet.

If they say there is nothing to avoid, record avoidances as ["none"] -- that is
an answer, not a blank.

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


def missing_fields(profile: dict) -> list[str]:
    """Fields still worth asking about. Nothing cosmetic belongs here -- a field
    that can be inferred must never make the caregiver answer twice."""
    return [f for f in REQUIRED_FIELDS if not profile.get(f)]


def onboard_turn(profile, history, text=None, audio=None) -> tuple[str, dict, bool]:
    """-> (reply, profile_patch, complete)

    Onboarding ends when the required fields are known, not after a set number
    of questions. Completion is decided here from the profile rather than by the
    model, which given the chance will keep interviewing until the caregiver
    gives up.

    `history` must NOT yet contain the message being handled.
    """
    turns = sum(1 for h in history if h["role"] == "user") + 1
    last_turn = turns >= MAX_ONBOARD_TURNS
    gaps = missing_fields(profile)

    wanted = "; ".join(f"{f} ({REQUIRED_FIELDS[f]})" for f in gaps) or "nothing"
    instruction = (
        f"Before this message you were still missing, in priority order: {wanted}.\n"
        "Extract everything you can from what they just said, then ask about the "
        "FIRST one or two you are STILL missing -- work down that list in order, "
        "the early ones matter most.")

    contents = _contents(history, text, audio)
    data = _json_call(_ONBOARD_SYSTEM, contents + [types.Content(
        role="user", parts=[types.Part.from_text(
            text=f"[instruction to Jio, not from the caregiver] {instruction}")])])

    patch = data.get("profile_patch", {})
    after = dict(profile)
    for key, value in patch.items():
        if value not in (None, "", [], {}):
            after[key] = value
    complete = (not missing_fields(after)) or last_turn
    if not complete:
        return data.get("reply", ""), patch, False

    # The reply above was written while the model still thought something was
    # missing, so it ends on a question. Now that the profile is actually full,
    # the closing line is generated separately -- otherwise the caregiver gets
    # "...and what did he do for work?" alongside "that's everything".
    close = _json_call(_ONBOARD_SYSTEM, contents + [types.Content(
        role="user", parts=[types.Part.from_text(text=(
            "[instruction to Jio, not from the caregiver] You now have everything "
            "you need. Confirm back the one or two things that matter most, and "
            "say that's enough. Ask NOTHING further -- no question of any kind, "
            "not even a polite one. Do not mention a link; they are about to be "
            "shown a button for that."))])])
    return close.get("reply", ""), patch, True


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


_OFFER_RULES = """How an offer is made -- this is the heart of the product:

Say it like someone who knows them, because you do. Every offer names the
specific thing in their own history that makes it fit -- the job they did, the
game they stopped playing, the thing they are good at. Never a generic pitch.
A memory callback justifies the match; it is not decoration.

Motivating, never pushy. The pull is that they are wanted somewhere specific, at
a specific time, for something only they can do -- not that it would be good for
them. Never mention loneliness, health benefits, or getting out more.

Concrete. Day, time, block, what's needed. Fragments, not full sentences.
End with an easy way to say yes.

Speak as "I", never "Jio will..." about yourself."""


def open_offer(profile: dict, intro: str, offer: dict, event: dict) -> str:
    """The week's opener plus the first suggestion, in one voice note."""
    system = f"""{JIO}

{SENIOR_REGISTER}

{_OFFER_RULES}

Open the week and make the FIRST offer, in one short message under 70 words.
Mention {profile.get('caregiver_name') or 'their child'} once, lightly -- they
are why Jio is here, and hearing that name is what makes this trustworthy rather
than a cold approach. Do not labour it.

Their profile:
{json.dumps(profile, indent=2)}

The event:
{json.dumps(event, indent=2)}

Why it fits them: {offer.get('rationale_text', '')}
Suggested opener: {intro}

Reply with JSON: {{"reply": "..."}}"""
    return _json_call(system, [types.Content(role="user", parts=[types.Part.from_text(
        text="Write the opening offer.")])]).get("reply", "")


def suggestion_turn(profile: dict, current: dict, nxt: dict, history,
                    text=None, audio=None) -> tuple[str, str]:
    """Read their answer to the offer on the table. -> (reply, decision)

    decision: accepted | declined | unclear
    """
    if nxt:
        pivot = (f"If they declined, acknowledge it, ask lightly what was off "
                 f"-- not your thing, or bad timing? -- and in the same breath "
                 f"move to this one instead:\n{json.dumps(nxt, indent=2)}\n"
                 "Make it feel like a better idea, not a consolation prize.\n"
                 "There IS another suggestion left, so you must not close the "
                 "conversation here, however many times they have already said "
                 "no. Offering a different kind of thing is not pushing -- "
                 "pushing would be arguing with the no you just heard.")
    else:
        pivot = ("If they declined, that was the last one. Close warmly and "
                 "briefly: no guilt, no comment on the pattern, no pressure. Say "
                 "you'll look for something different next week. Do not offer "
                 "anything else, and do not ask them to reconsider.")

    system = f"""{JIO}

{SENIOR_REGISTER}

{_OFFER_RULES}

This is on the table right now:
{json.dumps(current, indent=2)}

Their profile:
{json.dumps(profile, indent=2)}

Decide what they just said about it:
- "accepted": any yes, however hedged -- "okay lah", "can", "why not", "I'll try"
- "declined": any no, or a reason that amounts to no
- "unclear": a question, a tangent, or something you genuinely cannot read

If accepted: confirm warmly and practically -- day, time, where, who to look for.
Nothing else.
{pivot}
If unclear: answer what they actually said, then put the same offer back gently.
Never treat hesitation or a question as a refusal.

Reply with JSON:
{{"reply": "<under 50 words>", "decision": "accepted|declined|unclear"}}"""
    data = _json_call(system, _contents(history, text, audio))
    decision = data.get("decision", "unclear")
    return data.get("reply", ""), decision if decision in ("accepted", "declined", "unclear") else "unclear"


def senior_chat(profile: dict, history, text=None, audio=None,
                events: list | None = None, confirmed: dict | None = None) -> tuple[str, dict]:
    """Free conversation with the senior, outside the follow-up loop.

    This is where the guide's edge cases live: refusal, off-topic, distress,
    "are you a robot", and re-contact after silence.

    `events` and `confirmed` matter more than they look: this runs *after* an
    activity is accepted, so "what time was that again?" arrives here. Without
    them Jio cannot answer a question about the thing it just signed them up for.
    """
    booked = (f"\nThey have said yes to this, and it is the most likely thing they "
              f"are asking about:\n{json.dumps(confirmed, indent=2)}\n" if confirmed else "")
    catalogue = (f"\nEverything on locally, for answering questions about what's "
                 f"available:\n{json.dumps(events, indent=2)}\n" if events else "")

    system = f"""{JIO}

{SENIOR_REGISTER}

You are in ordinary conversation with the senior. Their profile:
{json.dumps(profile, indent=2)}
{booked}{catalogue}
Answer practical questions -- when, where, how to get there, who to ask for --
straight from the details above. Never invent a time, a place or a name, and
never guess: if it is not written above, say you'll check and come back to them.

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


def suggest(profile: dict, events: list, memory: str = "") -> list[dict]:
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
    note = (f"\n\nWhat you've learned about them so far -- this outranks the raw "
            f"profile where they disagree:\n{memory}" if memory else "")
    contents = [types.Content(role="user", parts=[types.Part.from_text(
        text=f"Profile:\n{json.dumps(profile, indent=2)}{note}"
             f"\n\nEvents:\n{json.dumps(events, indent=2)}")])]
    data = _json_call(system, contents)
    return data.get("intro", ""), data.get("suggestions", [])


# One question per turn, in this order. Never compounded into one voice note.
FOLLOWUP_STEPS = {
    "did_go": "Did they go?",
    "how_was_it": "How was it?",
    "best_part": "What was the best part?",
    "disliked": "Anything they didn't like?",
    "more_or_different": "Do they want more like that, or something different?",
    "barrier": "What got in the way? Logistics, nerves, health, or did they forget?",
}


def next_followup_step(answering: str, feedback: dict) -> str:
    """Given the question they just answered, what comes next.

    The branch is the point: someone who didn't go is never marched through
    questions about an event that didn't happen.
    """
    if answering == "open":
        return "did_go"
    if answering == "did_go":
        return "how_was_it" if feedback.get("attended") else "barrier"
    if answering == "barrier":
        return "done"
    order = ["how_was_it", "best_part", "disliked", "more_or_different", "done"]
    return order[order.index(answering) + 1] if answering in order[:-1] else "done"


def followup_turn(profile: dict, event: dict, history, answering: str,
                  text=None, audio=None) -> tuple[str, dict]:
    """One turn of the follow-up. -> (reply, feedback_patch)

    `answering` is the question they just replied to -- "open" for the first
    message. Jio asks whatever comes NEXT, which for did_go depends on what
    they just said, so the branch is decided in the same generation.
    """
    if answering == "open":
        ask = f"Open the follow-up. Ask exactly one thing: {FOLLOWUP_STEPS['did_go']}"
    elif answering == "did_go":
        ask = ("They are telling you whether they went.\n"
               f"If they DID go, now ask: {FOLLOWUP_STEPS['how_was_it']}\n"
               f"If they did NOT go, ask ONCE, lightly: {FOLLOWUP_STEPS['barrier']} "
               "-- no guilt, no disappointment, no hint they should have gone, and "
               "nothing else about it afterwards.")
    elif answering == "barrier":
        ask = ("Take the reason, say nothing more about it, and close. You'll find "
               "something for next week. Ask nothing further.")
    else:
        nxt = next_followup_step(answering, {"attended": True})
        ask = ("Close the conversation warmly and briefly. Ask nothing further."
               if nxt == "done" else f"Now ask exactly one thing: {FOLLOWUP_STEPS[nxt]}")

    system = f"""{JIO}

{SENIOR_REGISTER}

They were signed up for this:
{json.dumps(event, indent=2)}

Their profile:
{json.dumps(profile, indent=2)}

Follow the guide's "Post-event follow-up" section. Open neutral and factual, and
let their answer set the emotional register -- if they are flat or practical,
stay practical. Never celebrate attendance; praising an adult for turning up
lands badly.

ONE question per turn. Never bundle two questions into one voice note, however
naturally they seem to go together. Acknowledge what they just said in a few
words first, then ask.

{ask}

If what they said mentions other people, note how many they spoke to face to
face -- but never ask it as a survey question.

Reply with JSON:
{{"reply": "<under 35 words>",
  "feedback": {{"attended": true|false|null, "enjoyed": [], "disliked": [],
                "barrier": "logistics|nerves|health|forgot|none|null",
                "next_interest_signal": "<what they want more or less of, or null>",
                "connection_count": <people spoken to face to face, or null>}}}}"""
    data = _json_call(system, _contents(history, text, audio))
    return data.get("reply", ""), data.get("feedback", {})


def update_memory(profile: dict, memory: str, event: dict, feedback: dict) -> str:
    """Rolling narrative summary. The design is explicit that the next cycle
    adjusts qualitatively off this, not through a lookup table of rules."""
    system = f"""You keep a short rolling note about one person, for an agent that
suggests local activities to them. Rewrite the note to fold in what just
happened. Keep it under 120 words, plain prose, no bullets, no headings.

Record what actually happened and what it implies for what to suggest next --
what landed, what didn't, what to avoid offering again. Concrete and specific.
No sentiment, no speculation about their feelings, no clinical language.

Existing note (may be empty):
{memory or "(nothing yet)"}

Profile:
{json.dumps(profile, indent=2)}

They were signed up for:
{json.dumps(event, indent=2)}

What came back:
{json.dumps(feedback, indent=2)}

Reply with JSON: {{"reply": "<the rewritten note>"}}"""
    return _json_call(system, [types.Content(role="user", parts=[types.Part.from_text(
        text="Rewrite the note.")])]).get("reply", memory or "")
