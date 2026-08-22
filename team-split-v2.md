# Team Split v2 — "Jio"
## 5 people, one day, submit by 3:00pm

Revised against locked decisions: **Telegram, caregiver-onboarded, English, voice notes, no telephony.**

This is a materially easier build than v1. Telegram removes the entire frontend problem, and voice notes remove the realtime-audio problem. Spend the saved time on the demo and the pitch.

---

## What changed from v1

| Was | Now | Effect |
|---|---|---|
| Custom app frontend | Telegram bot | ~4 hours saved, no UI framework |
| Realtime voice (Live API) | Async voice notes | Removes the biggest failure risk |
| Senior self-onboards | Caregiver onboards | Simpler flow, cleaner demo |
| Twilio telephony | None | Cut entirely — see spec §10 |

The one thing Telegram costs you: judges can't *see* much. Which is why role 4 changes into a metrics-and-visuals role.

---

## Roles

### 1. Bot & Conversation Lead
**Owns the Telegram surface and how Jio talks.**
- Bot up and echoing inside the first 45 minutes — everything downstream depends on it
- Voice note handling both ways: receive OGG → transcribe; text → TTS → `sendVoice` (note: 1MB inline limit, keep replies short — which the persona wants anyway)
- The Jio persona prompt: warm, unhurried, short turns, graceful refusal handling
- The anti-scam opening message — this is a scripted, demo-critical moment, get it exactly right
- **Fallback if TTS is slow: text-only with one voice note in the demo.** Decide by 11:00.

### 2. Onboarding & Profile Extraction
**Owns the caregiver interview and the profile that comes out of it.**
- The 10-question interview as a conversational Gemini flow, not a form
- Unstructured conversation → structured `Profile` object. This is the best Gemini showcase in the build — make the extraction visible.
- Memory: rolling narrative summary per user, updated after feedback
- Photo intake (optional path — cut if behind)

### 3. Events, Roles & Matching
**Owns everything Jio knows about the world.**
- **Start here, before anything else:** build the Bukit Merah seed dataset. ~40 entries across NTUC Health AAC (Blk 117), PCS Cedar Tree (Blk 105), THK (Blk 118 BM View, Blk 44 Beo Cres), SG Cares roles, PA CCs, ActiveSG. Free events. Flag which have a volunteer/mentoring role.
- Suggestion engine: one easy yes, one stretch, one role — with a spoken rationale for each
- Spark matching: weighted score, 8–10 seeded neighbour profiles, one convincing match
- Function-calling tools per spec §11

### 4. Metrics, Trust & Visuals
**Owns what the judges can actually see, and the part that wins on substance.**
- Instrument the structural metrics: Connection Count, Zero-Contact Days, Attendance Rate, Role Held, Spark co-attendances
- A single clean metrics view — this is the only screen in the whole product, so it has to carry weight
- The caregiver escalation message
- The PDPA and anti-scam surface: what's stored, who sees what, the never-ask promise. Present this as a feature, not a disclaimer.
- If ahead: a before/after visual of the senior's week

### 5. Product, Pitch & Submission
**Not a spare role. The transcript says judging turns on the problem statement.**
- The one-line problem statement: *the invitations already exist in Bukit Merah; nobody converts them into attendance*
- The evidence slide: UK Biobank (structural beats subjective), JAGES (roles beat attendance). Two lines, cited. This is what separates you from 2,000 other submissions.
- Confirm the hackathon track requirements from the Notion page and make sure the build satisfies them — **do this in the first 30 minutes**
- Demo script locked by 1:00pm
- Film from 2:00. Repo public, README, one-line description, tracks selected.
- **Submit by 3:00.** Calls the cuts and enforces the freeze.

---

## Timeline

| Time | Milestone |
|---|---|
| Start | 20-min alignment. Agree data contracts (spec §12). Role 5 reads the Notion rules and reports back. |
| +45min | **Bot echoes a message.** If not, all hands on it. |
| +2h | **Checkpoint 1.** Voice notes working both directions. Seed dataset exists. Profile schema stubbed with fake data. |
| +4h | **Checkpoint 2.** Caregiver interview produces a real profile. Suggestions return against it. Metrics render. |
| 1:00pm | **Feature freeze.** Anything broken is now cut, not fixed. Demo script locked. |
| 1:00–2:00 | Integration and rehearsal only. Run the full flow five times. |
| 2:00 | Film. Multiple takes. |
| 3:00 | **Submit.** |

---

## Stub everything in hour one

Every role codes against the schemas in spec §12 with fake data first. Real implementations swap in behind them. Nobody blocks.

---

## Three failure modes

1. **The seed dataset gets built at 1pm.** It's unglamorous so it gets deferred, and then nothing has anything to suggest. Role 3 builds it first, before writing any logic.
2. **Voice eats the day.** Async voice notes are far safer than realtime, but TTS latency can still bite. Hard fallback decision at 11:00.
3. **The demo shows plumbing, not a person.** Open on Mr Tan and his empty Tuesday. Architecture goes in the README, not the video.
