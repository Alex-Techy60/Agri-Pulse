// All network access in one file. Components never call fetch directly.
const j = (r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)));

// Saved chats have no login: this browser keeps a long random secret and sends it with chat requests; the server stores only its hash.
// If localStorage is blocked (private mode) the secret lives for this page load only, so history works but is not kept across visits.
const randomHex = (bytes) => Array.from(crypto.getRandomValues(new Uint8Array(bytes)), (b) => b.toString(16).padStart(2, "0")).join("");
let memoryId = null;
const clientId = () => {
  try {
    let id = localStorage.getItem("clientId");
    if (!id) { id = randomHex(24); localStorage.setItem("clientId", id); }
    return id;
  } catch {
    return (memoryId ??= randomHex(24));
  }
};
const who = (extra = {}) => ({ "X-Client-Id": clientId(), ...extra });
export const newChatId = () => randomHex(16);

export const getDomain = () => fetch("/api/domain").then(j);
export const getHealth = () => fetch("/api/health").then(j);

const CHAT_TIMEOUT_MS = 90_000; // the server has its own time budget; this only stops a hung connection from spinning forever

/** Streams pipeline events. onTrace(step) per agent step; resolves with the final result.
 *  Rejects with an Error carrying one of: retryAfter (429), timeout, offline. */
export async function chatStream({ message, sessionId, language, imageB64, profile, signal }, onTrace) {
  if (navigator.onLine === false) throw Object.assign(new Error("offline"), { offline: true });
  const ctl = new AbortController();
  const onStop = () => ctl.abort();
  signal?.addEventListener("abort", onStop);
  const stopped = () => signal?.aborted === true; // the person pressed Stop: not a timeout
  const timer = setTimeout(() => ctl.abort(), CHAT_TIMEOUT_MS);
  try {
    const res = await fetch("/api/chat/stream", {
      method: "POST",
      headers: who({ "Content-Type": "application/json" }),
      body: JSON.stringify({ message, session_id: sessionId, language, image_b64: imageB64, profile }),
      signal: ctl.signal,
    });
    if (res.status === 429) throw Object.assign(new Error("rate limited"), { retryAfter: Number(res.headers.get("Retry-After")) || 60 });
    if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    let final = null;
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const parts = buf.split("\n\n");
      buf = parts.pop();
      for (const p of parts) {
        if (!p.startsWith("data: ")) continue;
        let ev;
        try { ev = JSON.parse(p.slice(6)); } catch { continue; } // one garbled event must not lose the answer
        if (ev.type === "trace" && ev.step) onTrace(ev.step);
        else if (ev.type === "final") final = ev.result;
      }
    }
    if (!final) throw new Error("stream ended without a result");
    return final;
  } catch (e) {
    if (stopped()) throw Object.assign(new Error("stopped"), { stopped: true });
    if (ctl.signal.aborted) throw Object.assign(new Error("timeout"), { timeout: true });
    if (navigator.onLine === false) throw Object.assign(new Error("offline"), { offline: true });
    throw e;
  } finally {
    signal?.removeEventListener("abort", onStop);
    clearTimeout(timer);
  }
}

export async function transcribe(blob, language, ext = "webm") {
  const fd = new FormData();
  fd.append("file", blob, `audio.${ext}`); // the extension tells the speech model which container this is
  if (language) fd.append("language", language);
  return fetch("/api/voice/transcribe", { method: "POST", body: fd }).then(j);
}

/** Natural read-aloud audio from the server, or null (no key / service down: the caller uses the browser voice). */
export async function speechAudio(text, language, pace, signal) {
  try {
    const r = await fetch("/api/voice/speak", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, language, pace }), signal });
    return r.ok ? await r.blob() : null;
  } catch {
    return null;
  }
}

export const liveCheck = (place, crop) => fetch(`/api/live-check?place=${encodeURIComponent(place)}&crop=${encodeURIComponent(crop)}`).then(j);
export const locate = (lat, lon) => fetch(`/api/locate?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}`).then(j);

export const listChats = () => fetch("/api/chats", { headers: who() }).then(j).then((d) => d.chats);
export const getChat = (id) => fetch(`/api/chats/${encodeURIComponent(id)}`, { headers: who() }).then(j);
export const deleteChat = (id) => fetch(`/api/chats/${encodeURIComponent(id)}`, { method: "DELETE", headers: who() }).then(j);

/** Place suggestions while typing: Open-Meteo's keyless geocoder, the same one the server uses, so a suggestion is a place the server can resolve. */
export async function suggestPlaces(q, signal) {
  const r = await fetch(`https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(q)}&count=6&language=en&format=json&countryCode=IN`, { signal });
  if (!r.ok) return [];
  const d = await r.json();
  return [...new Set((d.results || []).map((p) => [p.name, p.admin1].filter(Boolean).join(", ")))];
}

/** Thumbs up/down on one saved answer; value null clears it. Resolves false if it could not be saved (feedback is a convenience). */
export const sendFeedback = (messageId, value) =>
  fetch("/api/feedback", { method: "PUT", headers: who({ "Content-Type": "application/json" }), body: JSON.stringify({ message_id: messageId, value }) }).then((r) => r.ok).catch(() => false);

// --- Sign in with Google (optional: the server says whether it is configured) ---------------------------------------------------
// The browser gets an ID token from Google; the server verifies it and sets an HttpOnly cookie, so no token is ever kept in JS.
export const getAuthConfig = () => fetch("/api/auth/config").then(j);
export const getMe = () => fetch("/api/auth/me").then(j).then((d) => d.user);
export const signInWithGoogle = (credential) =>
  fetch("/api/auth/google", { method: "POST", headers: who({ "Content-Type": "application/json" }), body: JSON.stringify({ credential }) })
    .then((r) => (r.ok ? r.json() : Promise.reject(Object.assign(new Error(`HTTP ${r.status}`), { status: r.status }))))
    .then((d) => d.user);
export const signOut = () => fetch("/api/auth/logout", { method: "POST" }).then((r) => r.ok).catch(() => false);

// Settings (language, profile, read-aloud, speed) follow the person: saved on the server, localStorage stays as the instant/offline copy.
export const getSettings = () => fetch("/api/settings", { headers: who() }).then(j).then((d) => d.settings);
export const saveSettings = (settings) =>
  fetch("/api/settings", { method: "PUT", headers: who({ "Content-Type": "application/json" }), body: JSON.stringify(settings) }).then((r) => r.ok).catch(() => false);
