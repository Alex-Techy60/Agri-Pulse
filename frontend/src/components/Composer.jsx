import { useEffect, useRef } from "react";
import { uiText } from "../i18n.js";

const MAX_CHARS = 4000; // the API's limit on one message
const MAX_ROWS_PX = 140;

// Enter sends, Shift+Enter adds a line. Never send while an input-method editor (Hindi/Marathi keyboards) is mid-word.
export default function Composer({ value, onChange, onSend, busy, photo, onPhoto, onClearPhoto, rec, transcribing, onMic, lang, onStop }) {
  const t = uiText(lang);
  const box = useRef(null);

  useEffect(() => { // grow with the text, up to a few lines
    const el = box.current;
    if (!el) return;
    el.style.height = "auto";
    const border = el.offsetHeight - el.clientHeight; // scrollHeight leaves out the border that box-sizing adds back
    el.style.height = `${Math.min(el.scrollHeight + border, MAX_ROWS_PX)}px`;
  }, [value]);

  function key(e) {
    if (e.key !== "Enter" || e.shiftKey || e.nativeEvent.isComposing || e.keyCode === 229) return;
    e.preventDefault();
    onSend();
    box.current?.focus();
  }

  const can = !busy && (value.trim() || photo);
  return (
    <form className="composer" onSubmit={(e) => { e.preventDefault(); if (can) onSend(); box.current?.focus(); }}>
      {photo && (
        <div className="chip" role="status">
          {photo.previewUrl ? <img src={photo.previewUrl} alt="" /> : "📷"} <span>{t.photoReady(photo.name)}</span>
          <button type="button" className="ghost" onClick={onClearPhoto} aria-label={t.removePhoto} title={t.removePhoto}>✕</button>
        </div>
      )}
      <div className="bar">
        <button type="button" className={rec ? "mic on" : "mic"} onClick={onMic} disabled={transcribing} aria-label={t.mic} aria-pressed={rec}>{rec ? "■" : transcribing ? "…" : "🎤"}</button>
        <label className={photo ? "mic photo on" : "mic photo"} title={photo ? photo.name : t.addPhoto}>
          📷<input type="file" accept="image/*" onChange={onPhoto} disabled={busy} aria-label={t.addPhoto} />
        </label>
        <textarea
          ref={box} rows={1} value={value} maxLength={MAX_CHARS} enterKeyHint="send" aria-label={t.ask}
          onChange={(e) => onChange(e.target.value)} onKeyDown={key} placeholder={t.ask}
        />
        {busy && onStop
          ? <button type="button" className="stopbtn" onClick={onStop} aria-label={t.stopLabel}>■ {t.stopNow}</button>
          : <button type="submit" disabled={!can}>{t.send}</button>}
      </div>
      {value.length > MAX_CHARS - 500 && <small className="count">{value.length}/{MAX_CHARS}</small>}
    </form>
  );
}
