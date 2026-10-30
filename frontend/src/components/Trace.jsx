// The live "how the agents thought" panel. This is the single best thing to have on screen in a demo.
export default function Trace({ steps }) {
  if (!steps.length) return <p className="muted">Ask something to watch the agents work.</p>;
  return (
    <ol className="trace">
      {steps.map((s, i) => (
        <li key={i} className={s.ok ? "" : "bad"}>
          <b>{s.agent}</b> <span>{s.action}</span>
          {s.ms > 0 && <em>{s.ms}ms</em>}
          {s.detail && <div className="detail">{s.detail}</div>}
        </li>
      ))}
    </ol>
  );
}
