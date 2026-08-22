"""Owner: A.  Telegram plumbing. One bot, two roles, two voices.

Demo control commands (run these from the CAREGIVER chat):
  /link      deep link to forward to the senior
  /intro     send Jio's first message to the senior
  /suggest   send this week's three suggestions
  /followup  start the post-event follow-up
  /metrics   the closing numbers
  /profile   what Jio knows so far
"""

import os
import json
import asyncio
import logging
import pathlib
import contextlib
from datetime import datetime, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import (Application, CommandHandler, MessageHandler,
                          CallbackQueryHandler, ContextTypes, filters)
from dotenv import load_dotenv

import store
import agent
import voice

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
for noisy in ("httpx", "google_genai", "google_genai.models", "telegram", "httpcore"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
log = logging.getLogger("jio")

EVENTS_DIR = pathlib.Path(__file__).with_name("events")


def _load_events() -> list[dict]:
    """Every .json and .csv in events/, deduped by id.

    The scraper writes CSV on the schema in product-spec.md §12, so its output
    can be dropped straight into this folder without a conversion step.
    """
    events, seen = [], set()
    for path in sorted(EVENTS_DIR.glob("*.json")) + sorted(EVENTS_DIR.glob("*.csv")):
        if path.suffix == ".json":
            rows = json.loads(path.read_text())
        else:
            import csv
            with path.open(newline="", encoding="utf-8") as f:
                rows = [_from_csv(r) for r in csv.DictReader(f)]
        for e in rows:
            if e.get("id") and e["id"] not in seen:
                seen.add(e["id"])
                events.append(e)
    return events


def _from_csv(row: dict) -> dict:
    """CSV stores everything as strings; the prompts expect lists and bools."""
    e = dict(row)
    e["has_role"] = str(row.get("has_role", "")).strip().lower() in ("yes", "true", "1")
    for key in ("languages", "skills_wanted"):
        raw = (row.get(key) or "").strip()
        e[key] = [v.strip() for v in raw.split(",") if v.strip()]
    return e


EVENTS = _load_events()
EVENTS_BY_ID = {e["id"]: e for e in EVENTS}


@contextlib.asynccontextmanager
async def thinking(context, chat_id: int, action: str = ChatAction.RECORD_VOICE):
    """Show 'recording audio...' while Gemini and TTS work.

    Telegram drops a chat action after ~5 seconds, so it has to be re-sent. A
    reply here takes 3-6s and silence that long reads as a broken bot.
    """
    stop = asyncio.Event()

    async def beat():
        while not stop.is_set():
            try:
                await context.bot.send_chat_action(chat_id, action)
            except Exception as exc:
                log.debug("chat action failed: %s", exc)
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=4)

    task = asyncio.create_task(beat())
    try:
        yield
    finally:
        stop.set()
        await task


async def say(context, chat_id: int, text: str, role: str, **kwargs):
    """Voice note in the role's voice, with the text alongside. Falls back to
    text only if TTS fails -- a dead demo is worse than a silent one."""
    if not text:
        return
    try:
        await context.bot.send_voice(chat_id, voice.synthesize(text, role),
                                     caption=text[:1000], **kwargs)
    except Exception as exc:
        log.warning("tts failed, sending text: %s", exc)
        await context.bot.send_message(chat_id, text, **kwargs)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    arg = (context.args or [None])[0]

    if arg == "senior":
        store.SENIOR_CHAT_ID = chat_id
        store.PHASE = "senior_intro"
        log.info("senior joined: %s", chat_id)
        # Exactly the draft the caregiver approved, or generate it if they
        # reached the bot some other way.
        intro = store.DRAFT_INTRO or agent.senior_intro(store.PROFILE)
        await say(context, chat_id, intro, "senior")
        return

    store.CAREGIVER_CHAT_ID = chat_id
    store.PHASE = "consent"
    log.info("caregiver joined: %s", chat_id)

    # The caregiver onboards, but the senior is the data subject (spec §10).
    # Nothing is collected before this is answered.
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Yes, they've agreed", callback_data="consent:yes")],
        [InlineKeyboardButton("Not yet", callback_data="consent:no")],
    ])
    await context.bot.send_message(
        chat_id,
        "I'm Jio. Your parent never signs up for anything — you tell me about them, "
        "I do the rest.\n\n"
        "First, though: they're the one I'll be messaging, so they get to decide. "
        "I'll keep what you tell me to suggest activities, match them with someone "
        "nearby, and let you know if they stop engaging. Nothing else.\n\n"
        "*Have they agreed to be contacted?*",
        parse_mode="Markdown", reply_markup=kb)


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if store.role_for(chat_id) is None:
        return await update.message.reply_text("Send /start to begin.")
    async with thinking(context, chat_id):
        await _handle_message(update, context)


async def _handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    role = store.role_for(chat_id)

    text = update.message.text
    audio = None
    if update.message.voice:
        f = await update.message.voice.get_file()
        audio = bytes(await f.download_as_bytearray())

    if role == "caregiver" and store.PHASE == "consent":
        return await update.message.reply_text(
            "Answer the question above first — I can't collect anything about them "
            "until they've agreed. /start to see it again.")

    if role == "caregiver" and store.PHASE == "onboarding":
        # History must exclude the current message -- onboard_turn counts the
        # user turns in it to know when it has run out of patience.
        reply, patch, complete = agent.onboard_turn(
            store.PROFILE, store.ONBOARD_HISTORY, text, audio)
        store.profile_patch(patch)
        store.ONBOARD_HISTORY.append({"role": "user", "text": text or "(voice note)"})
        store.ONBOARD_HISTORY.append({"role": "model", "text": reply})
        await say(context, chat_id, reply, "caregiver")
        if patch:
            await context.bot.send_message(chat_id, _profile_card(), parse_mode="Markdown")
        if complete:
            store.PHASE = "awaiting_senior"
            await context.bot.send_message(
                chat_id, "That's enough to go on.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                    "Generate a link to share with them", callback_data="link:go")]]))
        return

    if role == "senior" and store.PHASE == "suggesting":
        offer, ev = _current_offer()
        nxt = (EVENTS_BY_ID.get(store.SUGGESTIONS[store.OFFER_INDEX + 1]["event_id"])
               if store.OFFER_INDEX + 1 < len(store.SUGGESTIONS) else None)

        reply, decision = agent.suggestion_turn(
            store.PROFILE, ev, nxt, store.SENIOR_HISTORY, text, audio)
        store.SENIOR_HISTORY += [{"role": "user", "text": text or "(voice note)"},
                                 {"role": "model", "text": reply}]
        log.info("offer %s -> %s", ev["id"], decision)

        if decision == "accepted":
            await _accept(context, ev, reply)
        elif decision == "declined":
            store.DECLINED.append(ev["id"])
            store.OFFER_INDEX += 1
            nxt_offer, nxt_event = _current_offer()
            if nxt_event:
                # The reply already pivots to the next one; attach its buttons.
                await say(context, chat_id, reply, "senior",
                          reply_markup=_offer_keyboard(nxt_event["id"]))
            else:
                store.PHASE = "senior_intro"   # back to ordinary conversation
                store.CYCLES_ALL_DECLINED += 1
                await say(context, chat_id, reply, "senior")
                if store.CAREGIVER_CHAT_ID:
                    note = "They passed on all three this week."
                    if store.CYCLES_ALL_DECLINED >= 3:
                        note += (f" That's {store.CYCLES_ALL_DECLINED} weeks running with "
                                 "nothing taken up. Worth a call.")
                    else:
                        note += " Nothing wrong — I'll try a different kind of thing next week."
                    await context.bot.send_message(store.CAREGIVER_CHAT_ID, note)
        else:
            await say(context, chat_id, reply, "senior",
                      reply_markup=_offer_keyboard(ev["id"]))
        return

    if role == "senior":
        if store.PHASE == "followup":
            asked = store.FOLLOWUP_STEP
            reply, fb = agent.followup_turn(
                store.PROFILE, store.CONFIRMED_EVENT, store.SENIOR_HISTORY,
                asked, text, audio)
            store.FEEDBACK.update({k: v for k, v in fb.items() if v is not None})
            if fb.get("connection_count"):
                store.METRICS["connection_count_after"] = fb["connection_count"]

            store.FOLLOWUP_STEP = agent.next_followup_step(asked, store.FEEDBACK)
            log.info("followup %s -> %s", asked, store.FOLLOWUP_STEP)

            if store.FOLLOWUP_STEP == "done":
                store.PHASE = "senior_intro"
                if store.FEEDBACK.get("attended"):
                    store.METRICS["zero_contact_days_after"] = 1
                store.MEMORY = agent.update_memory(
                    store.PROFILE, store.MEMORY, store.CONFIRMED_EVENT, store.FEEDBACK)
                log.info("memory: %s", store.MEMORY)
                await _report_to_caregiver(context)
        else:
            reply, data = agent.senior_chat(store.PROFILE, store.SENIOR_HISTORY, text, audio,
                                            events=EVENTS, confirmed=store.CONFIRMED_EVENT)
            if data.get("escalate") and store.CAREGIVER_CHAT_ID:
                await context.bot.send_message(
                    store.CAREGIVER_CHAT_ID,
                    f"Flagging: {data.get('escalate_reason') or 'they sound like they need a call'}.")
        store.SENIOR_HISTORY += [{"role": "user", "text": text or "(voice note)"},
                                 {"role": "model", "text": reply}]
        return await say(context, chat_id, reply, "senior")


async def send_link(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """A bot cannot message someone who hasn't started a chat with it. The
    caregiver forwards this into the family chat; the senior taps once.

    They also see the draft first message. Spec §10 makes the caregiver the
    scam-verification channel, and they can only vouch for what they've read.
    """
    if not store.CONSENT_AT:
        return await context.bot.send_message(chat_id, "Not until they've agreed. /start")

    async with thinking(context, chat_id, ChatAction.TYPING):
        store.DRAFT_INTRO = agent.senior_intro(store.PROFILE)
    await context.bot.send_message(
        chat_id,
        f"Here's what I'll say to them, word for word:\n\n_{store.DRAFT_INTRO}_\n\n"
        "If they ever wonder whether a message is really from me, you're the one "
        "they check with.",
        parse_mode="Markdown")

    # Sent WITHOUT parse_mode. Bot usernames contain underscores, which Markdown
    # eats as italics -- t.me/jio_singapore_bot silently becomes
    # t.me/jiosingaporebot, and the link 404s.
    me = await context.bot.get_me()
    await context.bot.send_message(
        chat_id, f"Forward this to them:\nhttps://t.me/{me.username}?start=senior")


async def link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_link(context, update.effective_chat.id)


async def intro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not store.SENIOR_CHAT_ID:
        return await update.message.reply_text("Senior hasn't tapped the link yet -- /link")
    async with thinking(context, store.SENIOR_CHAT_ID):
        await say(context, store.SENIOR_CHAT_ID, agent.senior_intro(store.PROFILE), "senior")


def _current_offer():
    """The suggestion on the table, as (offer, event). (None, None) when spent."""
    if store.OFFER_INDEX >= len(store.SUGGESTIONS):
        return None, None
    offer = store.SUGGESTIONS[store.OFFER_INDEX]
    return offer, EVENTS_BY_ID.get(offer["event_id"])


def _offer_keyboard(event_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Put my name down", callback_data=f"yes:{event_id}"),
        InlineKeyboardButton("Not this one", callback_data=f"no:{event_id}")]])


async def suggest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Opens the week. One offer at a time -- the next only if they pass."""
    if not store.SENIOR_CHAT_ID:
        return await update.message.reply_text("Senior hasn't tapped the link yet -- /link")

    async with thinking(context, store.SENIOR_CHAT_ID):
        intro_line, store.SUGGESTIONS = agent.suggest(store.PROFILE, EVENTS, store.MEMORY)
        store.OFFER_INDEX, store.DECLINED = 0, []
        store.PHASE = "suggesting"

        offer, ev = _current_offer()
        if not ev:
            return await update.message.reply_text("No suggestions came back -- try again.")
        spoken = agent.open_offer(store.PROFILE, intro_line, offer, ev)
        store.SENIOR_HISTORY.append({"role": "model", "text": spoken})
        await say(context, store.SENIOR_CHAT_ID, spoken, "senior",
                  reply_markup=_offer_keyboard(ev["id"]))


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    async with thinking(context, q.message.chat_id):
        await _handle_button(update, context)


async def _handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    action, arg = q.data.split(":", 1)

    if action == "link":
        await q.edit_message_text("That's enough to go on.")
        return await send_link(context, q.message.chat_id)

    if action == "consent":
        if arg == "no":
            store.PHASE = "consent"
            return await q.edit_message_text(
                "That's the right order. Ask them first — I'll be here. "
                "Send /start again when they've said yes.")
        store.CONSENT_AT = datetime.now(timezone.utc).isoformat(timespec="seconds")
        store.PHASE = "onboarding"
        await q.edit_message_text("Noted, and logged with the time. They can tell me to "
                                  "stop at any point and I'll stop.")
        return await say(context, q.message.chat_id,
                         f"Now — {agent.OPENING_QUESTION}", "caregiver")

    ev = EVENTS_BY_ID[arg]
    try:
        await q.edit_message_reply_markup(reply_markup=None)   # spend the buttons
    except Exception:
        pass

    if action == "no":
        # Same path as saying "no" out loud, so the two never diverge.
        store.DECLINED.append(ev["id"])
        store.OFFER_INDEX += 1
        nxt_offer, nxt_event = _current_offer()
        reply, _ = agent.suggestion_turn(store.PROFILE, ev, nxt_event,
                                         store.SENIOR_HISTORY, "No, not that one.")
        store.SENIOR_HISTORY.append({"role": "model", "text": reply})
        if nxt_event:
            return await say(context, q.message.chat_id, reply, "senior",
                             reply_markup=_offer_keyboard(nxt_event["id"]))
        store.PHASE = "senior_intro"
        return await say(context, q.message.chat_id, reply, "senior")

    await _accept(context, ev)


async def _accept(context: ContextTypes.DEFAULT_TYPE, ev: dict, reply: str | None = None):
    store.CONFIRMED_EVENT = ev
    store.PHASE = "senior_intro"
    if ev.get("has_role"):
        store.METRICS["role_held"] = True
    await say(context, store.SENIOR_CHAT_ID,
              reply or (f"Done. {ev['datetime']}, {ev['address']}. "
                        f"{ev.get('arrival_note', 'Ask at the front desk for the coordinator.')} "
                        "I'll check in with you after."), "senior")
    if store.CAREGIVER_CHAT_ID:
        await context.bot.send_message(store.CAREGIVER_CHAT_ID, f"They said yes to: {ev['title']}")


async def _report_to_caregiver(context: ContextTypes.DEFAULT_TYPE):
    """Factual summary of what changed -- never a transcript (spec §8)."""
    if not store.CAREGIVER_CHAT_ID:
        return
    fb, ev = store.FEEDBACK, store.CONFIRMED_EVENT
    if fb.get("attended"):
        line = f"They went to {ev['title']}."
        if fb.get("connection_count"):
            line += f" Spoke to {fb['connection_count']} people."
        if fb.get("next_interest_signal"):
            line += f" Wants: {fb['next_interest_signal']}."
    else:
        line = (f"They didn't make it to {ev['title']}"
                + (f" — {fb['barrier']}." if fb.get("barrier") else "."))
    await context.bot.send_message(store.CAREGIVER_CHAT_ID, line)


async def followup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Time-skip to the day after. Runs from either chat; the conversation
    always happens in the senior's existing thread."""
    if not store.SENIOR_CHAT_ID:
        return await update.message.reply_text("Senior hasn't tapped the link yet -- /link")
    if not store.CONFIRMED_EVENT:
        return await update.message.reply_text("Nothing confirmed yet -- /suggest")

    store.PHASE = "followup"
    store.FOLLOWUP_STEP = "did_go"     # the question now on the table
    store.FEEDBACK, store.NUDGED = {}, False
    store.SENIOR_HISTORY.clear()
    async with thinking(context, store.SENIOR_CHAT_ID):
        reply, _ = agent.followup_turn(store.PROFILE, store.CONFIRMED_EVENT, [],
                                       "open", "(open the follow-up)")
        store.SENIOR_HISTORY.append({"role": "model", "text": reply})
        await say(context, store.SENIOR_CHAT_ID, reply, "senior")


async def nudge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """One gentle nudge inside the window, then it's dropped for good."""
    if store.PHASE != "followup":
        return await update.message.reply_text("No follow-up open -- /followup")
    if store.NUDGED:
        return await update.message.reply_text(
            "Already nudged once. Silence counts as a non-response for this cycle.")
    store.NUDGED = True
    store.CYCLES_NO_RESPONSE += 1
    async with thinking(context, store.SENIOR_CHAT_ID):
        reply, _ = agent.followup_turn(
            store.PROFILE, store.CONFIRMED_EVENT, store.SENIOR_HISTORY,
            store.FOLLOWUP_STEP,
            "(they haven't replied -- nudge once, lightly, no pressure, then drop it)")
        await say(context, store.SENIOR_CHAT_ID, reply, "senior")


async def metrics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = store.METRICS
    await update.message.reply_text(
        f"*{store.PROFILE.get('preferred_name') or 'Them'} — week 1*\n"
        f"Connection Count  {m['connection_count_before']} → {m['connection_count_after']}\n"
        f"Zero-Contact Days {m['zero_contact_days_before']} → {m['zero_contact_days_after']}\n"
        f"Role held         {'yes' if m['role_held'] else 'no'}\n"
        f"Attendance rate   {'1/3' if store.CONFIRMED_EVENT else '0/3'}",
        parse_mode="Markdown")


def _profile_card() -> str:
    done = not agent.missing_fields(store.PROFILE)
    lines = ["*Profile*" if done else "_Building profile..._"]
    for k, v in store.PROFILE.items():
        if v not in (None, "", [], {}):
            lines.append(f"{k.replace('_', ' ')}: {', '.join(v) if isinstance(v, list) else v}")
    return "\n".join(lines)


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(_profile_card(), parse_mode="Markdown")


def main():
    app = Application.builder().token(os.environ["TELEGRAM_BOT_TOKEN"]).build()
    app.add_handler(CommandHandler("start", start))
    for name, fn in [("link", link), ("intro", intro), ("suggest", suggest),
                     ("followup", followup), ("nudge", nudge),
                     ("metrics", metrics), ("profile", profile)]:
        app.add_handler(CommandHandler(name, fn))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND | filters.VOICE, on_message))
    log.info("Jio running")
    app.run_polling()


if __name__ == "__main__":
    main()
