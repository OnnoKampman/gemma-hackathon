"""Owner: C.  Text -> OGG/Opus bytes for Telegram sendVoice.

Two fixed voices, and the distinction is the product:
  caregiver chat -> British male
  senior chat    -> American female
The caregiver and the senior never hear the same voice.

Google Cloud Text-to-Speech over REST, authenticated with Application Default
Credentials. Cloud TTS does not accept API keys -- it answers 401 "API keys are
not supported by this API" on every project -- so ADC is the only option here,
not a fallback. Run `gcloud auth application-default login`.
"""

import os
import base64
import subprocess
import tempfile

import requests
from dotenv import load_dotenv

load_dotenv()

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
ENDPOINT = "https://texttospeech.googleapis.com/v1/text:synthesize"

_creds = None


def _auth() -> dict:
    """-> request headers carrying an ADC bearer token."""
    global _creds
    import google.auth
    import google.auth.transport.requests

    try:
        if _creds is None:
            _creds, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"])
        if not _creds.valid:
            _creds.refresh(google.auth.transport.requests.Request())
    except Exception as exc:
        raise RuntimeError(
            "No Google credentials for Cloud TTS. Run:\n"
            "  gcloud auth application-default login\n"
            "  gcloud auth application-default set-quota-project YOUR_PROJECT"
        ) from exc

    headers = {"Authorization": f"Bearer {_creds.token}"}
    if PROJECT:
        headers["x-goog-user-project"] = PROJECT
    return headers

# There is no en-SG voice in Cloud TTS -- only en-AU, en-GB, en-IN and en-US.
# So the Singaporean-ness lives in the *text* (see the Singlish register in
# agent.JIO) and we pick the least jarring accent to read it. en-AU is the
# provisional default; swap via .env after listening. `python voice.py --list`
# shows everything the project has.
def _voice(name: str) -> dict:
    """languageCode always comes from the name, or the API 400s on a mismatch."""
    return {"languageCode": name[:5], "name": name}


VOICES = {
    "caregiver": _voice(os.environ.get("VOICE_CAREGIVER") or "en-AU-Chirp3-HD-Charon"),
    "senior": _voice(os.environ.get("VOICE_SENIOR") or "en-US-Chirp3-HD-Aoede"),
}

# The senior hears a slower, warmer delivery. Unhurried, per spec section 4.
RATES = {"caregiver": 1.0, "senior": 0.88}


def synthesize(text: str, role: str) -> bytes:
    """Return OGG/Opus bytes ready for Telegram sendVoice."""
    payload = {
        "input": {"text": text},
        "voice": VOICES[role],
        "audioConfig": {"audioEncoding": "MP3", "speakingRate": RATES[role]},
    }
    resp = requests.post(ENDPOINT, headers=_auth(), json=payload, timeout=30)
    resp.raise_for_status()
    mp3 = base64.b64decode(resp.json()["audioContent"])
    return _to_ogg(mp3)


def _to_ogg(mp3: bytes) -> bytes:
    """Telegram voice notes must be OGG/Opus. ffmpeg, via stdin/stdout."""
    with tempfile.NamedTemporaryFile(suffix=".ogg") as out:
        proc = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", "pipe:0",
             "-c:a", "libopus", "-b:a", "32k", "-ar", "48000", "-ac", "1",
             "-f", "ogg", out.name],
            input=mp3, capture_output=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {proc.stderr.decode()[:400]}")
        return open(out.name, "rb").read()


def list_voices(prefix: str = "en-") -> None:
    resp = requests.get("https://texttospeech.googleapis.com/v1/voices",
                        headers=_auth(), timeout=30)
    resp.raise_for_status()
    for v in resp.json()["voices"]:
        if v["name"].startswith(prefix):
            print(f"{v['name']:<34} {v['ssmlGender']:<8} {','.join(v['languageCodes'])}")


if __name__ == "__main__":
    import sys
    if "--list" in sys.argv:
        list_voices()
    else:
        for role in ("caregiver", "senior"):
            data = synthesize("Morning. Found three things for you this week.", role)
            path = f"/tmp/jio_{role}.ogg"
            open(path, "wb").write(data)
            print(f"{role:<10} {VOICES[role]['name']:<22} {len(data):>6} bytes -> {path}")
