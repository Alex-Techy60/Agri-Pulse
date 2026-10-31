import { useEffect, useState } from "react";

const POOL = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
const SCRAMBLE_MS = 300; // pure noise first
const STEP_MS = 70; // then one letter locks in per step
const TICK_MS = 50;
const plain = (s) => /^[\x20-\x7E]+$/.test(s); // the noise is Latin letters: Devanagari and other scripts are shown as they are
const rand = () => POOL[Math.floor(Math.random() * POOL.length)];
const noise = (s) => [...s].map((c) => (c === " " ? " " : rand())).join("");

// Text that "decodes" into place once (idea from Eldora UI's RandomizedTextEffect). The real text is always what screen readers get,
// the noise never contains digits or the real word's meaning, and reduced-motion users see the final text at once.
export default function ScrambleText({ text }) {
  const still = !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const skip = still || !plain(text);
  const [shown, setShown] = useState(skip ? text : noise(text));

  useEffect(() => {
    if (skip) return setShown(text);
    let cancelled = false; // the card can disappear mid-animation (chat switched): never touch state afterwards
    const t0 = performance.now();
    const id = setInterval(() => {
      if (cancelled) return;
      const age = performance.now() - t0;
      const locked = Math.max(0, Math.floor((age - SCRAMBLE_MS) / STEP_MS));
      if (locked >= text.length) { setShown(text); clearInterval(id); return; }
      setShown(text.slice(0, locked) + noise(text.slice(locked)));
    }, TICK_MS);
    return () => { cancelled = true; clearInterval(id); };
  }, [text, skip]);

  return <span aria-label={text}><span aria-hidden="true">{shown}</span></span>;
}
