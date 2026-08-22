# Jio — 2 hour build

## Get running (3 minutes)

```bash
source .venv/bin/activate      # Python 3.12, deps already installed
cp .env.example .env
python voice.py                # writes /tmp/jio_caregiver.ogg and /tmp/jio_senior.ogg — listen to both
python bot.py
```

`TELEGRAM_BOT_TOKEN` comes from @BotFather (`/newbot`).

### Google auth — ADC, not an API key

An API key will not work here, for two independent reasons:

- **Cloud TTS does not accept API keys on any project.** It answers
  `401 API keys are not supported by this API`. This is not an enablement
  setting; there is no version of this that works.
- **`generativelanguage.googleapis.com` is blocked by policy** on the temp
  hackathon accounts, so the key-based Gemini endpoint 403s too.

So, once per machine:

```bash
gcloud auth application-default login
gcloud config set project YOUR_PROJECT
gcloud auth application-default set-quota-project YOUR_PROJECT
gcloud services enable aiplatform.googleapis.com texttospeech.googleapis.com
```

Then set `GOOGLE_CLOUD_PROJECT` in `.env`. Gemini runs on **Vertex AI** — same
models, different service, and prompts are not used for training, which is also
the answer if a judge asks about the PDPA posture.

ADC is per machine and cannot be shared, so all four of you run it. If
`GOOGLE_CLOUD_LOCATION=global` is rejected for the model, use `us-central1`.

## Who owns what

Work in your own file. Nobody edits anyone else's.

| Owner | File | Job |
|---|---|---|
| A | `bot.py` | Telegram plumbing, routing, demo commands |
| B | `agent.py` | The four Gemini prompts. This is where the product actually lives. |
| C | `voice.py` | TTS. Pick the two voices, tune rate. |
| D | `events.json` + demo | Seed events, demo script, dry runs, **owns the laptop** |

`store.py` is shared and frozen — add fields, don't restructure.

## The two voices

Caregiver chat is British male, senior chat is American female. They are never
the same voice, and that is the point: the caregiver and the senior are in two
different rooms. It is the audible version of spec §10 — the caregiver sees
whether they went, never what they said. Say this in the pitch; it also answers
"isn't this a deepfake grandchild?" before anyone asks it.

## Demo flow

A bot cannot message someone who has not started a chat with it. So:

1. **Caregiver phone** — `/start`, answer Jio's questions by voice. Profile card fills in live.
2. **Caregiver phone** — `/link`, forward the link to the senior's chat.
3. **Senior phone** — tap the link. Jio's first message arrives in the American female voice: names the daughter, states the never-ask-for-money promise, one easy question.
4. Senior replies by voice note.
5. **Caregiver phone** — `/suggest`. Three suggestions land on the senior's phone; the third is a role. Senior taps "Put my name down".
6. **Caregiver phone** — `/followup`, then `/metrics`.

`/profile` any time to show what Jio knows.

## Rules for the next two hours

- **Scope froze at 0:10.** No new features. Spark matching is a spoken line in the follow-up, not code.
- Every Gemini and TTS call already falls back instead of crashing. Keep it that way.
- **Record the backup video at 1:40 regardless of what works.** Judges forgive a thin feature. They do not forgive a dead demo.

## Honesty in the demo

`events.json` is curated, not live — say so on the slide. There are no public
APIs for AAC programmes, and that gap *is* the government pitch.
