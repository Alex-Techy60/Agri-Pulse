// Browser text-to-speech with a voice chosen PER LANGUAGE. Voices load asynchronously, so they are tracked in state.
// A language with no installed voice is reported, never spoken with a wrong-language voice (that reads Hindi as gibberish).
import { useEffect, useState } from "react";
import { speechAudio } from "./api.js";

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

// Neural/cloud voices sound natural; eSpeak (the Linux default) sounds robotic, so it is only a last resort.
function quality({ v, lang }) {
  const name = String(v.name || "").toLowerCase();
  let s = 0;
  if (/natural|neural|online|google|wavenet|enhanced|premium/.test(name)) s += 4;
  if (v.localService === false) s += 2; // network voices are the neural ones on Chrome and Edge
  if (lang.endsWith("-in")) s += 1;
  if (/espeak|mbrola|festival|pico/.test(name)) s -= 10;
  return s;
}

/** The best installed voice for a language code like "hi": most natural first, Indian locale breaks ties. */
export function pickVoice(voices, lang) {
  const same = voices.filter((x) => x.lang === lang || x.lang.startsWith(`${lang}-`));
  return [...same].sort((a, b) => quality(b) - quality(a))[0]?.v ?? null;
}

/** Returns "ok", "novoice" (nothing installed for this language) or "unsupported" (no speech API at all). */
function browserSay(text, lang, { rate = 1, voices, onEnd }) {
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

let current = null; // the natural-voice playback in progress: { ctrl, audio, url }

// Each server voice request takes ~3-4 s whatever its length, so a long answer is cut after its first sentence or two:
// that short part plays while the rest is still being generated (both are requested at once).
function firstPart(text) {
  if (text.length <= 250) return [text];
  for (const m of text.matchAll(/[.!?।॥](\s|$)/g)) {
    if (m.index >= 60 && m.index <= 300) return [text.slice(0, m.index + 1).trim(), text.slice(m.index + 1).trim()].filter(Boolean);
    if (m.index > 300) break;
  }
  return [text];
}

/** Speaks text. With `natural` (the server has a neural voice), plays that and falls back to the browser voice if it fails. */
export function say(text, lang, opts) {
  stopSpeech();
  if (!opts.natural) return browserSay(text, lang, opts);
  const me = { ctrl: new AbortController() };
  current = me;
  const parts = firstPart(text);
  const audios = parts.map((p) => speechAudio(p, lang, opts.rate ?? 1, me.ctrl.signal));
  const drop = () => { me.audio?.pause(); if (me.url) URL.revokeObjectURL(me.url); };
  const fallback = (rest) => { // the part not yet played goes to the browser voice, so nothing is skipped
    if (current !== me) return; // stopped or replaced meanwhile
    current = null;
    drop();
    if (browserSay(rest, lang, opts) !== "ok") opts.onEnd?.();
  };
  const play = async (i) => {
    const blob = await audios[i];
    if (current !== me) return;
    const rest = parts.slice(i).join(" ");
    if (!blob) return fallback(rest);
    drop();
    me.url = URL.createObjectURL(blob);
    me.audio = new Audio(me.url);
    me.audio.onended = () => {
      if (current !== me) return;
      if (i + 1 < parts.length) return play(i + 1);
      stopSpeech();
      opts.onEnd?.();
    };
    me.audio.onerror = () => fallback(rest);
    me.audio.play().catch(() => fallback(rest)); // autoplay blocked: the browser voice may still be allowed
  };
  play(0);
  return "ok";
}

export function stopSpeech() {
  const c = current;
  current = null;
  if (c) {
    c.ctrl.abort();
    c.audio?.pause();
    if (c.url) URL.revokeObjectURL(c.url);
  }
  synth?.cancel();
}
