import { useEffect, useState } from "react";
import { suggestPlaces } from "../api.js";
import { uiText } from "../i18n.js";

const MIN_CHARS = 3;
// One-tap crop choices, each named in the crop's own script. The value is the English name the tools understand.
const CROPS = [
  { en: "Onion", label: "Onion (कांदा)" },
  { en: "Soybean", label: "Soybean (सोयाबीन)" },
  { en: "Cotton", label: "Cotton (कापूस)" },
  { en: "Tomato", label: "Tomato (टोमॅटो)" },
  { en: "Wheat", label: "Wheat (गहू)" },
];

// Place and crop: the two things every answer needs. Suggestions come from the same keyless geocoder the server uses.
export default function Profile({ fields, profile, onChange, lang, onLocate, locating }) {
  const t = uiText(lang);
  const [open, setOpen] = useState(() => !profile.place);
  const [places, setPlaces] = useState([]);
  const [typed, setTyped] = useState(false); // suggest only after the person types: a remembered place must not be sent to a third party on every page load
  const q = profile.place || "";

  useEffect(() => { // debounce, and drop a slow answer that arrives after a newer keystroke
    if (!typed || q.trim().length < MIN_CHARS) return setPlaces([]);
    const ctl = new AbortController();
    const timer = setTimeout(() => suggestPlaces(q.trim(), ctl.signal).then(setPlaces).catch(() => {}), 300);
    return () => { clearTimeout(timer); ctl.abort(); };
  }, [q, typed]);

  const summary = profile.place ? `📍 ${profile.place}` : "";

  return (
    <details className="profile" open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary><span>{summary || `📍 ${t.fields.place}`}</span><em aria-hidden="true">{open ? "▴" : "▾"}</em></summary>
      <div className="fields">
        {fields.map((f) => (
          <label key={f.key}>
            <span>{t.fields?.[f.key] || f.label}</span>
            <input
              list={f.key === "place" ? "opt-place" : undefined}
              value={profile[f.key] || ""} placeholder={f.placeholder} autoComplete="off" enterKeyHint="done"
              onChange={(e) => { if (f.key === "place") setTyped(true); onChange(f.key, e.target.value); }}
            />
            {f.key === "place" && <datalist id="opt-place">{places.map((p) => <option key={p} value={p} />)}</datalist>}
            {f.key === "place" && <button type="button" className="loc" onClick={onLocate} disabled={locating}>📍 {locating ? "…" : t.useloc}</button>}
          </label>
        ))}
        <div className="crop-chips" role="group" aria-label={t.fields?.crop || "Crop"}>
          {CROPS.map((c) => (
            <button
              key={c.en} type="button" aria-pressed={profile.crop === c.en}
              className={profile.crop === c.en ? "chip on" : "chip"}
              onClick={() => onChange("crop", c.en)}
            >
              {c.label}
            </button>
          ))}
        </div>
      </div>
    </details>
  );
}
