// Data cards rendered from tool output (real, live data) + the source/timestamp line under every answer.

const fmtTime = (iso) => {
  try { return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); } catch { return iso; }
};
const day = (d) => { try { return new Date(d).toLocaleDateString([], { weekday: "short", day: "numeric" }); } catch { return d; } };

export function Sources({ list }) {
  if (!list?.length) return null;
  return (
    <small className="live">
      Live data:{" "}
      {list.map((s, i) => (
        <span key={i} className={s.stale ? "stale" : ""}>
          <a href={s.url} target="_blank" rel="noreferrer">{s.name}</a> · {fmtTime(s.fetched_at)}{s.stale ? " (older data - source slow)" : ""}
          {i < list.length - 1 ? " · " : ""}
        </span>
      ))}
    </small>
  );
}

function Forecast({ c }) {
  return (
    <div className="card">
      <h3>{c.title}</h3>
      <div className="days">
        {c.days.map((d) => (
          <div key={d.date} className={`dcell ${d.rain_mm >= 2.5 ? "wet" : ""}`}>
            <b>{day(d.date)}</b>
            <span>{Math.round(d.tmax)}° / {Math.round(d.tmin)}°</span>
            <em>{d.rain_mm} mm</em>
          </div>
        ))}
      </div>
      {c.flags?.length > 0 && <div className="flags">{c.flags.map((f, i) => <span key={i} className="flag">{f.flag.replace("_", " ")} · {day(f.day)}</span>)}</div>}
      {c.soil_moisture != null && <small>Soil moisture (3-9 cm, model): {c.soil_moisture} m³/m³</small>}
    </div>
  );
}

function Prices({ c }) {
  const pts = c.series || [];
  const W = 260, H = 60;
  const vals = pts.map((p) => p.modal);
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const xy = pts.map((p, i) => [pts.length > 1 ? (i / (pts.length - 1)) * W : W / 2, H - ((p.modal - lo) / (hi - lo || 1)) * (H - 10) - 5]);
  const sig = c.signal?.signal;
  return (
    <div className="card">
      <h3>{c.title}</h3>
      {sig && <span className={`sig ${sig}`}>{sig.replace("_", " ")}{c.signal.change_pct != null ? ` · ${c.signal.change_pct}% in ${c.signal.window_days} days, same ${c.signal.markets_compared} markets` : ""}</span>}
      {pts.length > 1 && (
        <svg viewBox={`0 0 ${W} ${H}`} className="spark" role="img" aria-label="price trend">
          <polyline fill="none" stroke="currentColor" strokeWidth="2" points={xy.map((p) => p.join(",")).join(" ")} />
          {xy.map((p, i) => <circle key={i} cx={p[0]} cy={p[1]} r="2.5" />)}
        </svg>
      )}
      <small>{pts.length ? `₹${pts[pts.length - 1].modal} per quintal on ${pts[pts.length - 1].date}` : ""}</small>
      {c.markets?.length > 0 && (
        <table><tbody>{c.markets.map((m, i) => <tr key={i}><td>{m.market}</td><td>{m.district}</td><td>₹{m.modal}</td></tr>)}</tbody></table>
      )}
      {c.position && (
        <small className="position">
          State median ₹{c.position.state_median} across {c.position.markets} markets · best ₹{c.position.best_price} at {c.position.best_market}
          {c.position.local_median != null ? ` · your district ₹${c.position.local_median} (${c.position.pct_vs_state_median}% vs state)` : ""}
        </small>
      )}
    </div>
  );
}

const ALERTS = { DRY_SPELL_ALERT: "Dry spell", IRRIGATION_URGENT: "Irrigation urgent", WATERLOGGING_RISK: "Waterlogging risk" };

function RainHistory({ c }) {
  const pts = c.daily || [];
  const hi = Math.max(1, ...pts.map((p) => p.rain_mm ?? 0));
  const today = new Date().toISOString().slice(0, 10);
  return (
    <div className="card">
      <h3>{c.title}</h3>
      <div className="rainstats">
        <div><b>{c.past_7d_mm} mm</b><span>last 7 days</span></div>
        <div><b>{c.past_30d_mm} mm</b><span>last 30 days</span></div>
        <div><b>{c.forecast_7d_mm} mm</b><span>next 7 days</span></div>
      </div>
      {pts.length > 0 && (
        <div className="rainbars" role="img" aria-label="daily rain, last 30 days then next 7">
          {pts.map((p) => <i key={p.date} className={p.date >= today ? "next" : ""} style={{ height: `${Math.max(2, ((p.rain_mm ?? 0) / hi) * 100)}%` }} title={`${p.date}: ${p.rain_mm ?? "no data"} mm`} />)}
        </div>
      )}
      {c.alerts?.length > 0 && <div className="flags">{c.alerts.map((a) => <span key={a} className="flag">{ALERTS[a] || a}</span>)}</div>}
    </div>
  );
}

function Diagnosis({ c }) {
  return (
    <div className="card">
      <h3>{c.title}</h3>
      <span className={`sev ${c.severity}`}>Severity: {c.severity}</span>
      {c.symptoms?.length > 0 && <><h4>Symptoms seen</h4><ul>{c.symptoms.map((s, i) => <li key={i}>{s}</li>)}</ul></>}
      {c.possible_causes?.length > 0 && <><h4>Possible causes</h4><ul>{c.possible_causes.map((s, i) => <li key={i}>{s}</li>)}</ul></>}
      {c.recommendations?.length > 0 && <><h4>Next steps</h4><ul>{c.recommendations.map((s, i) => <li key={i}>{s}</li>)}</ul></>}
      <small>{c.disclaimer}</small>
    </div>
  );
}

const CARD_TYPES = { forecast: Forecast, prices: Prices, rainfall_history: RainHistory, diagnosis: Diagnosis };

export function Cards({ cards }) {
  if (!cards?.length) return null;
  return <div className="cards">{cards.map((c, i) => { const Card = CARD_TYPES[c.type]; return Card ? <Card key={i} c={c} /> : null; })}</div>;
}
