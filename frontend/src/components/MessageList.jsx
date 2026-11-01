import { Fragment, useEffect, useRef, useState } from "react";
import Message from "./Message.jsx";
import Hero from "./Hero.jsx";
import SourceStrip from "./SourceStrip.jsx";
import { uiText } from "../i18n.js";
import { say, stopSpeech } from "../speech.js";

const dayKey = (iso) => (iso ? new Date(iso).toDateString() : "");
function dayLabel(iso, lang) {
  const d = new Date(iso), now = new Date(), yest = new Date(now.getTime() - 86_400_000);
  const t = uiText(lang);
  if (d.toDateString() === now.toDateString()) return t.today;
  if (d.toDateString() === yest.toDateString()) return t.yesterday;
  return d.toLocaleDateString(lang, { day: "numeric", month: "short", year: d.getFullYear() === now.getFullYear() ? undefined : "numeric" });
}

// The conversation: one live region (screen readers hear each new message once), grouped bubbles, day separators,
// a typing indicator that names the pipeline step running, and a "latest" button when the reader has scrolled up.
export default function MessageList({ msgs, chatId, busy, step, lang, prompts, onAsk, onRetry, slow, voices, rate, languages, notice, onNotice, health, onVote }) {
  const t = uiText(lang);
  const endRef = useRef(null);
  const atBottom = useRef(true);
  const lastChat = useRef(chatId);
  const [away, setAway] = useState(false);
  const [speakingId, setSpeakingId] = useState(null);

  // "At the bottom" = the end marker is on screen. Works whether the list or the whole page scrolls (phones).
  useEffect(() => {
    if (!window.IntersectionObserver) return;
    const io = new IntersectionObserver(([e]) => { atBottom.current = e.isIntersecting; setAway(!e.isIntersecting); }, { rootMargin: "0px 0px 80px 0px" });
    io.observe(endRef.current);
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    const switched = lastChat.current !== chatId; // opening another chat always lands on its latest message
    lastChat.current = chatId;
    const mine = msgs.length && msgs[msgs.length - 1].role === "user";
    if (!msgs.length) return; // the welcome screen starts at its heading: scrolling to its end hid the title on first load
    if (switched || mine || atBottom.current) endRef.current?.scrollIntoView({ block: "end" }); // instant: following a stream of steps with animations would lag behind them
  }, [msgs, chatId, busy]);

  useEffect(() => () => stopSpeech(), []);
  useEffect(() => { stopSpeech(); setSpeakingId(null); }, [chatId]);
  useEffect(() => { if (!notice) return; const id = setTimeout(() => onNotice(""), 9000); return () => clearTimeout(id); }, [notice]);

  function speak(m) {
    if (speakingId === m.at) { stopSpeech(); return setSpeakingId(null); }
    const l = m.meta?.language || lang; // the answer's own language, which can differ from the picker
    const out = say(m.text, l, { rate, voices, onEnd: () => setSpeakingId((id) => (id === m.at ? null : id)) });
    if (out === "ok") return setSpeakingId(m.at);
    setSpeakingId(null);
    onNotice(t.novoice(languages?.[l] || l)); // no voice installed for this language, or no speech API in this browser
  }

  const last = msgs.length - 1;
  return (
    <section className="chat" role="log" aria-live="polite" aria-relevant="additions" aria-label={t.conversation} aria-busy={busy}>
      {msgs.length === 0 && <Hero lang={lang} />}
      {msgs.length === 0 && <SourceStrip health={health} lang={lang} />}
      {msgs.length === 0 && (
        <div className="suggest">
          {prompts.map((p) => (
            <button key={p} type="button" onClick={() => onAsk(p)}>{p}</button>
          ))}
        </div>
      )}
      {msgs.map((m, i) => {
        const prev = msgs[i - 1];
        const newDay = m.at && dayKey(m.at) !== dayKey(prev?.at);
        return (
          <Fragment key={m.at ? `${m.at}-${m.role}` : i}>
            {newDay && <div className="daysep"><span>{dayLabel(m.at, lang)}</span></div>}
            <Message
              m={m} lang={lang} grouped={!newDay && prev?.role === m.role}
              speakingId={speakingId} onSpeak={speak} onVote={onVote}
              onRetry={i === last && !busy && m.retry ? () => onRetry(m.retry) : undefined}
            />
          </Fragment>
        );
      })}
      {busy && (
        <div className="row bot" role="status">
          <span className="avatar" aria-hidden="true">🌾</span>
          <div className="msg bot typing"><i /><i /><i /><span className="shimmer">{slow ? t.slowwait : step ? `${step.agent} · ${step.action}` : t.thinking}</span></div>
        </div>
      )}
      {busy && <div className="skeleton" aria-hidden="true"><i /><i /><i /></div>}
      {notice && <p className="notice" role="status">🔇 {notice} <button type="button" className="ghost" onClick={() => onNotice("")} aria-label="OK">✕</button></p>}
      <div ref={endRef} className="end" />
      {away && msgs.length > 0 && <button type="button" className="jump" onClick={() => endRef.current?.scrollIntoView({ block: "end" })}>↓ {t.jump}</button>}
    </section>
  );
}
