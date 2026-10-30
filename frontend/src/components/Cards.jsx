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
      {sig && <span className={`sig ${sig}`}>{sig.replace("_", " ")}{c.signal.pct_vs_baseline != null ? ` · ${c.signal.pct_vs_baseline}% vs recent avg` : ""}</span>}
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
    </div>
  );
}

export function Cards({ cards }) {
  if (!cards?.length) return null;
  return <div className="cards">{cards.map((c, i) => (c.type === "forecast" ? <Forecast key={i} c={c} /> : c.type === "prices" ? <Prices key={i} c={c} /> : null))}</div>;
}
