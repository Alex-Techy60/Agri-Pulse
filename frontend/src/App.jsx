import { useEffect, useRef, useState } from "react";
import { chatStream, getDomain, getHealth, transcribe } from "./api.js";
import Trace from "./components/Trace.jsx";
import { Cards, Sources } from "./components/Cards.jsx";

const SESSION = crypto.randomUUID?.() ?? String(Date.now());
const loadProfile = () => { try { return JSON.parse(localStorage.getItem("profile") || "{}"); } catch { return {}; } };
const saveProfile = (p) => { try { localStorage.setItem("profile", JSON.stringify(p)); } catch { /* private mode */ } };
const loadLang = () => { try { return localStorage.getItem("lang") || "en"; } catch { return "en"; } };
const saveLang = (l) => { try { localStorage.setItem("lang", l); } catch { /* private mode */ } };
const MAX_PHOTO_BYTES = 5 * 1024 * 1024; // the API caps image_b64 at about 5 MB
// The few messages written by the UI itself (everything else comes from the API in the farmer's language).
const UI_TEXT = {
  en: { down: "Something went wrong reaching the server. Please try again.", wait: (n) => `Too many questions right now. Please wait ${n} seconds and try again.`, deaf: "I could not hear that clearly. Please try again, or type your question.", nomic: "The microphone is not available. Allow microphone access (the page needs https), or type your question." },
  hi: { down: "सर्वर तक पहुँचने में दिक्कत हुई। कृपया फिर से कोशिश करें।", wait: (n) => `अभी बहुत सवाल आ गए हैं। कृपया ${n} सेकंड रुककर फिर कोशिश करें।`, deaf: "मैं साफ़ सुन नहीं पाया। कृपया फिर से बोलें या सवाल लिखें।", nomic: "माइक्रोफ़ोन उपलब्ध नहीं है। माइक्रोफ़ोन की अनुमति दें (पेज https पर होना चाहिए) या सवाल लिखें।" },
  mr: { down: "सर्व्हरशी संपर्क होऊ शकला नाही. कृपया पुन्हा प्रयत्न करा.", wait: (n) => `सध्या खूप प्रश्न आले आहेत. कृपया ${n} सेकंद थांबून पुन्हा प्रयत्न करा.`, deaf: "मला नीट ऐकू आले नाही. कृपया पुन्हा बोला किंवा प्रश्न लिहा.", nomic: "मायक्रोफोन उपलब्ध नाही. मायक्रोफोनची परवानगी द्या (पेज https वर असावे) किंवा प्रश्न लिहा." },
};
const uiText = (lang) => UI_TEXT[lang] || UI_TEXT.en;
// Voice: Chrome/Firefox record webm, Safari/iPhone records mp4, so the recorder picks what the browser supports and the file name follows the real type.
const MAX_RECORD_MS = 60_000; // a forgotten mic must not grow past the server's 5 MB limit
const MIN_AUDIO_BYTES = 2000; // below this there is no speech worth sending
const AUDIO_TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
const pickAudioType = () => AUDIO_TYPES.find((t) => window.MediaRecorder?.isTypeSupported?.(t)) || "";
const SPEECH_RMS = 0.015; // microphone level (0-1) that counts as sound: a quiet room stays below, speech is well above
const MIN_SPEECH_FRAMES = 3; // 100 ms each: at least 0.3 s of sound, or nothing is uploaded
// Level meter: counts 100 ms frames that were loud enough. Returns null where the browser has no analyser (then the clip is sent anyway).
function startMeter(stream) {
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    const ctx = new Ctx();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    ctx.createMediaStreamSource(stream).connect(analyser);
    const buf = new Float32Array(analyser.fftSize);
    const m = { frames: 0, stop: () => { clearInterval(timer); ctx.close().catch(() => {}); } };
    const timer = setInterval(() => {
      analyser.getFloatTimeDomainData(buf);
      let sum = 0;
      for (const v of buf) sum += v * v;
      if (Math.sqrt(sum / buf.length) > SPEECH_RMS) m.frames += 1;
    }, 100);
    return m;
  } catch {
    return null;
  }
}
const audioExt = (type) => (/mp4|m4a|aac/.test(type) ? "m4a" : /ogg/.test(type) ? "ogg" : "webm");
const PHOTO_PROMPT = "Please check this crop photo.";
const readB64 = (file) => new Promise((ok, bad) => {
  const fr = new FileReader();
  fr.onload = () => ok(String(fr.result).split(",")[1]); // the API wants raw base64, no data: prefix
  fr.onerror = bad;
  fr.readAsDataURL(file);
});

export default function App() {
  const [domain, setDomain] = useState(null);
  const [health, setHealth] = useState(null);
  const [lang, setLang] = useState(loadLang);
  const [msgs, setMsgs] = useState([]);
  const [trace, setTrace] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [rec, setRec] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [speak, setSpeak] = useState(false);
  const [profile, setProfile] = useState(loadProfile);
  const [photo, setPhoto] = useState(null);
  const recorder = useRef(null);
  const busyRef = useRef(false);
  const endRef = useRef(null);

  useEffect(() => {
    getDomain().then(setDomain).catch(() => setDomain({ title: "Backend unreachable", tagline: "Start it: make dev", suggested_prompts: [], languages: { en: "English" } }));
    getHealth().then(setHealth).catch(() => {});
  }, []);
  useEffect(() => endRef.current?.scrollIntoView({ behavior: "smooth" }), [msgs, trace]);

  async function send(text) {
    text = (text ?? input).trim() || (photo ? PHOTO_PROMPT : "");
    if (!text || busy) return;
    const image = photo;
    setInput("");
    setPhoto(null);
    setBusy(true);
    setTrace([]);
    setMsgs((m) => [...m, { role: "user", text: image ? `📷 ${image.name}\n${text}` : text }]);
    try {
      const imageB64 = image ? await readB64(image) : undefined;
      const r = await chatStream({ message: text, sessionId: SESSION, language: lang, imageB64, profile: { place: profile.place, crop: profile.crop } }, (s) => setTrace((t) => [...t, s]));
      setMsgs((m) => [...m, { role: "bot", text: r.answer, meta: r }]);
      if (r.profile?.place) { const np = { ...profile, place: profile.place || r.profile.place }; setProfile(np); saveProfile(np); }
      if (speak && "speechSynthesis" in window) {
        const u = new SpeechSynthesisUtterance(r.answer);
        u.lang = lang;
        speechSynthesis.speak(u);
      }
    } catch (e) {
      const text = e.retryAfter ? uiText(lang).wait(e.retryAfter) : uiText(lang).down;
      setMsgs((m) => [...m, { role: "bot", text, meta: { degraded: true } }]);
    } finally {
      setBusy(false);
    }
  }

  function pickPhoto(e) {
    const f = e.target.files?.[0];
    e.target.value = ""; // lets the same file be picked again
    if (!f) return;
    if (f.size > MAX_PHOTO_BYTES) return alert("Photo is too large. Please use one under 5 MB.");
    setPhoto(f);
  }

  const botSay = (text) => setMsgs((m) => [...m, { role: "bot", text, meta: { degraded: true } }]);

  async function toggleMic() {
    if (transcribing) return;
    if (rec) return recorder.current?.stop();
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      return botSay(uiText(lang).nomic); // denied, no microphone, or an http page (browsers only allow the mic on https and localhost)
    }
    const type = pickAudioType();
    let mr;
    try {
      mr = type ? new MediaRecorder(stream, { mimeType: type }) : new MediaRecorder(stream);
    } catch {
      stream.getTracks().forEach((t) => t.stop());
      return botSay(uiText(lang).nomic);
    }
    const chunks = [];
    const meter = startMeter(stream);
    const stopTimer = setTimeout(() => mr.state === "recording" && mr.stop(), MAX_RECORD_MS);
    mr.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    mr.onstop = async () => {
      clearTimeout(stopTimer);
      meter?.stop();
      stream.getTracks().forEach((t) => t.stop());
      setRec(false);
      const realType = mr.mimeType || type || "audio/webm";
      const blob = new Blob(chunks, { type: realType });
      if (blob.size < MIN_AUDIO_BYTES || (meter && meter.frames < MIN_SPEECH_FRAMES)) return botSay(uiText(lang).deaf); // nothing was said: do not upload silence
      setTranscribing(true);
      const out = await transcribe(blob, lang, audioExt(realType)).catch(() => ({ text: "" }));
      setTranscribing(false);
      const heard = (out.text || "").trim();
      if (!heard) return botSay(uiText(lang).deaf);
      if (busyRef.current) setInput(heard); // an answer is still being written: keep what was said instead of dropping it
      else send(heard);
    };
    recorder.current = mr;
    mr.start();
    setRec(true);
  }

  busyRef.current = busy;
  if (!domain) return null;
  return (
    <div className="app">
      <header>
        <div>
          <h1>{domain.title}</h1>
          <p>{domain.tagline}</p>
        </div>
        <div className="controls">
          <select value={lang} onChange={(e) => { setLang(e.target.value); saveLang(e.target.value); }} aria-label="Language">
            {Object.entries(domain.languages).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
          <label className="chk"><input type="checkbox" checked={speak} onChange={(e) => setSpeak(e.target.checked)} /> Read aloud</label>
          {health && <span className={`pill ${health.llm_configured ? "ok" : "warn"}`}>{health.llm_configured ? "AI online" : "AI offline (live data only)"}</span>}
        </div>
      </header>

      <div className="profile">
        {(domain.profile_fields || []).map((f) => (
          <label key={f.key}>
            <span>{f.label}</span>
            <input
              list={f.options ? `opt-${f.key}` : undefined}
              value={profile[f.key] || ""}
              placeholder={f.placeholder}
              onChange={(e) => { const np = { ...profile, [f.key]: e.target.value }; setProfile(np); saveProfile(np); }}
            />
            {f.options && <datalist id={`opt-${f.key}`}>{f.options.map((o) => <option key={o} value={o} />)}</datalist>}
          </label>
        ))}
      </div>

      <main>
        <section className="chat">
          {msgs.length === 0 && (
            <div className="suggest">
              {(domain.suggested_prompts_by_lang?.[lang] || domain.suggested_prompts).map((p) => (
                <button key={p} onClick={() => send(p)}>{p}</button>
              ))}
            </div>
          )}
          {msgs.map((m, i) => (
            <div key={i} className={`msg ${m.role}`}>
              <p>{m.text}</p>
              <Cards cards={m.meta?.cards} />
              <Sources list={m.meta?.live_sources} />
              {m.meta?.sources?.length > 0 && <small>Documents: {m.meta.sources.join(", ")}</small>}
              {m.meta?.degraded && <small className="warn"> · degraded mode</small>}
            </div>
          ))}
          {busy && <div className="msg bot typing">thinking…</div>}
          <div ref={endRef} />
        </section>

        <aside>
          <h2>Agent trace</h2>
          <Trace steps={trace} />
        </aside>
      </main>

      <form className="composer" onSubmit={(e) => { e.preventDefault(); send(); }}>
        <button type="button" className={rec ? "mic on" : "mic"} onClick={toggleMic} disabled={transcribing} aria-label="Voice input">{rec ? "■" : transcribing ? "…" : "🎤"}</button>
        <label className={photo ? "mic photo on" : "mic photo"} title={photo ? photo.name : "Add a crop photo"}>
          📷<input type="file" accept="image/*" onChange={pickPhoto} disabled={busy} aria-label="Add a crop photo" />
        </label>
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder={photo ? `Photo ready: ${photo.name}` : "Ask anything…"} disabled={busy} />
        <button type="submit" disabled={busy || (!input.trim() && !photo)}>Send</button>
      </form>
    </div>
  );
}
