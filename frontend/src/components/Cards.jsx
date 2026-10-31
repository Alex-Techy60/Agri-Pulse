import { useState } from "react";
import AlertList from "./AlertList.jsx";
import ErrorBoundary from "./ErrorBoundary.jsx";
import ScrambleText from "./ScrambleText.jsx";
import { uiText } from "../i18n.js";
import { safeHref } from "../url.js";

// Data cards rendered from tool output (real, live data) + the source/timestamp line under every answer.

const valid = (iso) => { const d = new Date(iso); return Number.isNaN(d.getTime()) ? null : d; }; // Invalid Date does not throw, so check it
const fmtTime = (iso) => valid(iso)?.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) ?? "";
const day = (d) => { try { return new Date(d).toLocaleDateString([], { weekday: "short", day: "numeric" }); } catch { return d; } };

const fullTime = (iso, lang) => valid(iso)?.toLocaleString(lang, { dateStyle: "medium", timeStyle: "medium" }) ?? "";

// One chip per live source (idea from prompt-kit's Source): a dot for fresh or older data, the name and time, and a tap for the
// full timestamp and the link. Only what the API sent is shown; a source with no URL is simply not a link.
export function Sources({ list, lang }) {
  const t = uiText(lang);
  if (!Array.isArray(list) || !list.length) return null;
  return (
    <div className="sources" aria-label={t.live}>
      <small className="muted">{t.live}</small>
      <div className="chips">
        {list.filter(Boolean).map((s, i) => (
          <details key={i} className={s.stale ? "srcchip stale" : "srcchip"}>
            <summary>
              <i aria-hidden="true" />
              <b>{s.name}</b>
              {fmtTime(s.fetched_at) && <time dateTime={s.fetched_at}>{fmtTime(s.fetched_at)}</time>}
              {s.stale && <span className="badge old">{t.stale}</span>}
            </summary>
            <div className="srcbody">
              {fullTime(s.fetched_at, lang) && <div>{t.fetchedAt}: <time dateTime={s.fetched_at}>{fullTime(s.fetched_at, lang)}</time></div>}
              {s.stale && <div className="warn">{t.staleWhy}</div>}
              {safeHref(s.url) && <a href={safeHref(s.url)} target="_blank" rel="noreferrer">{t.openSource} ↗</a>}
            </div>
          </details>
        ))}
      </div>
    </div>
  );
}

function Forecast({ c, lang }) {
  if (!Array.isArray(c.days) || !c.days.length) return null; // never show a card with nothing real in it
  return (
    <div className="card">
      <h3>{c.title}</h3>
      <div className="days">
        {(c.days || []).map((d) => (
          <div key={d.date} className={`dcell ${d.rain_mm >= 2.5 ? "wet" : ""}`}>
            <b>{day(d.date)}</b>
            <span>{Math.round(d.tmax)}° / {Math.round(d.tmin)}°</span>
            <em>{d.rain_mm} mm</em>
          </div>
        ))}
      </div>
      <AlertList lang={lang} alerts={(c.flags || []).map((f) => ({ key: f?.flag, day: f?.day }))} />
      {c.soil_moisture != null && <small>Soil moisture (3-9 cm, model): {c.soil_moisture} m³/m³</small>}
    </div>
  );
}

const SIGNAL_LABEL = { SELL_NOW: "sell", HOLD: "hold", NEUTRAL: "steady" }; // INSUFFICIENT_DATA shows no badge: the answer text explains it

// Price chart with a value axis, first/last date, and a tooltip on every point. Real numbers only.
function Chart({ pts, t }) {
  const W = 300, H = 112, L = 54, R = 8, T = 12, B = 26;
  const vals = pts.map((p) => p.modal);
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const x = (i) => L + (pts.length > 1 ? (i / (pts.length - 1)) * (W - L - R) : (W - L - R) / 2);
  const y = (v) => T + (1 - (v - lo) / (hi - lo || 1)) * (H - T - B);
  const short = (d) => String(d).slice(5);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="spark" role="img" aria-label={`${t.perq}: ${lo} - ${hi}`}>
      <line x1={L} x2={W - R} y1={y(hi)} y2={y(hi)} className="grid" />
      <line x1={L} x2={W - R} y1={y(lo)} y2={y(lo)} className="grid" />
      <text x={L - 4} y={y(hi) + 4} textAnchor="end">₹{hi}</text>
      <text x={L - 4} y={y(lo) + 4} textAnchor="end">₹{lo}</text>
      <text x={L} y={H - 7}>{short(pts[0].date)}</text>
      <text x={W - R} y={H - 7} textAnchor="end">{short(pts[pts.length - 1].date)}</text>
      <polyline fill="none" stroke="currentColor" strokeWidth="2" points={pts.map((p, i) => `${x(i)},${y(p.modal)}`).join(" ")} />
      {pts.map((p, i) => <circle key={i} cx={x(i)} cy={y(p.modal)} r="3.5"><title>{`${p.date}: ₹${p.modal}`}</title></circle>)}
    </svg>
  );
}

// The decision badge flips on tap to show WHY (idea from Eldora UI's CardFlipHover, but tap/keyboard, since phones have no hover).
// The back only restates numbers and the rule the server sent; the 5 % band comes from the card, not from this file.
function SignalFlip({ s, t }) {
  const [back, setBack] = useState(false);
  const word = t[SIGNAL_LABEL[s.signal]];
  const pct = s.change_pct;
  return (
    <button type="button" className={`flip ${s.signal}${back ? " back" : ""}`} aria-pressed={back} onClick={() => setBack((b) => !b)}>
      <span className="face front" aria-hidden={back}>
        <strong><ScrambleText text={word} /></strong>
        <span>{pct != null ? t.trend(pct, s.window_days, s.markets_compared) : t.trendOnly}</span>
        <em>{t.tapWhy}</em>
      </span>
      <span className="face rear" aria-hidden={!back}>
        <span>{pct != null ? t.why(s.compared_with, s.latest_date, pct, s.markets_compared, s.band_pct) : t.trendOnly}</span>
        <em>{t.tapBack}</em>
      </span>
    </button>
  );
}

function Prices({ c, lang }) {
  const t = uiText(lang);
  const pts = (c.series || []).filter((p) => Number.isFinite(p.modal));
  const sig = SIGNAL_LABEL[c.signal?.signal];
  const s = c.signal || {};
  return (
    <div className="card">
      <h3>{c.title}</h3>
      {sig && <SignalFlip s={s} t={t} />}
      {!sig && s.signal === "INSUFFICIENT_DATA" && <p className="notrend">{t.noTrend}</p>}
      {pts.length > 1 && <Chart pts={pts} t={t} />}
      <small>{pts.length ? `₹${pts[pts.length - 1].modal} ${t.perq} · ${pts[pts.length - 1].date}` : ""}</small>
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

function RainHistory({ c, lang }) {
  if (c.past_7d_mm == null || c.past_30d_mm == null || c.forecast_7d_mm == null) return null;
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
      <AlertList lang={lang} alerts={(c.alerts || []).map((a) => ({ key: a }))} />
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

const WATER = { RAIN_COVERS_NEED: "rain covers need", WETTER_THAN_OPTIMUM: "wetter than ideal", NEEDS_IRRIGATION: "needs irrigation", NEEDS_IRRIGATION_RAIN_FAR_BELOW_NEED: "needs irrigation (little rain)", FAR_WETTER_THAN_CROP_TOLERATES: "too wet" };

function CropFit({ c }) {
  const rows = c.crops || [];
  if (!rows.length) return null;
  return (
    <div className="card">
      <h3>{c.title}</h3>
      <table>
        <thead><tr><td>Crop</td><td>Fit</td><td>Sow about</td><td>Harvest</td><td>Water</td></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.crop}><td>{r.crop}</td><td>{r.fit}</td><td>{r.sow_on}</td><td>{r.harvest_from} to {r.harvest_to}</td><td>{WATER[r.rain_label] || r.rain_label}</td></tr>
          ))}
        </tbody>
      </table>
      {c.note && <small className="muted">{c.note}</small>}
    </div>
  );
}

function Soil({ c }) {
  if (c.ph == null && c.clay_pct == null) return null;
  return (
    <div className="card">
      <h3>{c.title}</h3>
      <div className="rainstats">
        <div><b>{c.ph}</b><span>pH</span></div>
        <div><b>{c.clay_pct}%</b><span>clay</span></div>
        <div><b>{c.sand_pct}%</b><span>sand</span></div>
        <div><b>{c.organic_carbon_g_kg} g/kg</b><span>organic carbon</span></div>
      </div>
      <small className="muted">{c.texture_class} soil. {c.note}</small>
    </div>
  );
}

function Notice({ c, lang }) {
  const t = uiText(lang);
  if (c.kind !== "no_prices" || !c.crop) return null; // an unknown notice kind renders nothing
  return (
    <div className="card nonotice" role="note">
      <h3>{c.crop} · {t.kPrices}</h3>
      <p>{t.noPrices(c.crop, c.state || "", c.days ?? "", c.complete !== false)}</p>
    </div>
  );
}

const CARD_TYPES = { notice: Notice, soil: Soil, crop_fit: CropFit, forecast: Forecast, prices: Prices, rainfall_history: RainHistory, diagnosis: Diagnosis };

export function Cards({ cards, lang }) {
  if (!Array.isArray(cards) || !cards.length) return null;
  return (
    <div className="cards">
      {cards.map((c, i) => {
        const Card = c && CARD_TYPES[c.type]; // an unknown card type renders nothing
        return Card ? <ErrorBoundary key={i}><Card c={c} lang={lang} /></ErrorBoundary> : null; // a malformed known card is skipped, not fatal
      })}
    </div>
  );
}
