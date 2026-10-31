import { uiText } from "../i18n.js";

const ICON = { HEAVY_RAIN: "🌧️", HEAT_STRESS: "🔥", COLD_STRESS: "❄️", DRY_SPELL_ALERT: "🏜️", IRRIGATION_URGENT: "💧", WATERLOGGING_RISK: "🌊" };
const SEVERE = new Set(["HEAVY_RAIN", "IRRIGATION_URGENT", "WATERLOGGING_RISK"]);
const dayLabel = (d, lang) => { try { return new Date(d).toLocaleDateString(lang, { weekday: "short", day: "numeric", month: "short" }); } catch { return d || ""; } };
const humanize = (k) => String(k).toLowerCase().replace(/_/g, " ");

// Alerts arrive like notifications, one after another (idea from Eldora UI's AnimatedList). Every row is a rule the server
// actually fired, with its own day; nothing is made up here. An unknown flag still shows, in plain words.
export default function AlertList({ alerts, lang }) {
  const t = uiText(lang);
  const rows = (alerts || []).filter((a) => a && a.key);
  if (!rows.length) return null;
  return (
    <div className="alerts">
      <h4>{t.alerts}</h4>
      <ul>
        {rows.map((a, i) => (
          <li key={`${a.key}-${a.day || i}`} className={SEVERE.has(a.key) ? "severe" : ""} style={{ animationDelay: `${i * 0.18}s` }}>
            <i aria-hidden="true">{ICON[a.key] || "⚠️"}</i>
            <b>{t.fl?.[a.key] || humanize(a.key)}</b>
            {a.day && <time dateTime={a.day}>{dayLabel(a.day, lang)}</time>}
          </li>
        ))}
      </ul>
    </div>
  );
}
