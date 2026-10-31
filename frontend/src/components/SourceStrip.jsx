import { uiText } from "../i18n.js";

// The live sources behind every number, with whether each is set up on THIS server (from /api/health). Nothing here is data:
// a source that is not configured says so instead of pretending. Cards lift in turn (CSS), echoing the data flowing in.
export default function SourceStrip({ health, lang }) {
  const t = uiText(lang);
  if (!health) return null;
  const sources = [
    { kind: t.kWeather, name: "Open-Meteo", on: true }, // needs no key
    { kind: t.kPrices, name: "data.gov.in Agmarknet", on: !!health.mandi_key_configured },
    { kind: t.kSoil, name: "ISRIC SoilGrids", on: true }, // needs no key
    { kind: t.kDocs, name: "PIB, Govt. of India", on: (health.knowledge_chunks ?? 0) > 0 },
  ];
  return (
    <section className="srcstrip" aria-label={t.srcTitle}>
      <h2>{t.srcTitle}</h2>
      <ul>
        {sources.map((s, i) => (
          <li key={s.name} className={s.on ? "on" : "off"} style={{ animationDelay: `${i * 1.4}s` }}>
            <small>{s.kind}</small>
            <b>{s.name}</b>
            <span><i aria-hidden="true" />{s.on ? t.srcReady : t.srcOff}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
