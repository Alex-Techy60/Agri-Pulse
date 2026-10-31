import { useId } from "react";
import { safeHref } from "../url.js";

// Status badge with a pulsing dot and a light that travels along a line above it. Ported from the Eldora UI AnimatedBadge:
// plain React + CSS (no Next.js, Tailwind, motion or icon package). Animations stop for people who ask for reduced motion.
function rgba(hex, alpha) {
  const h = hex.replace("#", "");
  const full = h.length === 3 ? [...h].map((c) => c + c).join("") : h;
  if (full.length !== 6) return hex; // not a hex colour (e.g. "red"): use it as is
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16));
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

export default function AnimatedBadge({ text, color = "#3ecf8e", href }) {
  const id = useId().replace(/:/g, ""); // mask and gradient ids must be unique when several badges are on one page
  const body = (
    <>
      <span className="ab-trail" aria-hidden="true">
        <svg viewBox="0 0 50 50" fill="none" width="100%" height="100%">
          <g mask={`url(#m${id})`}><circle className="ab-light" cx="0" cy="0" r="20" fill={`url(#g${id})`} /></g>
          <defs>
            <mask id={`m${id}`}><path d="M 69 49.8 h -30 q -3 0 -3 -3 v -13 q 0 -3 -3 -3 h -23 q -3 0 -3 -3 v -13 q 0 -3 -3 -3 h -30" strokeWidth="0.6" stroke="white" /></mask>
            <radialGradient id={`g${id}`} fx="1">
              <stop offset="0%" stopColor={color} /><stop offset="20%" stopColor={color} /><stop offset="100%" stopColor="transparent" />
            </radialGradient>
          </defs>
        </svg>
      </span>
      <span className="ab-dot" aria-hidden="true" style={{ backgroundColor: rgba(color, 0.4) }}>
        <i className="ping" style={{ backgroundColor: color }} />
        <i className="core" style={{ backgroundColor: rgba(color, 0.8) }} />
      </span>
      <span className="ab-sep" aria-hidden="true" />
      <span className="ab-text">{text}</span>
      {href && <span className="ab-arrow" aria-hidden="true">›</span>}
    </>
  );
  return safeHref(href) ? <a className="abadge" href={safeHref(href)} target="_blank" rel="noreferrer">{body}</a> : <span className="abadge" role="status">{body}</span>;
}
