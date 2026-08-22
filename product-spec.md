# Product Specification — "Jio"
## An AI companion that gets mobile Singaporean seniors back into their community

**Version** 0.1 — hackathon build spec
**Platform** Telegram
**Pilot geography** Bukit Merah
**Status** Draft pending hackathon track requirements

---

## 1. Problem statement

How might we build low-barrier solutions that empower mobile Singaporean adults aged 60–70 to maintain meaningful social networks, driving a quantifiable increase in their daily wellbeing?

**The sharpened version, and the one to pitch:** in Bukit Merah the invitations already exist. Four Active Ageing Centres sit within a few blocks of each other running fitness, social, enrichment and volunteer programmes every week. The gap is not supply. The gap is that nobody converts a poster on a void deck into a person in a room.

**Jio closes that gap.** It notices, it suggests, it removes the friction, it follows up, and — critically — it moves the person from *attendee* to *someone with a role*.

### Evidence base

| Finding | Source | What it dictates in the product |
|---|---|---|
| Objective social isolation predicts mortality after full adjustment (HR 1.26); subjective loneliness does not (HR 0.99) | UK Biobank, ~467k people | We measure **structural** connection — people, events, days — never a loneliness score |
| Social participation reduces functional disability; benefit strengthens across multiple organisation types | JAGES, Japan | Suggest variety, not repetition of one activity |
| Holding a **leadership role** in a civic group adds protective effect against dementia onset beyond participation alone | JAGES / AGES cohort | The mentoring slot is not a bonus feature. It is the point. |

Do not cite Blue Zones. The underlying demography is contested.

---

## 2. Users

**Primary user:** Singaporean adult, 60–70, mobile and independent, living in Bukit Merah. Owns a smartphone. Uses WhatsApp or Telegram for family chat. Has time and capability but a contracting weekly routine.

**Onboarding actor (locked decision):** the **caregiver** — typically an adult child — completes onboarding on the senior's behalf. This resolves the Initiation Job: the senior never registers for anything, never learns an interface, never feels digitally inadequate. They receive a message from a name their child already told them about.

**Third party:** the Spark match — another Jio user in the same locality.

---

## 3. Locked scope decisions

| Decision | Choice | Consequence |
|---|---|---|
| Platform | Telegram | No app install, no account creation by the senior, native voice notes |
| Telephony | **None.** Voice notes only | Bot API cannot initiate calls; an unknown number is the scam signature in Singapore |
| Onboarding | Caregiver-led | Zero-friction entry; raises a consent design problem (see §9) |
| Demo language | English | Multilingual architecture, single-language demo |
| Agent identity | "They," no gender, no human persona claim | Trust and honesty; also avoids sounding like a fake grandchild |
| Proactivity | Task-scoped only | Jio initiates only for: weekly suggestions, event reminders, post-event follow-up, Spark introductions |
| Events | Free, ideally with a service or volunteer component | Removes cost barrier; aligns with the role finding |
| Matching | 1:1, seeded | Mediated contact only, no details exchanged |
| Non-engagement | Escalate to caregiver | See §8 |
| Buyer | Government (AIC / PA / MOH / AAC operators) | Shapes the metric and the privacy posture |

---

## 4. The agent

### Name
**Jio** — Singlish for "to invite someone out."

### Voice and character
- **They / them.** Jio never claims to be a person, never pretends to remember being young, never says "I understand how you feel."
- **Warm, unhurried, slightly dry.** Singaporean seniors are not sentimental and respond badly to being handled.
- **Short turns.** A voice note is 15–30 seconds. Never a monologue.
- **Encouraging without pressure.** Suggests, accepts refusal gracefully, returns next week without comment on the refusal.
- **Concrete, never abstract.** Not "would you like to be more socially active?" but "Wednesday morning, 9am, Blk 117, they need someone who can count. Twenty minutes' walk. Shall I put your name down?"

### Register examples

> "Morning, Mr Tan. Found three things this week. First one — the Blk 117 centre needs someone to help with the Wednesday tea. You did stock-take for thirty years, they need exactly that. Interested, or shall I read you the other two?"

> "No problem. I'll keep looking. Next week I'll find you something different — maybe something outdoors instead."

### Hard rules
- Jio never asks for NRIC, bank details, passwords, or OTPs — and says so, unprompted, in the first message
- Jio never asks the senior to click a link to an external site
- Jio never pushes after two consecutive refusals in one conversation
- If the senior expresses distress, Jio stops suggesting activities, responds simply, and flags the caregiver

---

## 5. Onboarding

Conducted by the caregiver, in Telegram, mixed voice and text. Target: under 8 minutes.

### Phase 1 — Consent and framing (caregiver)
- What Jio is, in two sentences
- What is stored, who can see it (§9)
- Explicit confirmation the senior has agreed to be contacted
- Caregiver provides the senior's Telegram handle

### Phase 2 — Profile interview
Conversational, not a form. Gemini extracts structured fields from unstructured answers; the caregiver sees the profile populate live.

Questions, in this order:
1. Tell me about them — what did they do for work?
2. What did they love doing when they were younger, that they've stopped doing?
3. What do they watch on TV?
4. What makes them laugh?
5. How far are they comfortable travelling? Walking distance, one bus, or further?
6. Mornings or afternoons?
7. Do they prefer a small group or a big crowd?
8. Is there a friend they already go out with?
9. What are they good at that other people aren't? *(This drives the mentoring match)*
10. Anything to avoid — stairs, heat, loud rooms, certain days?

**Photo (optional):** the caregiver may upload a photo of the senior's home area, a noticeboard, or an old photograph of them doing something they loved. Used to enrich the profile, not for identification.

### Phase 3 — Close
- "Would they like a Jio kaki — someone nearby to go to things with?"
- "Would they be willing to be someone else's trusted friend?"
- Confirm first contact time
- Explain the anti-scam anchor (§10)

### Phase 4 — First contact with the senior
Jio's opening message to the senior is short, references their child by name, and asks one easy question. No suggestions in the first exchange.

---

## 6. Event engine

### Sources (Bukit Merah pilot)

| Source | Type | Access |
|---|---|---|
| NTUC Health AAC, Blk 117 Jalan Bukit Merah | Programmes + volunteering | Curated |
| PCS Cedar Tree AAC, Blk 105 Jalan Bukit Merah | Programmes | Curated |
| THK AAC, Blk 118 Bukit Merah View | Programmes | Curated |
| THK AAC, Blk 44 Beo Crescent | Programmes | Curated |
| SG Cares / discover.nyc.gov.sg | Volunteering roles | Curated |
| People's Association CCs, Bukit Merah | Interest groups | Curated |
| ActiveSG | Fitness | Curated |

**No public APIs exist for these.** The seed dataset is curated and must be labelled as such in the demo and README. Production path: partnership with AIC or direct AAC integration — that is exactly the government pitch.

### Weekly suggestion rule
Three suggestions per week, of which **exactly one is a mentoring or volunteering role matched to their stated skill.**

Composition:
1. **One easy yes** — close, familiar, low commitment
2. **One stretch** — new activity type, still within mobility radius
3. **One role** — where they are needed, not served

Suggestions are filtered on mobility radius, time-of-day preference, group size, avoidances, and prior feedback. Each carries a one-sentence rationale Jio can say aloud: *why this, for you.*

### Confirmation
Senior replies by voice note or a single tap. Jio confirms with the practical details only: what, where, when, how to get there, who to look for on arrival. If there's a Spark match attending, Jio says so.

---

## 7. Spark Friend

**Job:** match the user 1:1 with a peer they'd plausibly enjoy — the Shared Context Job.

### Matching signals
- Locality (same or adjacent blocks)
- Overlapping interests, present and past
- Life stage — retired, widowed, caregiving, still working part-time
- Language preference
- Social appetite — small group vs crowd
- Schedule compatibility
- Complementary skills — one mentors, one learns

Weighted score, OkCupid-style. **Transparent by design:** Jio can state why two people were matched.

### Rules
- **All contact stays mediated.** No phone numbers, no addresses, no Telegram handles exchanged.
- Introduction happens *at an event*, never as a cold pairing: "Mdm Lim is going to the same Thursday session. She also used to sew. I told her to look out for you."
- Both parties consent to the introduction before either name is shared.
- Either can decline silently; the other is never told.
- Trusted-friend status is the same relationship, upgraded: a Spark pair who have co-attended can opt to become each other's trusted friend, which means Jio may tell them if the other stops turning up.

### Hackathon implementation
8–10 seeded profiles in the Bukit Merah area. One high-quality match surfaced for the demo persona. The scoring is real; the population is seeded.

---

## 8. Follow-up loop

24–48 hours after a confirmed event, Jio sends a voice note:

1. Did you go?
2. How was it?
3. What was the best part?
4. Anything you didn't like?
5. Want more like that, or something different?

Answers update the profile and memory. If they didn't go, Jio asks once what got in the way — logistics, nerves, health, forgot — and adjusts future suggestions accordingly. No guilt, no repeated asking.

### Escalation to caregiver
Jio notifies the caregiver when:
- Three consecutive suggestion cycles pass with no response at all
- The senior declines every suggestion for three consecutive weeks
- Confirmed attendance drops to zero after a period of attending
- The senior expresses distress, or mentions health deterioration

The escalation is a factual summary — what changed and when — not a transcript and not an interpretation.

---

## 9. Measurement

Structural only. No loneliness scales.

| Metric | Definition | Cadence |
|---|---|---|
| **Connection Count** | Distinct people spoken to face-to-face in the past 7 days | Weekly, self-reported in follow-up |
| **Attendance Rate** | Confirmed attendances ÷ suggestions made | Rolling 4 weeks |
| **Zero-Contact Days** | Days in the past week with no face-to-face contact | Weekly |
| **Role Held** | Boolean: currently holds a recurring responsibility | Monthly |
| **Formed Friendship** ★ | A Spark pair who have independently co-attended ≥3 times, at least once without a Jio suggestion prompting it | Quarterly |

**Formed Friendship is the north star** — the point at which the product has made itself unnecessary for that pair. That is the number to put in front of a government buyer, because it is the only one that shows the effect persisting outside the intervention.

Every metric is observable behaviour. Every metric can be audited. This is the differentiator against every companionship product that has sold a feeling and lost its contracts.

---

## 10. Privacy, PDPA and anti-scam

### PDPA posture

Drafted against Singapore's Personal Data Protection Act. Confirm with counsel before any real deployment — this is a hackathon draft, not legal advice.

**Consent (§13–17 PDPA).** Two-party consent is required and this is the sharpest design problem in the product. The caregiver onboards, but the *senior* is the data subject. Therefore:
- The caregiver attests that the senior has agreed to be contacted
- Jio's first message to the senior restates, in plain language, what Jio is and what it does with what they say
- The senior can withdraw at any time by saying "stop" — no menu, no settings screen
- Withdrawal is honoured immediately and the caregiver is told that it happened, not why

**Notification (§20).** Purposes stated at collection: to suggest local activities, to match with a peer, to notify a named caregiver if engagement stops.

**Purpose limitation (§18).** Profile data is used for suggestion, matching and escalation only. Not for marketing. Not sold. Not used to train external models.

**Accuracy (§23) and Retention (§25).** Profile retained while active; purged 90 days after withdrawal or 12 months of inactivity. Voice notes transcribed, then audio deleted within 30 days; transcripts retained as profile evidence only.

**Protection (§24).** Encryption at rest and in transit. Access limited to the assigned caregiver and system operators. No cross-user visibility of raw profile data — Spark matching operates on derived scores, not on readable profiles.

**Access and correction (§21–22).** Senior or caregiver may request their profile in plain language; Jio can read it back aloud on request.

**Do Not Call.** Not engaged, because there is no telephony and no marketing message. This is a further argument against Twilio.

**Transparency to the senior about caregiver visibility.** The caregiver sees: attendance, engagement level, escalation flags. The caregiver does **not** see conversation transcripts. The senior is told this explicitly in Jio's first message. When the two parties' interests conflict, Jio is on the senior's side — and says so.

### Anti-scam design

The single largest adoption barrier for this user group. Singaporean seniors are trained by national campaign to distrust unsolicited contact.

1. **Verified account anchor.** All contact originates from one verified Telegram account, introduced by the caregiver during onboarding. Never a phone number, never an unknown caller.
2. **Stated negative promise.** In Jio's first message and repeated monthly: *"I will never ask you for money, your NRIC, your bank details, or a password. If anyone says they are from Jio and asks for those things, it is not us."*
3. **No outbound links.** Jio never sends a URL the senior must click. Directions are described in words.
4. **No payments, ever.** Free events only — which is why §3 locks it that way. There is no path in the product where money changes hands, so there is no path a scammer can imitate.
5. **Caregiver as verification channel.** The senior can always confirm with their child that a message is real.

---

## 11. Architecture

```
Telegram Bot API
  ├─ receives: text, voice notes (OGG), photos
  └─ sends:    text, voice notes, inline keyboards

Agent layer (Gemini)
  ├─ Onboarding interview      → structured profile extraction
  ├─ Suggestion reasoning      → event ranking + rationale generation
  ├─ Conversation manager      → persona, turn-taking, refusal handling
  └─ Feedback parser           → profile + memory update

Tools (function calling)
  ├─ search_events(profile, week)
  ├─ find_mentoring_role(skills, radius)
  ├─ score_spark_match(profile_a, profile_b)
  ├─ confirm_attendance(user, event)
  ├─ log_feedback(user, event, feedback)
  └─ escalate_to_caregiver(user, reason)

Data
  ├─ Profiles (structured)
  ├─ Memory (rolling narrative summary per user)
  ├─ Events (curated Bukit Merah seed set, ~40 entries)
  └─ Metrics (structural, per §9)

Audio
  ├─ In:  voice note → transcription
  └─ Out: text → TTS → OGG → sendVoice
```

**Multilingual path (architecture only, English demo).** Language is a profile field. Transcription, reasoning and TTS all key off it. Singlish and Hokkien need prompt-level register instruction rather than a separate language code. Nothing in the architecture assumes English; the demo simply uses it.

---

## 12. Data model

```
Profile {
  id, telegram_handle, name, preferred_name,
  caregiver_id, consent_confirmed_at,
  languages[], age_band, locality, block,
  work_history, skills[],
  interests[], past_interests[],
  tv_shows[], sources_of_joy[],
  mobility_radius, preferred_times[], group_size_preference,
  avoidances[],
  has_existing_companion, willing_trusted_friend,
  spark_match_id, trusted_friend_ids[],
  created_at, last_engaged_at
}

Event {
  id, title, organisation, block, address, lat_lng,
  datetime, recurrence, cost, languages[],
  accessibility_notes, group_size,
  has_role, role_description, skills_wanted[],
  source, source_verified_at
}

Suggestion {
  id, user_id, event_id, week,
  type: easy | stretch | role,
  rationale_text, confidence,
  status: sent | confirmed | declined | attended | no_show
}

FeedbackTurn {
  suggestion_id, attended, enjoyed[], disliked[],
  barrier: logistics | nerves | health | forgot | none,
  next_interest_signal, recorded_at
}

Metrics {
  user_id, week,
  connection_count, zero_contact_days,
  attendance_rate, role_held,
  spark_coattendances
}
```

---

## 13. Out of scope for the hackathon

Build the architecture so these slot in; do not build them today.

- Real telephony
- Live event API integrations
- Six-language support (architecture supports it; demo is English)
- Trained ML matching (weighted score instead)
- Caregiver dashboard beyond an escalation message
- Real authentication, real PDPA-compliant storage
- Group formation beyond 1:1

---

## 14. Demo narrative (under 3 minutes)

1. **0:00–0:20** — The problem, in one person. Mr Tan, 67, Bukit Merah. Four Active Ageing Centres within a ten-minute walk. He hasn't been to any of them. His daughter worries on the phone twice a week and nothing changes.
2. **0:20–1:00** — Daughter onboards Jio in Telegram. Voice interview. Profile builds visibly on screen: thirty years in stock-take, likes badminton, stopped after his knee, watches Channel 8 dramas, one bus maximum.
3. **1:00–1:40** — Jio's first message to Mr Tan. Short. Names his daughter. States the never-ask-for-money promise. Mr Tan replies by voice note.
4. **1:40–2:20** — Three suggestions arrive. The third is a role: the Blk 117 centre needs help with Wednesday stock. He confirms by voice.
5. **2:20–2:40** — Post-event follow-up call. He liked it. Jio surfaces Mdm Lim, who was also there and also used to play badminton.
6. **2:40–3:00** — The metric on screen. Connection Count: 1 → 6. Zero-Contact Days: 5 → 1. Role held: yes. Then the closing line.

**Closing line:** *Most products in this space stop at detection — they notice isolation and tell a family member. Jio notices, mobilises, and gives the person something to be responsible for. Detection is a smoke alarm. We built the fire brigade and the fireproofing too.*

---

## 15. Why government buys this

- **A structural, auditable metric** rather than a wellbeing claim — the thing that companionship providers elsewhere could not produce when contracts came up for renewal
- **Uses existing supply.** No new centres, no new programmes, no new headcount. It fills the seats that Active Ageing Centres already fund and already struggle to fill.
- **Fills volunteer roles as a side effect** — AACs need volunteers and are matching seniors into them anyway
- **Fits the national posture** on active ageing and on scam resilience simultaneously
- **Bukit Merah is a real pilot boundary**, with four AACs already operating and one of them already defining its service area by block radius
