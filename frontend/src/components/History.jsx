import { useEffect } from "react";
import { uiText } from "../i18n.js";

// Saved chats of this browser. A column on wide screens, a drawer (Escape or the backdrop closes it) on phones.
export default function History({ chats, chatId, open, busy, lang, onNew, onOpen, onDelete, onClose }) {
  const t = uiText(lang);
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <>
      {open && <div className="backdrop" onClick={onClose} />}
      <nav id="history" className={open ? "history open" : "history"} aria-label={t.history}>
        <button type="button" className="newchat" onClick={onNew} disabled={busy}>＋ {t.newchat}</button>
        <h2>{t.history}</h2>
        {chats.length === 0 && <p className="muted">{t.nochats}</p>}
        <ul>
          {chats.map((c) => (
            <li key={c.id} className={c.id === chatId ? "cur" : ""}>
              <button type="button" className="open" onClick={() => onOpen(c.id)} disabled={busy} title={c.title} aria-current={c.id === chatId ? "true" : undefined}>
                <span>{c.title}</span>
                <small>{new Date(c.updated_at).toLocaleString(lang, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</small>
              </button>
              <button type="button" className="del" onClick={() => onDelete(c.id)} disabled={busy} aria-label={t.del} title={t.del}>🗑</button>
            </li>
          ))}
        </ul>
      </nav>
    </>
  );
}
