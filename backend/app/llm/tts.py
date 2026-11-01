"""Natural-sounding read-aloud via Sarvam AI (Bulbul), which has neural voices for every Indian language we support.
Browsers on Linux only have eSpeak, which sounds robotic. Without SARVAM_API_KEY, or if Sarvam fails, the UI falls back
to the browser voice: this module only ever returns audio bytes or None, it never raises."""
import base64
import logging
import re
from collections import OrderedDict

import httpx

from app.core.config import get_settings

log = logging.getLogger("tts")
URL = "https://api.sarvam.ai/text-to-speech"
LANGS = {"en", "hi", "mr", "gu", "pa", "ta", "te", "kn", "bn", "ml", "od"}  # Sarvam codes are these + "-IN"
CHUNK = 1800  # bulbul:v3 takes up to 2500 chars per call; leave room
MAX_CHUNKS = 4  # a read-aloud answer, not a book: caps the credits one click can spend
_cache: OrderedDict[tuple, bytes] = OrderedDict()  # replaying the same answer must not spend credits again
CACHE_SIZE = 32


def available() -> bool:
    return bool(get_settings().sarvam_api_key)


def chunks(text: str) -> list[str]:
    """Split at sentence ends (including the Hindi danda) so no chunk breaks a sentence mid-way."""
    parts, cur = [], ""
    for sent in re.split(r"(?<=[.!?।॥])\s+", text.strip()):
        while len(sent) > CHUNK:  # one giant sentence: cut at a space
            cut = sent.rfind(" ", 0, CHUNK) if " " in sent[:CHUNK] else CHUNK
            parts.append(sent[:cut].strip())
            sent = sent[cut:].strip()
        if cur and len(cur) + 1 + len(sent) > CHUNK:
            parts.append(cur)
            cur = sent
        else:
            cur = f"{cur} {sent}".strip()
    if cur:
        parts.append(cur)
    return [p for p in parts if p][:MAX_CHUNKS]


def speak(text: str, lang: str, pace: float = 1.0) -> bytes | None:
    """MP3 bytes for the text in that language, or None (no key, unsupported language, or the service failed)."""
    s = get_settings()
    text = (text or "").strip()
    if not s.sarvam_api_key or lang not in LANGS or not text:
        return None
    pace = min(2.0, max(0.5, pace))
    key = (text, lang, pace)
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    body = {"language_code": f"{lang}-IN", "model": s.tts_model, "pace": pace, "output_audio_codec": "mp3"}
    if s.tts_speaker:
        body["speaker"] = s.tts_speaker
    audio = b""
    try:
        with httpx.Client(timeout=s.tts_timeout_s) as c:
            for part in chunks(text):
                r = c.post(URL, json={**body, "text": part}, headers={"api-subscription-key": s.sarvam_api_key})
                r.raise_for_status()
                audio += b"".join(base64.b64decode(a) for a in r.json().get("audios", []))  # MP3 frames join cleanly
    except Exception as e:
        log.warning("sarvam tts failed: %s", type(e).__name__)  # type only: never log the key or the farmer's text
        return None
    if not audio:
        return None
    _cache[key] = audio
    if len(_cache) > CACHE_SIZE:
        _cache.popitem(last=False)
    return audio
