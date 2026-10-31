// Browser text-to-speech with a voice chosen PER LANGUAGE. Voices load asynchronously, so they are tracked in state.
// A language with no installed voice is reported, never spoken with a wrong-language voice (that reads Hindi as gibberish).
import { useEffect, useState } from "react";

const synth = typeof window !== "undefined" ? window.speechSynthesis : undefined;
const norm = (l) => String(l || "").toLowerCase().replace("_", "-"); // Android reports hi_IN, desktop hi-IN
export const speechSupported = !!synth;

const list = () => (synth?.getVoices?.() ?? []).map((v) => ({ v, lang: norm(v.lang) }));

export function useVoices() {
  const [voices, setVoices] = useState(list);
  useEffect(() => {
    if (!synth) return;
    const on = () => setVoices(list());
    synth.addEventListener?.("voiceschanged", on);
    on();
    return () => synth.removeEventListener?.("voiceschanged", on);
  }, []);
  return voices;
}

/** The best installed voice for a language code like "hi": exact Indian locale first, then any voice of that language. */
export function pickVoice(voices, lang) {
  const same = voices.filter((x) => x.lang === lang || x.lang.startsWith(`${lang}-`));
  return (same.find((x) => x.lang.endsWith("-in")) || same[0])?.v ?? null;
}

/** Returns "ok", "novoice" (nothing installed for this language) or "unsupported" (no speech API at all). */
export function say(text, lang, { rate = 1, voices, onEnd }) {
  if (!synth) return "unsupported";
  const voice = pickVoice(voices, lang);
  if (!voice && voices.length) return "novoice"; // an empty list may just mean the voices have not loaded yet: then try the default
  synth.cancel();
  const u = new SpeechSynthesisUtterance(text);
  if (voice) { u.voice = voice; u.lang = voice.lang; } else u.lang = lang;
  u.rate = rate;
  u.onend = u.onerror = () => onEnd?.();
  synth.speak(u);
  return "ok";
}

export const stopSpeech = () => synth?.cancel();
