import { useEffect, useState } from "react";
import { suggestPlaces } from "../api.js";
import { uiText } from "../i18n.js";

// Icons are decoration for people who read slowly; the crop name is always shown next to them. Unlisted crops get a seedling.
const ICON = {
  apple: "🍎", banana: "🍌", brinjal: "🍆", cabbage: "🥬", cauliflower: "🥦", chilli: "🌶️", coriander: "🌿", garlic: "🧄", ginger: "🫚",
  grapes: "🍇", groundnut: "🥜", lemon: "🍋", maize: "🌽", mango: "🥭", mustard: "🌼", onion: "🧅", paddy: "🌾", potato: "🥔",
  rice: "🍚", soybean: "🫘", tomato: "🍅", wheat: "🌾",
};
const icon = (crop) => ICON[String(crop).toLowerCase()] || "🌱";
const MIN_CHARS = 3;

// Place and crop: the two things every answer needs. Suggestions come from the same keyless geocoder the server uses.
export default function Profile({ fields, profile, onChange, lang, onLocate, locating }) {
  const t = uiText(lang);
  const [open, setOpen] = useState(() => !(profile.place && profile.crop));
  const [places, setPlaces] = useState([]);
  const [typed, setTyped] = useState(false); // suggest only after the person types: a remembered place must not be sent to a third party on every page load
  const q = profile.place || "";

  useEffect(() => { // debounce, and drop a slow answer that arrives after a newer keystroke
    if (!typed || q.trim().length < MIN_CHARS) return setPlaces([]);
    const ctl = new AbortController();
    const timer = setTimeout(() => suggestPlaces(q.trim(), ctl.signal).then(setPlaces).catch(() => {}), 300);
    return () => { clearTimeout(timer); ctl.abort(); };
  }, [q, typed]);

  const crops = fields.find((f) => f.key === "crop")?.options || [];
  const summary = [profile.place && `📍 ${profile.place}`, profile.crop && `${icon(profile.crop)} ${profile.crop}`].filter(Boolean).join("  ·  ");

  return (
    <details className="profile" open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary><span>{summary || `📍 ${t.fields.place} · ${t.fields.crop}`}</span><em aria-hidden="true">{open ? "▴" : "▾"}</em></summary>
      <div className="fields">
        {fields.map((f) => (
          <label key={f.key}>
            <span>{t.fields?.[f.key] || f.label}</span>
            <input
              list={f.key === "place" ? "opt-place" : f.options ? `opt-${f.key}` : undefined}
              value={profile[f.key] || ""} placeholder={f.placeholder} autoComplete="off" enterKeyHint="done"
              onChange={(e) => { if (f.key === "place") setTyped(true); onChange(f.key, e.target.value); }}
            />
            {f.key === "place" && <datalist id="opt-place">{places.map((p) => <option key={p} value={p} />)}</datalist>}
            {f.options && f.key !== "crop" && <datalist id={`opt-${f.key}`}>{f.options.map((o) => <option key={o} value={o} />)}</datalist>}
            {f.key === "place" && <button type="button" className="loc" onClick={onLocate} disabled={locating}>📍 {locating ? "…" : t.useloc}</button>}
          </label>
        ))}
      </div>
      {crops.length > 0 && (
        <div className="crops" role="radiogroup" aria-label={t.pickCrop}>
          {crops.map((c) => {
            const on = String(profile.crop || "").toLowerCase() === c.toLowerCase();
            return <button key={c} type="button" role="radio" aria-checked={on} className={on ? "crop on" : "crop"} onClick={() => onChange("crop", c)}><i aria-hidden="true">{icon(c)}</i>{c}</button>;
          })}
        </div>
      )}
    </details>
  );
}
