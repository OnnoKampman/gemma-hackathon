# gemma-hackathon

## Overview

Team of four people.
6 hours to complete the entire project from ideation to publishing.

### Three tracks

Best Use of Gemma: Push an open model somewhere thoughtful, useful, or technically surprising. Gemma’s openness, deployability, privacy, efficiency, or adaptability is essential—not interchangeable.
Best Elderly Hack: Make modern technology easier for older adults to use, trust, and stay connected through. A senior, caregiver, or eldercare worker can complete a meaningful task with low friction and appropriate safety.
Most Creative Gemini Hack: Build the wildest, fastest, or most original use of Gemini Flash 3.7. Gemini’s speed or multimodal behavior creates a memorable live moment.

More info: https://65labs-gemini-hack.notion.site

## Problem Statement

How might we build low-barrier solutions that empower mobile Singaporean adults aged 60-70 to maintain meaningful social networks, driving a quantifiable increase in their daily wellbeing?

## Jobs to be Done

We focus on jobs 1, 2, 3, and 5.

### The "Initiation" Job

When I want to join a new local activity or digital community,
I want to bypass complex registrations, unfamiliar interfaces, or steep learning curves,
So I can participate immediately without feeling frustrated or digitally inadequate.

### The "Shared Context" Job

When I reach out to connect with others,
I want to easily find peers who share my specific life stage, interests, or neighborhood,
So I can engage in conversations that feel genuinely relevant and deeply engaging.

### The "Psychological Safety" Job

When I am introduced to a new social platform or community initiative,
I want to immediately know that it is a secure, scam-free environment that respects my privacy,
So I can overcome my fear of vulnerability and engage without anxiety.

### The "Peer and Friend" Job

When I see a peer or friend elderly person socially isolating,
I want to inspire and encourage them to engage in activities,
So I feel a sense of responsibility and being a contributing member of society.

### The "Caregiver" Job

When I see the person in my care socially isolate,
I want to facilitate them to find a community they can engage in,
So I worry less about them.

## Solution

**Jio** — Singlish for "to invite someone out". A Telegram agent that gets mobile
Singaporean seniors back into their community. The caregiver onboards on the
senior's behalf, so the senior never registers for anything; Jio then talks to
the senior directly by voice note, suggests three local activities a week — one
of which is a *role*, not a seat — and follows up afterwards.

Full product spec: [product-spec.md](product-spec.md).

## Tech Stack

### Components

| Layer | Choice | Why |
|---|---|---|
| Surface | Telegram Bot API (`python-telegram-bot` 22.x) | No app install, no account creation by the senior, native voice notes |
| Reasoning | Gemini Flash via `google-genai` | Accepts audio inline — no separate speech-to-text step |
| Speech in | Gemini, direct from OGG voice notes | One hop instead of two; no Whisper, no transcription service |
| Speech out | Google Cloud Text-to-Speech (REST) | Locale is in the voice name, so the two accents are deterministic |
| Audio transcode | ffmpeg → OGG/Opus | Telegram `sendVoice` accepts nothing else |
| State | Python dict in `store.py` | Single demo pair. A database would be scaffolding for users we don't have yet. |
| Events | Curated JSON, 12 Bukit Merah entries | No public API exists for AAC programmes — that gap *is* the government pitch |

Runtime is Python 3.12 in a `uv` venv.

### Two voices

The caregiver hears a **British male** voice. The senior hears an **American
female** voice. They are never the same voice, and that is deliberate: it is the
audible form of the privacy boundary in the spec — the caregiver sees *whether*
their parent went to something, never *what they said*. Jio is on the senior's
side, and it sounds like it.

### Flow

```
caregiver phone                      senior phone
     |                                    |
  /start                                  |
     |  voice/text  -->  Gemini  -->  profile (live card)
     |                                    |
  /link  ---- t.me/bot?start=senior ----> tap
     |                                    |
     |                          Gemini -> intro -> TTS(US female) -> voice note
     |                                    |
  /suggest ------------------------> 3 suggestions: easy / stretch / role
     |                                    |  tap "put my name down"
  /followup ------------------------> did you go? how was it?
     |                                    |
  /metrics  <-- connection count, zero-contact days, role held
```

A Telegram bot cannot message someone who has not first started a chat with it.
Hence the deep link: the caregiver forwards it into the family chat the senior
already uses, and the senior taps once. That single tap is the entire
registration burden the product places on them.

### Repo layout

| File | Owner | Contents |
|---|---|---|
| `bot.py` | A | Telegram handlers, routing, demo commands |
| `agent.py` | B | The four Gemini prompts — onboard, intro, suggest, follow-up |
| `voice.py` | C | TTS + ffmpeg transcode |
| `events.json` | D | Seed events, 5 of 12 carrying a role |
| `store.py` | shared | State. Frozen — add fields, don't restructure. |

### Setup

See [SETUP.md](SETUP.md). A BotFather token, plus Application Default
Credentials from `gcloud auth application-default login` — Gemini runs on Vertex
AI and TTS on the same credentials. API keys are not an option: Cloud TTS
rejects them outright, and the key-based Gemini endpoint is blocked by policy on
the hackathon accounts.

### Notes for the pitch

- Every Gemini and TTS call falls back to text rather than crashing.
- `events.json` is curated, not live. Say so on the slide.
- This stack is Gemini-only. It targets the Elderly and Gemini tracks; the Gemma
  track would need an on-device component we have not built.
