# Skill Spec — Event Suggestion

**Belongs to:** product-spec.md §6 (Event engine). This document makes that section precise enough to build against — the exact algorithm, scoring formula, trigger, and message flow for how Jio turns a `Profile` and the `Events` table into the three weekly suggestions.

**Owner (per team-split-v2.md):** Role 3 — Events, Roles & Matching, in coordination with Role 1 (message flow/persona) and Role 2 (profile/memory fields consumed).

---

## 1. Job story

Every week, when [senior]'s scheduled suggestion time arrives, Jio wants to surface up to three concrete things to do — one easy, one new, one where they're needed — each with a one-line reason, so that [senior] can say yes without having to search for it themselves.

---

## 2. Trigger

**Fixed weekly schedule, per user.** Each `Profile` has a `preferred_times[]` field (from onboarding §5, Q6). The suggestion cycle fires once per week on a day/time derived from that preference (e.g. the start of their stated preferred window).

- This is a proactive, task-scoped trigger — allowed under the locked scope decision in product-spec.md §3.
- Hackathon implementation: same time-skip mechanism as the follow-up loop (§8) — a demo-only command fast-forwards to "next Monday" rather than a real cron wait.
- A cycle does **not** fire if the previous cycle's suggestions are still open (no reply yet) — see §7.

---

## 3. Inputs

```
generate_weekly_suggestions(profile_id, week) →
  reads:
    Profile           (radius, times, group_size, avoidances, skills, interests, past_interests)
    Memory             (rolling narrative summary — recent barriers, next_interest_signal)
    Events             (curated Bukit Merah seed set, ~40 entries)
    Suggestion[]       (this user's history — prior sent/declined/attended, for scoring only, not hard exclusion)
```

No hard "never show this again" list is maintained. Declined and attended events remain visible to the scorer; recency and outcome are scoring inputs (§5), and Memory's qualitative signal (from FeedbackTurn, per §8 of product-spec.md) is read by the same reasoning surface that writes rationale templates' variable slots (§8 below). This keeps suppression judgment-based rather than a brittle exclusion rule, consistent with how the follow-up loop already updates memory qualitatively rather than through hardcoded rules.

---

## 4. Algorithm

```
1. HARD FILTER the Events table against the Profile:
     - within mobility_radius
     - matches at least one preferred_times[] window
     - group_size within group_size_preference tolerance
     - none of Event's implied conditions match Profile.avoidances[]
     - Event.datetime falls within the coming week
     - if group_size or accessibility_notes are unset on an Event, treat as pass (don't filter on missing data)

   IF the filtered set has fewer than 3 events:
     WIDEN once — relax radius by one tier (e.g. walking → one bus) and/or
     widen the time-of-day window — and re-filter.
     (Auto-widen silently; do not ask the caregiver or senior first.)

2. SCORE every event that survives the hard filter (§5) against the Profile + Memory.

3. RANK by score, descending. Take the top 8 as the candidate shortlist.
   (Top-N shortlist, not the full filtered set — keeps the composition step
   in §6 cheap and keeps rationale generation bounded.)

4. SELECT 3 from the shortlist per the composition rule (§6).

5. WRITE each selection as a Suggestion record:
     { id, user_id, event_id, week, type, rationale_text, confidence: score, status: sent }

6. RENDER rationale_text from the template library (§8), filling slots from
   Profile + the specific Event.

7. HAND OFF to the conversation layer (Role 1) for turn-by-turn presentation (§7).
```

---

## 5. Scoring formula

Deterministic, weighted — same style as the Spark match score in product-spec.md §7, for the same reason: auditability. A government buyer (§15) can be shown *why* a suggestion was ranked where it was; there is no black-box LLM ranking step to defend.

`score(event, profile, memory)` = weighted sum, each term 0–1 before weighting:

| Signal | Weight | How it's computed |
|---|---|---|
| Interest match | 0.30 | Overlap between `event.tags` (implicit from title/org/type) and `profile.interests[] / past_interests[]` |
| Proximity | 0.20 | Closer block scores higher; same-block = 1.0, one-bus = 0.5, edge-of-radius = 0.2 |
| Time-of-day fit | 0.15 | 1.0 if event falls inside a `preferred_times[]` window, 0.5 if adjacent, 0 otherwise (should already be filtered out at 0, kept as a soft term for near-boundary cases from the widened search) |
| Skill match (role events only) | 0.20 | Overlap between `event.skills_wanted[]` and `profile.skills[]`; 0 for non-role events |
| Recency/outcome adjustment | 0.10 | +1.0 if this event/org was attended and enjoyed before (from FeedbackTurn), −0.5 if declined in the last 2 cycles, 0 otherwise — a soft nudge, not a hard exclusion |
| Novelty | 0.05 | +1.0 if the event type is *not* in `past_interests[]`/recent Suggestions (rewards "stretch"-shaped events during scoring, composition in §6 still decides slot assignment) |

Role events additionally require `event.has_role = true`; skill match only applies there.

This formula is the concrete implementation behind the "filtered on mobility radius, time-of-day preference, group size, avoidances, and prior feedback" line in product-spec.md §6 — that sentence described the inputs; this table is the function.

---

## 6. Composition rule (3 slots)

Fixed target, per product-spec.md §6:
1. **Easy** — top-scoring event the senior has plausibly done before (high interest-match + high recency/outcome term)
2. **Stretch** — top-scoring event that's new to them (high novelty term), still inside mobility radius
3. **Role** — top-scoring event where `has_role = true` **and** skill match > 0

**Fallback when no role event with skill match > 0 exists in the shortlist:**
Do **not** force a bad-fit role match. Swap the 3rd slot for the next-best stretch-shaped event instead, so the week ships 2 stretch-flavoured picks and 1 easy pick rather than a role nobody asked for. This trades off the "always one role" ideal against suggestion quality — acceptable because role-matching quality (not role-presence alone) is what protects the mentoring pitch in §1's evidence table.

If the shortlist can't fill even 2 distinct slots after widening (§4 step 1), send however many distinct events are available (1 or 2) rather than repeating one event across slots.

---

## 7. Presentation flow

Sequential, one suggestion per turn — matching the "short turns, never a monologue" persona rule (product-spec.md §4):

```
Jio → suggestion 1 (voice note or text, with rationale)
Senior → accept / decline / "read me the next one"
Jio → (if declined or asked) suggestion 2
Senior → accept / decline
Jio → (if declined or asked) suggestion 3
Senior → accept / decline
```

- The senior can accept **more than one** of the 3 in a cycle — each accepted suggestion becomes its own confirmed commitment (independent `Suggestion.status` transitions), since a mobile, independent senior may reasonably go to two things in a week.
- Jio does not wait for all 3 to be delivered before letting the senior act — if they say yes to suggestion 1, Jio confirms it (per §6 of product-spec.md: what/where/when/how/who) and then still offers 2 and 3 in the same or a follow-on turn, unless the senior declines twice in a row (existing hard rule, product-spec.md §4: "never pushes after two consecutive refusals in one conversation" — offering the 3rd after 2 declines would violate this, so the cycle stops at 2 declines and simply doesn't present the 3rd suggestion that day).
- A cycle stays "open" (not re-triggered next week) until the senior has responded to at least the presented suggestions or the follow-up/escalation logic in §8 of product-spec.md takes over.

---

## 8. Rationale rendering (templated, not LLM-generated per turn)

Deterministic templates with profile/event field slots — chosen over live LLM generation for cost, latency, and consistency in the demo. Each `type` has a template family; pick by which signal scored highest for that event.

```
Interest-match template:
  "{event.title} at {event.block} — you mentioned {profile.interest_matched}, this is that."

Skill/role template:
  "{event.org} needs someone for {event.role_description}. You did {profile.skill_matched}
   for {profile.years_if_known} — they need exactly that."

Novelty/stretch template:
  "Something different this week — {event.title}, {event.block}. {event.group_size_label} group,
   {event.time_label}."

Proximity template (fallback when no strong interest/skill signal):
  "{event.title}, {distance_label} from you, {event.time_label}."
```

Slot values are pulled directly from `Profile` and `Event` fields already in the data model (product-spec.md §12) — no new free-text generation step, no risk of the template inventing a fact not in the profile. `profile.interest_matched` / `profile.skill_matched` are just the specific array entries that drove the score in §5, not new fields.

---

## 9. Edge cases

| Case | Behaviour |
|---|---|
| Fewer than 2 events survive even after widening | Send what's available (1–2), no error state shown to the senior — Jio just offers what it has |
| Same event scores highest for two slots | Never repeat an event within one cycle — take the next-best distinct event for the second slot |
| Senior has no recorded skills (`skills[]` empty) | Skill match term = 0 for all events; role slot falls back per §6 |
| Two consecutive declines before all 3 offered | Stop the cycle at 2 declines (persona hard rule); mark unpresented suggestion(s) as `status: not_sent`, not `declined` |
| Suggestion accepted, then a Spark match is also attending that event | Confirmation message says so, per product-spec.md §6 ("If there's a Spark match attending, Jio says so") — handled by the confirmation step, not this skill |

---

## 10. Function-calling surface (product-spec.md §11)

Refines the existing `search_events(profile, week)` tool signature:

```
search_events(profile_id, week) → Event[]        // hard filter + widen, §4 step 1
score_events(events, profile, memory) → ScoredEvent[]   // §5
select_suggestions(scored_events) → Suggestion[3 or fewer]  // §6
```

`find_mentoring_role(skills, radius)` (existing tool) is the role-slot-specific case of `search_events` filtered to `has_role = true` — reused here rather than duplicated, called when scoring the role slot in step 4.

No change to the `Suggestion` shape in product-spec.md §12 — `confidence` now has a concrete definition: the weighted score from §5, 0–1.
