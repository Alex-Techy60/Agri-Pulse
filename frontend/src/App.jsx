import { useEffect, useRef, useState } from "react";
import { chatStream, deleteChat, getChat, getDomain, getHealth, listChats, locate, newChatId, sendFeedback, transcribe, getAuthConfig, getMe, getSettings, saveSettings } from "./api.js";
import MessageList from "./components/MessageList.jsx";
import Composer from "./components/Composer.jsx";
import History from "./components/History.jsx";
import Profile from "./components/Profile.jsx";
import SignIn from "./components/SignIn.jsx";
import AnimatedBadge from "./components/AnimatedBadge.jsx";
import { prepareImage } from "./image.js";
import { say, stopSpeech, useVoices } from "./speech.js";
import { uiText } from "./i18n.js";

// The open chat survives a page reload; its messages come back from the server.
const loadChatId = () => { try { return localStorage.getItem("chatId") || newChatId(); } catch { return newChatId(); } };
const saveChatId = (id) => { try { localStorage.setItem("chatId", id); } catch { /* private mode */ } };
const loadProfile = () => { try { return JSON.parse(localStorage.getItem("profile") || "{}"); } catch { return {}; } };
const saveProfile = (p) => { try { localStorage.setItem("profile", JSON.stringify(p)); } catch { /* private mode */ } };
// localStorage is shared by every app on this origin and can hold anything (we have seen the value "\"en\"" with quote marks).
// A bad tag makes toLocaleString throw and blanks the whole page, so only a plain language code is accepted.
const cleanLang = (v) => { const l = String(v ?? "").replace(/^["']+|["']+$/g, "").trim(); return /^[a-z]{2,3}$/.test(l) ? l : "en"; };
const loadLang = () => { try { return cleanLang(localStorage.getItem("lang")); } catch { return "en"; } };
const saveLang = (l) => { try { localStorage.setItem("lang", l); } catch { /* private mode */ } };
const stamp = () => new Date().toISOString();
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
const loadRate = () => { try { return Number(localStorage.getItem("rate")) || 1; } catch { return 1; } };
const saveRate = (r) => { try { localStorage.setItem("rate", String(r)); } catch { /* private mode */ } };

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
  const [locating, setLocating] = useState(false);
  const [speak, setSpeak] = useState(false);
  const [profile, setProfile] = useState(loadProfile);
  const [photo, setPhoto] = useState(null); // {b64, previewUrl, name}: already shrunk to 1024 px
  const [slow, setSlow] = useState(false);
  const [aiDown, setAiDown] = useState(false); // "key configured" is not "AI answering": the badge follows the last real answer
  const [notice, setNotice] = useState("");
  const [rate, setRate] = useState(loadRate);
  const voices = useVoices();
  const [chatId, setChatId] = useState(loadChatId);
  const [chats, setChats] = useState([]);
  const [drawer, setDrawer] = useState(false);
  const [authCfg, setAuthCfg] = useState({ enabled: false, client_id: "" });
  const [user, setUser] = useState(null);
  const opened = useRef(0); // the latest chat the person asked to open; a slow earlier request must not overwrite it
  const recorder = useRef(null);
  const abortRef = useRef(null); // lets the Stop button cancel the answer being written
  const [dragging, setDragging] = useState(false);
  const busyRef = useRef(false);
  const prefsReady = useRef(false); // never write settings to the server before the saved ones were read, or a fresh device would erase them

  // Settings: the server copy (per account or per browser) wins over this device's localStorage. Re-read after sign-in, since the owner changed.
  const pullPrefs = () => getSettings().then((p) => {
    if (p && Object.keys(p).length) {
      if (p.lang) { setLang(cleanLang(p.lang)); saveLang(cleanLang(p.lang)); }
      if (typeof p.speak === "boolean") setSpeak(p.speak);
      if (p.rate) { setRate(p.rate); saveRate(p.rate); }
      if (p.profile) { setProfile(p.profile); saveProfile(p.profile); }
    }
    prefsReady.current = true;
  }).catch(() => {}); // server down: keep local settings, and stay read-only so nothing is overwritten
  useEffect(() => { pullPrefs(); }, []);
  useEffect(() => {
    if (!prefsReady.current) return;
    const id = setTimeout(() => saveSettings({ lang, speak, rate, profile }), 800); // debounced: typing a village is one save, not ten
    return () => clearTimeout(id);
  }, [lang, speak, rate, profile]);

  useEffect(() => {
    getDomain().then(setDomain).catch(() => setDomain({ title: "Backend unreachable", tagline: "Start it: make dev", suggested_prompts: [], languages: { en: "English" } }));
    getHealth().then(setHealth).catch(() => {});
    getAuthConfig().then((c) => { setAuthCfg(c); if (c.enabled) getMe().then(setUser).catch(() => {}); }).catch(() => {}); // login is optional: any failure = anonymous
    // Reopen the chat that was open last time, but only if the server has it (asking for an unsaved one is a 404 in the console).
    listChats().then((cs) => { setChats(cs); if (cs.some((c) => c.id === chatId)) getChat(chatId).then((c) => setMsgs(c.messages)).catch(() => {}); }).catch(() => {});
  }, []);
  useEffect(() => saveChatId(chatId), [chatId]);
  useEffect(() => { document.documentElement.lang = lang; }, [lang]); // screen readers and Devanagari shaping follow the chosen language

  // The chat list belongs to whoever is signed in, so it is reloaded on sign-in; signing out also clears the screen of their chats.
  const onUser = (u) => { setUser(u); refreshChats(); pullPrefs(); };
  const onSignedOut = () => { setUser(null); newChat(); setChats([]); refreshChats(); pullPrefs(); };
  const refreshChats = () => listChats().then(setChats).catch(() => {}); // history is a convenience: the chat works without it

  function newChat() {
    if (busy) return;
    opened.current += 1;
    setChatId(newChatId());
    setMsgs([]);
    setTrace([]);
    setDrawer(false);
  }

  async function openChat(id) {
    if (busy || id === chatId) return setDrawer(false);
    const mine = ++opened.current;
    try {
      const c = await getChat(id);
      if (mine !== opened.current) return;
      setChatId(id);
      setMsgs(c.messages);
      setTrace([]);
      setDrawer(false);
    } catch {
      if (mine === opened.current) botSay(uiText(lang).loadfail);
    }
  }

  async function removeChat(id) {
    if (busy || !window.confirm(uiText(lang).delask)) return;
    await deleteChat(id).catch(() => {});
    if (id === chatId) newChat();
    refreshChats();
  }

  async function send(text) {
    text = (text ?? input).trim() || (photo ? PHOTO_PROMPT : "");
    if (!text || busy) return;
    const image = photo;
    let stoppedPhoto = false;
    setInput("");
    setPhoto(null);
    setBusy(true);
    setSlow(false);
    const ctl = new AbortController();
    abortRef.current = ctl;
    const slowTimer = setTimeout(() => setSlow(true), 15_000); // live sources can be slow: say so instead of looking frozen
    setTrace([]);
    setMsgs((m) => [...m, { role: "user", text: image ? `📷 ${image.name}\n${text}` : text, at: stamp() }]);
    try {
      const imageB64 = image?.b64;
      const r = await chatStream({ message: text, sessionId: chatId, language: lang, imageB64, profile: { place: profile.place, crop: profile.crop, sowing_date: profile.sowing_date }, signal: ctl.signal }, (s) => setTrace((t) => [...t, s]));
      setMsgs((m) => [...m, { role: "bot", text: r.answer, meta: r, at: stamp(), id: r.message_id || undefined, feedback: null }]);
      setAiDown(!!r.live_only);
      refreshChats();
      if (r.profile?.place) { const np = { ...profile, place: profile.place || r.profile.place }; setProfile(np); saveProfile(np); }
      if (speak) speakNow(r.answer, r.language || lang);
    } catch (e) {
      if (e.stopped) { // the person pressed Stop: nothing was saved, so take the question back into the box instead of leaving a half chat
        setMsgs((m) => m.slice(0, -1));
        setInput(text === PHOTO_PROMPT ? "" : text);
        if (image) { setPhoto(image); stoppedPhoto = true; }
        return;
      }
      const failure = e.retryAfter ? uiText(lang).wait(e.retryAfter) : e.timeout ? uiText(lang).timeout : e.offline ? uiText(lang).offline : uiText(lang).down;
      setMsgs((m) => [...m, { role: "bot", text: failure, meta: { degraded: true }, at: stamp(), retry: image ? undefined : text }]); // a photo is not kept, so only text can be retried
    } finally {
      clearTimeout(slowTimer);
      setSlow(false);
      setBusy(false);
      abortRef.current = null;
      if (image && !stoppedPhoto) URL.revokeObjectURL(image.previewUrl);
    }
  }

  // Automatic read-aloud uses the same per-language voice as the Listen button; no voice for the language means a visible note, not silence.
  function speakNow(text, l) {
    const out = say(text, l, { rate, voices });
    if (out === "novoice") setNotice(uiText(lang).novoice(domain.languages[l] || l));
  }

  const stop = () => abortRef.current?.abort();

  // Thumbs: shown at once, saved in the background; if saving fails the thumb goes back so the screen never claims a vote that was lost.
  async function vote(m, value) {
    const set = (v) => setMsgs((all) => all.map((x) => (x.id === m.id ? { ...x, feedback: v } : x)));
    set(value);
    if (!(await sendFeedback(m.id, value))) set(m.feedback ?? null);
  }

  // Drop a crop photo anywhere on the page. Only images; same resize path as the camera button.
  const hasFiles = (e) => [...(e.dataTransfer?.types || [])].includes("Files");
  async function dropPhoto(e) {
    e.preventDefault();
    setDragging(false);
    const f = [...(e.dataTransfer?.files || [])][0];
    if (!f || busy) return;
    if (!f.type.startsWith("image/")) return botSay(uiText(lang).notImage);
    try { setPhoto(await prepareImage(f)); } catch { botSay(uiText(lang).photoFail); }
  }

  async function pickPhoto(e) {
    const f = e.target.files?.[0];
    e.target.value = ""; // lets the same file be picked again
    if (!f) return;
    try {
      setPhoto(await prepareImage(f)); // resized in the browser: a phone photo is several MB, a diagnosis needs far less
    } catch {
      botSay(uiText(lang).photoFail); // a format this browser cannot decode (some HEIC files)
    }
  }

  // "Use my location": the browser's coordinates go to /api/locate only, which hands back a place name; nothing else sees or keeps them.
  function useLocation() {
    if (!navigator.geolocation) return botSay(uiText(lang).noloc);
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const out = await locate(pos.coords.latitude, pos.coords.longitude).catch(() => ({}));
        setLocating(false);
        if (out.place) { const np = { ...profile, place: out.place }; setProfile(np); saveProfile(np); }
        else botSay(out.error || uiText(lang).noloc);
      },
      () => { setLocating(false); botSay(uiText(lang).noloc); }, // denied, unavailable, or an http page
      { timeout: 15000, maximumAge: 600000 },
    );
  }

  function setField(key, value) { const np = { ...profile, [key]: value }; setProfile(np); saveProfile(np); }

  const botSay = (text) => setMsgs((m) => [...m, { role: "bot", text, meta: { degraded: true }, at: stamp() }]);

  // Try again: drop the failed question and its error, then ask it afresh (nothing was saved for a failed turn).
  function retry(text) {
    if (busy) return;
    setMsgs((m) => m.slice(0, -2));
    send(text);
  }

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
    <div className="app" onDragOver={(e) => { if (hasFiles(e)) { e.preventDefault(); setDragging(true); } }} onDragLeave={(e) => { if (!e.relatedTarget) setDragging(false); }} onDrop={dropPhoto}>
      {dragging && (
        <div className="dropzone" role="status">
          <div><span aria-hidden="true">📷</span><h3>{uiText(lang).dropTitle}</h3><p>{uiText(lang).dropHint}</p></div>
        </div>
      )}
      <header>
        <div>
          <h1>{domain.title}</h1>
          <p>{uiText(lang).tagline || domain.tagline}</p>
        </div>
        <div className="controls">
          <button type="button" className="mic hbtn" onClick={() => setDrawer(true)} aria-label={uiText(lang).history} aria-expanded={drawer} aria-controls="history">☰ {uiText(lang).history}</button>
          <select value={lang} onChange={(e) => { setLang(e.target.value); saveLang(e.target.value); }} aria-label="Language">
            {Object.entries(domain.languages).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
          <label className="chk"><input type="checkbox" checked={speak} onChange={(e) => { setSpeak(e.target.checked); if (!e.target.checked) stopSpeech(); }} /> 🔊 Read aloud</label>
          <select value={rate} onChange={(e) => { setRate(Number(e.target.value)); saveRate(Number(e.target.value)); }} aria-label={uiText(lang).rate} title={uiText(lang).rate}>
            <option value={0.8}>🐢 {uiText(lang).slow}</option>
            <option value={1}>{uiText(lang).normal}</option>
            <option value={1.25}>🐇 {uiText(lang).fast}</option>
          </select>
          <SignIn clientId={authCfg.enabled ? authCfg.client_id : ""} user={user} onUser={onUser} onSignedOut={onSignedOut} lang={lang} />
          {health && <AnimatedBadge text={!health.llm_configured ? "AI offline (live data only)" : aiDown ? uiText(lang).aiBusy : uiText(lang).aiOn} color={health.llm_configured && !aiDown ? "#3ecf8e" : "#ff8a3d"} />}
        </div>
      </header>

      <Profile fields={domain.profile_fields || []} profile={profile} onChange={setField} lang={lang} onLocate={useLocation} locating={locating} />

      <main>
        <History chats={chats} chatId={chatId} open={drawer} busy={busy} lang={lang} onNew={newChat} onOpen={openChat} onDelete={removeChat} onClose={() => setDrawer(false)} />
        <MessageList
          msgs={msgs} chatId={chatId} busy={busy} step={trace[trace.length - 1]} lang={lang}
          prompts={domain.suggested_prompts_by_lang?.[lang] || domain.suggested_prompts}
          onAsk={send} onRetry={retry} slow={slow} voices={voices} rate={rate} languages={domain.languages} notice={notice} onNotice={setNotice} health={health} onVote={vote}
        />
      </main>

      <Composer value={input} onChange={setInput} onSend={() => send()} busy={busy} photo={photo} onPhoto={pickPhoto} onClearPhoto={() => { URL.revokeObjectURL(photo?.previewUrl); setPhoto(null); }} rec={rec} transcribing={transcribing} onMic={toggleMic} lang={lang} onStop={stop} />
    </div>
  );
}
