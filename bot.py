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
import logging
import pathlib

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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

EVENTS = json.loads(pathlib.Path(__file__).with_name("events.json").read_text())
EVENTS_BY_ID = {e["id"]: e for e in EVENTS}


async def say(context, chat_id: int, text: str, role: str, **kwargs):
    """Voice note in the role's voice, with the text alongside. Falls back to
    text only if TTS fails -- a dead demo is worse than a silent one."""
    if not text:
        return
    try:
        await context.bot.send_voice(chat_id, voice.synthesize(text, role), caption=text[:1000])
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
        await say(context, chat_id, agent.senior_intro(store.PROFILE), "senior")
        return

    store.CAREGIVER_CHAT_ID = chat_id
    store.PHASE = "onboarding"
    log.info("caregiver joined: %s", chat_id)
    await say(context, chat_id,
              "I'm Jio. Your parent never signs up for anything -- you tell me about "
              "them, I do the rest. Three questions, two minutes. "
              f"First one: {agent.ONBOARD_QUESTIONS[0]}", "caregiver")


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    role = store.role_for(chat_id)
    if role is None:
        return await update.message.reply_text("Send /start to begin.")

    text = update.message.text
    audio = None
    if update.message.voice:
        f = await update.message.voice.get_file()
        audio = bytes(await f.download_as_bytearray())

    if role == "caregiver" and store.PHASE == "onboarding":
        # History must exclude the current message -- agent.onboard_turn counts
        # the user turns in it to work out which question comes next.
        reply, patch, complete = agent.onboard_turn(store.ONBOARD_HISTORY, text, audio)
        store.profile_patch(patch)
        store.ONBOARD_HISTORY.append({"role": "user", "text": text or "(voice note)"})
        store.ONBOARD_HISTORY.append({"role": "model", "text": reply})
        await say(context, chat_id, reply, "caregiver")
        if patch:
            await context.bot.send_message(chat_id, _profile_card(), parse_mode="Markdown")
        if complete:
            store.PHASE = "awaiting_senior"
            await context.bot.send_message(chat_id, "That's everything I need. Send /link.")
        return

    if role == "senior":
        if store.PHASE == "followup":
            reply, fb, done = agent.followup_turn(
                store.PROFILE, store.CONFIRMED_EVENT, store.SENIOR_HISTORY, text, audio)
            store.FEEDBACK.update({k: v for k, v in fb.items() if v is not None})
            if fb.get("connection_count"):
                store.METRICS["connection_count_after"] = fb["connection_count"]
            if done:
                store.METRICS["zero_contact_days_after"] = 1
        else:
            reply, data = agent.senior_chat(store.PROFILE, store.SENIOR_HISTORY, text, audio)
            if data.get("escalate") and store.CAREGIVER_CHAT_ID:
                await context.bot.send_message(
                    store.CAREGIVER_CHAT_ID,
                    f"Flagging: {data.get('escalate_reason') or 'they sound like they need a call'}.")
        store.SENIOR_HISTORY += [{"role": "user", "text": text or "(voice note)"},
                                 {"role": "model", "text": reply}]
        return await say(context, chat_id, reply, "senior")


async def link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """A bot cannot message someone who hasn't started a chat with it. The
    caregiver forwards this into the family chat; the senior taps once."""
    me = await context.bot.get_me()
    await update.message.reply_text(
        f"Forward this to them:\n\nhttps://t.me/{me.username}?start=senior")


async def intro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not store.SENIOR_CHAT_ID:
        return await update.message.reply_text("Senior hasn't tapped the link yet -- /link")
    await say(context, store.SENIOR_CHAT_ID, agent.senior_intro(store.PROFILE), "senior")


async def suggest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not store.SENIOR_CHAT_ID:
        return await update.message.reply_text("Senior hasn't tapped the link yet -- /link")
    intro_line, suggestions = agent.suggest(store.PROFILE, EVENTS)
    store.SUGGESTIONS = suggestions
    store.PHASE = "suggesting"

    await say(context, store.SENIOR_CHAT_ID, intro_line, "senior")
    for s in suggestions:
        ev = EVENTS_BY_ID.get(s["event_id"])
        if not ev:
            continue
        spoken = f"{ev['title']}. {ev['datetime']}, {ev['block']}. {s['rationale_text']}"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Put my name down", callback_data=f"yes:{ev['id']}"),
                                    InlineKeyboardButton("Not this one", callback_data=f"no:{ev['id']}")]])
        try:
            await context.bot.send_voice(store.SENIOR_CHAT_ID, voice.synthesize(spoken, "senior"),
                                         caption=spoken[:1000], reply_markup=kb)
        except Exception as exc:
            log.warning("tts failed: %s", exc)
            await context.bot.send_message(store.SENIOR_CHAT_ID, spoken, reply_markup=kb)


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    action, event_id = q.data.split(":", 1)
    ev = EVENTS_BY_ID[event_id]

    if action == "no":
        return await q.edit_message_caption(caption=f"{ev['title']}\n\n— not this one")

    store.CONFIRMED_EVENT = ev
    if ev.get("has_role"):
        store.METRICS["role_held"] = True
    await q.edit_message_caption(caption=f"{ev['title']}\n\n✓ name down")
    await say(context, store.SENIOR_CHAT_ID,
              f"Done. {ev['datetime']}, {ev['address']}. {ev.get('arrival_note', 'Ask at the front desk for the coordinator.')} "
              f"I'll check in with you after.", "senior")
    if store.CAREGIVER_CHAT_ID:
        await context.bot.send_message(store.CAREGIVER_CHAT_ID, f"They said yes to: {ev['title']}")


async def followup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not store.CONFIRMED_EVENT:
        return await update.message.reply_text("Nothing confirmed yet -- /suggest")
    store.PHASE = "followup"
    store.SENIOR_HISTORY.clear()
    # Neutral and factual -- not "you went!". Praising an adult for turning up
    # lands wrong. See "Post-event follow-up" in agent-voice.md.
    reply, _, _ = agent.followup_turn(store.PROFILE, store.CONFIRMED_EVENT, [],
                                      "(open the follow-up)")
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
    lines = [f"*{store.profile_filled()}/{len(store.PROFILE)} known*"]
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
                     ("followup", followup), ("metrics", metrics), ("profile", profile)]:
        app.add_handler(CommandHandler(name, fn))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND | filters.VOICE, on_message))
    log.info("Jio running")
    app.run_polling()


if __name__ == "__main__":
    main()
