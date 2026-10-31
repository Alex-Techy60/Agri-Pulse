// All network access in one file. Components never call fetch directly.
const j = (r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)));

export const getDomain = () => fetch("/api/domain").then(j);
export const getHealth = () => fetch("/api/health").then(j);

/** Streams pipeline events. onTrace(step) per agent step; resolves with the final result. */
export async function chatStream({ message, sessionId, language, imageB64, profile }, onTrace) {
  const res = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId, language, image_b64: imageB64, profile }),
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
      const ev = JSON.parse(p.slice(6));
      if (ev.type === "trace") onTrace(ev.step);
      else if (ev.type === "final") final = ev.result;
    }
  }
  if (!final) throw new Error("stream ended without a result");
  return final;
}

export async function transcribe(blob, language, ext = "webm") {
  const fd = new FormData();
  fd.append("file", blob, `audio.${ext}`); // the extension tells the speech model which container this is
  if (language) fd.append("language", language);
  return fetch("/api/voice/transcribe", { method: "POST", body: fd }).then(j);
}

export const liveCheck = (place, crop) => fetch(`/api/live-check?place=${encodeURIComponent(place)}&crop=${encodeURIComponent(crop)}`).then(j);
export const locate = (lat, lon) => fetch(`/api/locate?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}`).then(j);
