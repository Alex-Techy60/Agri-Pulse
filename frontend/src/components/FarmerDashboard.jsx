import { useCallback, useEffect, useState } from "react";
import { uiText } from "../i18n.js";
import { getBoardStats, getDashboard, listGrievances } from "../api.js";
import { Cards, Sources } from "./Cards.jsx";

// Every number on this page comes from /api/dashboard (live tools) or /api/public/board (stored reports).
// Nothing is typed in here: a source that fails shows "source unavailable", never an invented value.
const SECTIONS = [
  { key: "weather", title: (t) => t.dWeather },
  { key: "mandi", title: (t) => t.dMandi },
  { key: "soil", title: (t) => t.dSoil },
  { key: "rain_history", title: (t) => t.dRain },
];

export default function FarmerDashboard({ lang, profile, onNavigate }) {
  const t = uiText(lang);
  const place = (profile?.place || "").trim();
  const crop = profile?.crop || "Onion";
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [board, setBoard] = useState(null);
  const [reports, setReports] = useState(null);

  const load = useCallback(() => {
    if (!place) { setData(null); return; }
    setLoading(true);
    setLoadError("");
    getDashboard(place, crop)
      .then(setData)
      .catch(() => { setData(null); setLoadError(t.down); })
      .finally(() => setLoading(false));
  }, [place, crop, t.down]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    getBoardStats().then(setBoard).catch(() => setBoard(null));
    listGrievances().then((r) => setReports(r.slice(0, 5))).catch(() => setReports(null));
  }, []);

  return (
    <div className="dash">
      <section className="card dash-head">
        <div>
          <span className="dash-kicker">{t.dKicker}</span>
          <h2>{place ? `${place} · ${crop}` : t.dSetPlace}</h2>
          {data?.generated_at && (
            <p className="muted">{t.dFetched} {new Date(data.generated_at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}</p>
          )}
        </div>
        <div className="dash-actions">
          {place && <button type="button" className="ghost" onClick={load} disabled={loading}>{loading ? "…" : `↻ ${t.dRefresh}`}</button>}
          <button type="button" onClick={() => onNavigate("advisory")}>{t.dAsk}</button>
          <button type="button" className="ghost" onClick={() => onNavigate("report")}>{t.dReport}</button>
        </div>
      </section>

      {loadError && <div role="alert" className="card dash-unavail">{loadError}</div>}

      {place && (
        <div className="dash-grid">
          {SECTIONS.map(({ key, title: titleOf }) => {
            const title = titleOf(t);
            const sec = data?.sections?.[key];
            return (
              <section key={key} className="card dash-card" aria-label={title}>
                <h3>{title}</h3>
                {!sec && <p className="muted">{loading ? t.dLoading : t.dNoData}</p>}
                {sec && sec.ok && (
                  <>
                    {sec.cards?.length ? <Cards cards={sec.cards} lang={lang} /> : <p className="muted">{t.dNoRecords}</p>}
                    <Sources list={sec.sources} lang={lang} />
                  </>
                )}
                {sec && !sec.ok && (
                  <div className="dash-unavail" role="status">
                    <strong>{t.dUnavail}</strong>
                    <span className="muted"> {sec.error || "no reply"}. {t.dNoNumber}</span>
                    <button type="button" className="ghost" onClick={load} disabled={loading}>{t.dRetry}</button>
                  </div>
                )}
              </section>
            );
          })}
        </div>
      )}

      <section className="card dash-card" aria-label={t.dCrises}>
        <div className="dash-head-row">
          <h3>{t.dCrises}</h3>
          {board && (
            <button type="button" className="linkbtn" onClick={() => onNavigate("board")}>
              {t.dBoard(board.total_reports)}
            </button>
          )}
        </div>
        {reports === null && <p className="muted">{t.dNoReports}</p>}
        {reports && reports.length === 0 && <p className="muted">{t.dNoCrises}</p>}
        {reports && reports.length > 0 && (
          <ul className="report-list">
            {reports.map((r) => (
              <li key={r.id}>
                <span className={`badge ${r.urgency === "P1" ? "bad" : ""}`}>{r.urgency}</span>{" "}
                <strong>{r.category.replace(/_/g, " ").toLowerCase()}</strong>{" "}
                <span className="muted">{r.place} · {r.status}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
