import { useState } from "react";
import { Cards, Sources } from "./Cards.jsx";
import { uiText } from "../i18n.js";

const OFFLINE_MARK = "(AI summary unavailable - showing live data only)";
const clock = (iso, lang) => { try { return new Date(iso).toLocaleTimeString(lang, { hour: "2-digit", minute: "2-digit" }); } catch { return ""; } };

// One bubble. Bot messages get Copy / Listen (read aloud) and, when the request failed, Try again.
export default function Message({ m, lang, grouped, onRetry, speakingId, onSpeak, onVote, onAsk }) {
  const t = uiText(lang);
  const [copied, setCopied] = useState(false);
  const bot = m.role === "bot";
  // The AI was down and the text is the raw live data: lead with the cards and fold the text, but only if there are cards to lead with.
  const folded = bot && m.meta?.live_only && Array.isArray(m.meta.cards) && m.meta.cards.some((c) => c && c.type);

  function copy() {
    navigator.clipboard?.writeText(m.text).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); }).catch(() => {}); // needs https or localhost
  }

  return (
    <div className={`row ${m.role}${grouped ? " cont" : ""}`}>
      {bot && <span className="avatar" aria-hidden="true">{grouped ? "" : "🌾"}</span>}
      <div className="bubble-wrap">
        <article className={`msg ${m.role}`} aria-label={bot ? "KisaanMitra" : t.you}>
          {folded ? (
            <>
              <p className="liveonly">{t.liveOnly}</p>
              <Cards cards={m.meta.cards} lang={lang} />
              <details className="raw"><summary>{t.rawData}</summary><pre>{m.text.replace(OFFLINE_MARK, "").trim()}</pre></details>
            </>
          ) : (
            <>
              <p lang={m.meta?.language || lang}>{m.text}</p>
              <Cards cards={m.meta?.cards} lang={lang} />
            </>
          )}
          <Sources list={m.meta?.live_sources} lang={lang} />
          {!folded && m.meta?.sources?.length > 0 && <small>{t.docs}: {m.meta.sources.join(", ")}</small>}
          {m.meta?.degraded && <small className="warn note">⚠ {t.degraded}</small>}
        </article>
        {onAsk && Array.isArray(m.meta?.follow_ups) && m.meta.follow_ups.length > 0 && (
          <nav className="followups" aria-label={t.more}>
            <small className="muted">{t.more}</small>
            {m.meta.follow_ups.filter((q) => typeof q === "string" && q).map((q) => <button key={q} type="button" onClick={() => onAsk(q)}>{q}</button>)}
          </nav>
        )}
        <div className="meta">
          {m.at && <time dateTime={m.at}>{clock(m.at, lang)}</time>}
          {bot && (
            <>
              {m.id && onVote && (
                <span className="vote" role="group" aria-label={t.helpful}>
                  <button type="button" className={m.feedback === "up" ? "ghost on" : "ghost"} aria-pressed={m.feedback === "up"} aria-label={t.yes} title={t.yes} onClick={() => onVote(m, m.feedback === "up" ? null : "up")}>👍</button>
                  <button type="button" className={m.feedback === "down" ? "ghost on" : "ghost"} aria-pressed={m.feedback === "down"} aria-label={t.no} title={t.no} onClick={() => onVote(m, m.feedback === "down" ? null : "down")}>👎</button>
                  {m.feedback && <span className="thanks" role="status">{t.thanks}</span>}
                </span>
              )}
              <button type="button" className="ghost" onClick={copy}>{copied ? `✓ ${t.copied}` : `⧉ ${t.copy}`}</button>
              <button type="button" className="ghost" onClick={() => onSpeak(m)} aria-pressed={speakingId === m.at}>{speakingId === m.at ? `■ ${t.stop}` : `🔊 ${t.speak}`}</button>
              {onRetry && <button type="button" className="ghost retry" onClick={onRetry}>↻ {t.retry}</button>}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
