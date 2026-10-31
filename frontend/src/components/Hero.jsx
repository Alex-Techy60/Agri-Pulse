import { useEffect, useState } from "react";
import { uiText } from "../i18n.js";

const EVERY_MS = 5000;

// Empty-chat welcome. Two headline lines slide in from opposite sides (Eldora UI's MultiDirectionSlideText); under them one
// product promise at a time rotates (the testimonial-slider idea, but with promises this app keeps, not invented quotes).
// Rotation pauses on hover/focus and is off for reduced-motion users; the dots always let you read all three.
export default function Hero({ lang }) {
  const t = uiText(lang);
  const [i, setI] = useState(0);
  const [paused, setPaused] = useState(false);
  const still = !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const n = t.promises.length;

  useEffect(() => {
    if (still || paused) return;
    const id = setInterval(() => setI((k) => (k + 1) % n), EVERY_MS);
    return () => clearInterval(id);
  }, [still, paused, n]);

  return (
    <section className="hero">
      <div className="lines">
        <h2 className="a">{t.heroA}</h2>
        <h2 className="b">{t.heroB}</h2>
      </div>
      <div className="promise" onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)} onFocus={() => setPaused(true)} onBlur={() => setPaused(false)}>
        <p key={i}>{t.promises[i]}</p>
        <div className="dots">
          {t.promises.map((_, k) => <button key={k} type="button" className={k === i ? "on" : ""} aria-label={t.promiseDot(k + 1)} aria-current={k === i} onClick={() => setI(k)} />)}
        </div>
      </div>
    </section>
  );
}
