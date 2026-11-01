import { useEffect, useRef, useState } from "react";
import { signInWithGoogle, signOut } from "../api.js";
import { uiText } from "../i18n.js";

const GSI = "https://accounts.google.com/gsi/client";

// Loads Google's official sign-in script once. If it is blocked (offline, ad blocker) the promise rejects and the app simply
// stays anonymous: login is a convenience, never a gate.
let gsiPromise = null;
const loadGsi = () => (gsiPromise ??= new Promise((resolve, reject) => {
  if (window.google?.accounts?.id) return resolve();
  const el = document.createElement("script");
  el.src = GSI; el.async = true; el.defer = true;
  el.onload = () => resolve();
  el.onerror = () => { gsiPromise = null; reject(new Error("gsi blocked")); };
  document.head.appendChild(el);
}));

function Avatar({ user }) {
  const [broken, setBroken] = useState(false);
  const initial = (user.name || user.email || "?").trim().charAt(0).toUpperCase();
  return broken || !user.picture
    ? <span className="acct-avatar" aria-hidden="true">{initial}</span>
    : <img className="acct-avatar" src={user.picture} alt="" referrerPolicy="no-referrer" onError={() => setBroken(true)} />;
}

/** Signed out: Google's own button (brand-compliant). Signed in: avatar with a small menu holding name, email and Sign out. */
export default function SignIn({ clientId, user, onUser, onSignedOut, lang }) {
  const t = uiText(lang);
  const slot = useRef(null);
  const menu = useRef(null);
  const [open, setOpen] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (user || !clientId) return;
    let live = true;
    loadGsi().then(() => {
      if (!live || !slot.current) return;
      window.google.accounts.id.initialize({
        client_id: clientId,
        ux_mode: "popup",
        auto_select: false,
        callback: ({ credential }) => {
          signInWithGoogle(credential).then((u) => { setFailed(false); onUser(u); }).catch(() => setFailed(true));
        },
      });
      slot.current.innerHTML = "";
      window.google.accounts.id.renderButton(slot.current, { type: "standard", theme: "filled_black", size: "medium", shape: "pill", text: "signin_with", locale: lang });
    }).catch(() => {});
    return () => { live = false; };
  }, [user, clientId, lang]);

  useEffect(() => {
    if (!open) return;
    const away = (e) => { if (!menu.current?.contains(e.target)) setOpen(false); };
    const esc = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", esc); };
  }, [open]);

  if (!clientId) return null;
  if (!user) {
    return (
      <div className="signin">
        <div ref={slot} className="gbtn" />
        {failed && <span className="signin-err" role="alert">{t.signInFailed}</span>}
      </div>
    );
  }
  return (
    <div className="account" ref={menu}>
      <button type="button" className="acct-btn" onClick={() => setOpen((o) => !o)} aria-label={t.accountMenu} aria-haspopup="menu" aria-expanded={open}>
        <Avatar user={user} />
      </button>
      {open && (
        <div className="acct-menu" role="menu">
          <div className="acct-who">
            <Avatar user={user} />
            <div><small>{t.signedInAs}</small><strong>{user.name}</strong><span>{user.email}</span></div>
          </div>
          <p className="acct-note">{t.accountNote}</p>
          <button type="button" role="menuitem" className="acct-out" onClick={async () => { setOpen(false); await signOut(); window.google?.accounts?.id.disableAutoSelect(); onSignedOut(); }}>{t.signOut}</button>
        </div>
      )}
    </div>
  );
}
