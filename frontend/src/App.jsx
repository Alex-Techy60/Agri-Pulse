import { useEffect, useRef, useState } from "react";
import { chatStream, getDomain, getHealth, transcribe } from "./api.js";
import Trace from "./components/Trace.jsx";
import { Cards, Sources } from "./components/Cards.jsx";

const SESSION = crypto.randomUUID?.() ?? String(Date.now());
const loadProfile = () => { try { return JSON.parse(localStorage.getItem("profile") || "{}"); } catch { return {}; } };
const saveProfile = (p) => { try { localStorage.setItem("profile", JSON.stringify(p)); } catch { /* private mode */ } };

export default function App() {
  const [domain, setDomain] = useState(null);
  const [health, setHealth] = useState(null);
  const [lang, setLang] = useState("en");
  const [msgs, setMsgs] = useState([]);
  const [trace, setTrace] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [rec, setRec] = useState(false);
  const [speak, setSpeak] = useState(false);
  const [profile, setProfile] = useState(loadProfile);
  const recorder = useRef(null);
  const endRef = useRef(null);

  useEffect(() => {
    getDomain().then(setDomain).catch(() => setDomain({ title: "Backend unreachable", tagline: "Start it: make dev", suggested_prompts: [], languages: { en: "English" } }));
    getHealth().then(setHealth).catch(() => {});
  }, []);
  useEffect(() => endRef.current?.scrollIntoView({ behavior: "smooth" }), [msgs, trace]);

  async function send(text) {
    text = (text ?? input).trim();
    if (!text || busy) return;
    setInput("");
    setBusy(true);
    setTrace([]);
    setMsgs((m) => [...m, { role: "user", text }]);
    try {
      const r = await chatStream({ message: text, sessionId: SESSION, language: lang, profile: { place: profile.place, crop: profile.crop } }, (s) => setTrace((t) => [...t, s]));
      setMsgs((m) => [...m, { role: "bot", text: r.answer, meta: r }]);
      if (r.profile?.place) { const np = { ...profile, place: profile.place || r.profile.place }; setProfile(np); saveProfile(np); }
      if (speak && "speechSynthesis" in window) {
        const u = new SpeechSynthesisUtterance(r.answer);
        u.lang = lang;
        speechSynthesis.speak(u);
      }
    } catch (e) {
      setMsgs((m) => [...m, { role: "bot", text: "Something went wrong reaching the server. Please try again.", meta: { degraded: true } }]);
    } finally {
      setBusy(false);
    }
  }

  async function toggleMic() {
    if (rec) return recorder.current?.stop();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      const chunks = [];
      mr.ondataavailable = (e) => chunks.push(e.data);
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setRec(false);
        const out = await transcribe(new Blob(chunks, { type: "audio/webm" }), lang).catch(() => ({ text: "" }));
        if (out.text) send(out.text);
      };
      recorder.current = mr;
      mr.start();
      setRec(true);
    } catch {
      alert("Microphone not available");
    }
  }

  if (!domain) return null;
  return (
    <div className="app">
      <header>
        <div>
          <h1>{domain.title}</h1>
          <p>{domain.tagline}</p>
        </div>
        <div className="controls">
          <select value={lang} onChange={(e) => setLang(e.target.value)} aria-label="Language">
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
              {domain.suggested_prompts.map((p) => (
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
        <button type="button" className={rec ? "mic on" : "mic"} onClick={toggleMic} aria-label="Voice input">{rec ? "■" : "🎤"}</button>
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask anything…" disabled={busy} />
        <button type="submit" disabled={busy || !input.trim()}>Send</button>
      </form>
    </div>
  );
}
