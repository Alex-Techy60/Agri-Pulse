import { useState } from "react";
import { uiText } from "../i18n.js";

// The live "how the agents thought" panel. This is the single best thing to have on screen in a demo.
// Collapsible (closed by default on phones, where it sits under the chat), steps animate in, failed steps are red,
// and a guardrail REJECTED followed by passed is called out: that self-correction is the point of the demo.
export default function Trace({ steps, lang }) {
  const t = uiText(lang);
  const [open, setOpen] = useState(() => !window.matchMedia?.("(max-width: 800px)").matches);
  const [all, setAll] = useState(false); // show every step's detail
  const rejected = steps.findIndex((s) => s.agent === "Guardrail" && s.action === "REJECTED");
  const corrected = rejected >= 0 && steps.some((s, i) => i > rejected && s.agent === "Guardrail" && s.action.startsWith("passed"));
  return (
    <details className="tracebox" open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>{t.howDecided}{steps.length > 0 && <em>{t.steps(steps.length)}</em>}</summary>
      {corrected && <p className="fixed" role="status">✓ {t.fixed}</p>}
      {!steps.length ? (
        <p className="muted">{t.traceEmpty}</p>
      ) : (
        <>
          <button type="button" className="ghost expand" onClick={() => setAll((v) => !v)} aria-pressed={all}>{all ? t.hideDetails : t.showDetails}</button>
          <ol className="trace">
            {steps.map((s, i) => {
              const guard = s.agent === "Guardrail";
              const cls = !s.ok ? "bad" : guard && s.action.startsWith("passed") && corrected ? "fixed" : "";
              const head = <><b>{s.agent}</b> <span>{s.action}</span>{s.ms > 0 && <em>{s.ms}ms</em>}</>;
              return (
                <li key={i} className={cls}>
                  {s.detail ? (
                    // a failed step or a guardrail verdict is the story, so it starts open; the rest fold away until asked for
                    <details open={all || !s.ok || guard}>
                      <summary>{head}</summary>
                      <div className="detail">{s.detail}</div>
                    </details>
                  ) : head}
                </li>
              );
            })}
          </ol>
        </>
      )}
    </details>
  );
}
