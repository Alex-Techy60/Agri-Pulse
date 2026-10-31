"""One LLM client for every provider that speaks the OpenAI chat format.

Degradation ladder (the demo must NEVER crash on stage):
    primary provider -> fallback provider -> offline answer (caller-supplied)

`LLMResult.degraded` tells the UI which rung answered so it can show a badge.
"""
from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
from dataclasses import dataclass, field

import httpx

from app.core.config import Settings, get_settings

log = logging.getLogger("llm")

MIN_REASONING_TOKENS = 400
_DROPPED = (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadError)  # not timeouts: retrying those would double a 25 s wait


@dataclass
class LLMResult:
    text: str
    provider: str  # "primary" | "fallback" | "offline"
    model: str = ""
    ms: int = 0
    degraded: bool = False
    error: str = ""
    raw: dict = field(default_factory=dict)


class LLMClient:
    def __init__(self, settings: Settings | None = None, transport: httpx.BaseTransport | None = None):
        self.s = settings or get_settings()
        self._http = httpx.Client(timeout=self.s.llm_timeout_s, transport=transport)

    # ------------------------------------------------------------------ chat
    def chat(
        self,
        messages: list[dict],
        *,
        fast: bool = False,
        json_mode: bool = False,
        temperature: float | None = None,
        max_tokens: int = 700,
        offline: str = "I'm having trouble reaching my AI service right now. Please try again in a moment.",
        primary_only: bool = False,  # optional steps: a safe default beats waiting on the slow fallback
    ) -> LLMResult:
        s = self.s
        providers = []
        if s.llm_api_key:
            providers.append(("primary", s.llm_base_url, s.llm_api_key, s.llm_fast_model if fast else s.llm_model))
            if not fast and s.llm_fast_model != s.llm_model:
                # Groq limits tokens per model: when the big model's daily quota is spent, the small one
                # (own quota, ~1 s) still answers, instead of the 20-35 s free fallback.
                providers.append(("reserve", s.llm_base_url, s.llm_api_key, s.llm_fast_model))
        if s.fallback_api_key and s.fallback_base_url and s.fallback_model and not primary_only:
            providers.append(("fallback", s.fallback_base_url, s.fallback_api_key, s.fallback_model))

        last_err = "no provider configured (set LLM_API_KEY)"
        for name, base, key, model in providers:
            t0 = time.time()
            try:
                body: dict = {
                    "model": model,
                    "messages": messages,
                    "temperature": s.llm_temperature if temperature is None else temperature,
                    "max_tokens": max_tokens,
                }
                if model.startswith("openai/gpt-oss"):  # reasoning models: reasoning tokens count against max_tokens
                    body["reasoning_effort"] = "low"
                if name == "fallback" or model.startswith("openai/gpt-oss"):
                    # the free fallback reasons too: at the router's 80 tokens it cut JSON off, losing Marathi detection
                    body["max_tokens"] = max(max_tokens, MIN_REASONING_TOKENS)
                if json_mode:
                    body["response_format"] = {"type": "json_object"}
                def send():
                    url = f"{base.rstrip('/')}/chat/completions"
                    try:
                        return self._http.post(url, headers={"Authorization": f"Bearer {key}"}, json=body)
                    except _DROPPED:  # a connection the provider dropped is not an outage: retry before the slow fallback
                        time.sleep(0.5)
                        return self._http.post(url, headers={"Authorization": f"Bearer {key}"}, json=body)

                r = send()
                wait = _short_retry_after(r) if (r.status_code == 429 and name == "primary") else None
                if wait is not None:  # free-tier burst limit: waiting a moment beats dropping to a slower fallback
                    time.sleep(wait)
                    r = send()
                r.raise_for_status()
                data = r.json()
                text = data["choices"][0]["message"]["content"] or ""
                return LLMResult(
                    text=strip_think(text),
                    provider=name,
                    model=model,
                    ms=int((time.time() - t0) * 1000),
                    degraded=name not in ("primary", "reserve"),  # reserve is the same provider; the trace names the model
                    raw=data,
                )
            except Exception as e:  # network, 429, 5xx, bad JSON...
                last_err = f"{name}: {type(e).__name__}: {e}"
                log.warning("LLM %s failed: %s", name, last_err)

        return LLMResult(text=offline, provider="offline", degraded=True, error=last_err)

    def chat_json(self, messages: list[dict], **kw) -> tuple[dict | None, LLMResult]:
        res = self.chat(messages, json_mode=True, **kw)
        return parse_json(res.text), res

    # ---------------------------------------------------------------- vision
    def vision(self, image_b64: str, question: str, mime: str = "image/jpeg") -> LLMResult:
        msgs = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": question},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
                ],
            }
        ]
        s = self.s
        if not s.llm_api_key:
            return LLMResult(text="", provider="offline", degraded=True, error="no LLM_API_KEY")
        t0 = time.time()
        try:
            r = self._http.post(
                f"{s.llm_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {s.llm_api_key}"},
                json={"model": s.llm_vision_model, "messages": msgs, "max_tokens": 500},
            )
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"] or ""
            return LLMResult(text=text, provider="primary", model=s.llm_vision_model, ms=int((time.time() - t0) * 1000))
        except Exception as e:
            return LLMResult(text="", provider="offline", degraded=True, error=f"{type(e).__name__}: {e}")

    # ----------------------------------------------------------------- audio
    def transcribe(self, audio: bytes, filename: str = "audio.webm", language: str | None = None, prompt: str | None = None) -> str:
        """Speech -> text with Whisper. verbose_json gives per-segment silence scores: on silence or room noise Whisper
        otherwise invents phrases such as "Thank you.", which would be sent on as the farmer's question."""
        s = self.s
        if not s.llm_api_key:
            return ""
        data = {"model": s.stt_model, "response_format": "verbose_json", "temperature": "0"}
        if language:
            data["language"] = language
        if prompt:
            data["prompt"] = prompt  # vocabulary hint (crop and market words in the right script); it does not steer the content
        for attempt in (1, 2):
            try:
                r = self._http.post(
                    f"{s.llm_base_url.rstrip('/')}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {s.llm_api_key}"},
                    data=data,
                    files={"file": (filename, audio)},
                )
                break
            except _DROPPED:  # a connection the provider dropped: one retry, as for chat
                if attempt == 2:
                    raise
                time.sleep(0.5)
        r.raise_for_status()
        return speech_text(r.json())


# --------------------------------------------------------------------- utils
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)

# Whisper's own silence test: a segment is not speech when it is probably silent AND the model is unsure of its own words.
# Groq's whisper-large-v3-turbo reports no_speech_prob = 0 for everything (checked 31 Oct 2026: pure silence came back as
# "Thank you." with probability 0 and avg_logprob -0.29), so that test cannot be relied on there. The phrase list below is
# what actually catches it; the browser also skips the upload when the microphone level never rose.
NO_SPEECH_P, LOW_LOGPROB = 0.6, -1.0
MAX_COMPRESSION = 2.4  # Whisper's own decoding-failure test: text that compresses this well is looping on one phrase
# What Whisper writes for silence or room noise (its training data was subtitled video). Dropping them costs nothing: none is a farm question.
HALLUCINATIONS = {"thank you", "thanks", "thank you very much", "thanks for watching", "thank you for watching", "please subscribe", "bye", "goodbye", "you",
                  "okay", "ok", "oh", "uh", "um", "subtitles by the amara.org community", "धन्यवाद", "शुक्रिया", "देखने के लिए धन्यवाद", "आभारी आहे"}


def _plain(text: str) -> str:
    """Lower-cased text without punctuation or symbols. By Unicode category, not a regex: Python's \\w drops Devanagari vowel signs and virama."""
    return " ".join("".join(c for c in text.lower() if unicodedata.category(c)[0] not in "PS").split())


def _is_hallucination(text: str) -> bool:
    plain = _plain(text)
    return not any(c.isalnum() for c in text) or plain in HALLUCINATIONS  # no letters or digits at all, or a stock phrase


def speech_text(result: dict) -> str:
    """Text of the segments that are speech. Falls back to the plain text when the provider sent no segment scores."""
    if not isinstance(result, dict):
        return ""
    segs = result.get("segments")
    if segs:
        kept = [str(g.get("text", "")).strip() for g in segs
                if not (g.get("no_speech_prob", 0) > NO_SPEECH_P and g.get("avg_logprob", 0) < LOW_LOGPROB) and g.get("compression_ratio", 0) <= MAX_COMPRESSION]
        text = " ".join(t for t in kept if t).strip()
    else:
        text = str(result.get("text", "")).strip()
    return "" if _is_hallucination(text) else text


RETRY_AFTER_MAX_S = 4.0


def _short_retry_after(r) -> float | None:
    """Seconds to wait if the 429 says the limit clears quickly; None if it is long or unspecified."""
    try:
        v = float(r.headers.get("retry-after", ""))
    except (TypeError, ValueError):
        return None
    return v if 0 <= v <= RETRY_AFTER_MAX_S else None


def strip_think(text: str) -> str:
    """Reasoning models (qwen3, deepseek-r1) leak <think> blocks. Remove them."""
    return _THINK.sub("", text).strip()


def parse_json(text: str) -> dict | None:
    """Tolerant JSON parse: handles ```json fences and chatter around the object."""
    if not text:
        return None
    t = text.strip()
    t = re.sub(r"^```(?:json)?|```$", "", t, flags=re.MULTILINE).strip()
    try:
        out = json.loads(t)
        return out if isinstance(out, dict) else None
    except Exception:
        m = re.search(r"\{.*\}", t, re.DOTALL)
        if m:
            try:
                out = json.loads(m.group(0))
                return out if isinstance(out, dict) else None
            except Exception:
                return None
    return None


_client: LLMClient | None = None


def get_llm() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
