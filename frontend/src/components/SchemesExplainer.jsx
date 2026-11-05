import { useState, useEffect } from "react";
import { getSchemes, explainScheme } from "../api.js";
import { uiText } from "../i18n.js";
import { say, stopSpeech, useVoices } from "../speech.js";

export default function SchemesExplainer({ lang, profile, onAsk, onNavigate }) {
  const t = uiText(lang);
  const voices = useVoices();
  const [schemes, setSchemes] = useState([]);
  const [selectedScheme, setSelectedScheme] = useState("pm_kisan");
  const [customText, setCustomText] = useState("");
  const [useCustom, setUseCustom] = useState(false);
  const [landAcres, setLandAcres] = useState("2.5");
  const [category, setCategory] = useState("Small Farmer");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [speaking, setSpeaking] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getSchemes().then((s) => {
      setSchemes(s);
      if (s.length > 0) setSelectedScheme(s[0].id);
    }).catch(() => {});
  }, []);

  async function handleAnalyze() {
    setLoading(true);
    setError("");
    stopSpeech();
    setSpeaking(false);
    try {
      const payload = {
        document_id: useCustom ? null : selectedScheme,
        text: useCustom ? customText : null,
        language: lang,
        farmer_profile: {
          place: profile?.place || "Nashik, Maharashtra",
          crop: "Onion",
          land_acres: Number(landAcres) || 2.5,
          category: category
        }
      };
      const res = await explainScheme(payload);
      setResult(res);
    } catch (e) {
      setError("Analysis failed. Please check connection.");
    } finally {
      setLoading(false);
    }
  }

  function handleReadAloud() {
    if (!result?.voice_script) return;
    if (speaking) {
      stopSpeech();
      setSpeaking(false);
      return;
    }
    setSpeaking(true);
    say(result.voice_script, lang, {
      rate: 0.95,
      voices,
      onEnd: () => setSpeaking(false)
    });
  }

  return (
    <div className="explainer-view" style={{ display: "flex", flexDirection: "column", gap: "16px", padding: "12px 0" }}>
      <div className="card" style={{ background: "var(--panel)", border: "1px solid var(--line)", borderRadius: "14px", padding: "16px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "10px", marginBottom: "6px" }}>
          <div>
            <h2 style={{ fontSize: "17px", margin: "0 0 6px", color: "var(--text)" }}>📜 Sarkari Yojana & Subsidy Explainer (सरकारी योजना व अनुदान)</h2>
            <p style={{ margin: "0 0 14px", fontSize: "13px", color: "var(--muted)" }}>
              Official government notifications explained in simple words. <b>Every single point is verified against exact quotes in the official circular.</b>
            </p>
          </div>
          {onNavigate && (
            <button
              type="button"
              onClick={() => onNavigate("schemes_engine")}
              style={{ background: "#16212c", color: "#7cc4ff", border: "1px solid #2a4365", padding: "6px 12px", borderRadius: "8px", fontSize: "12px", cursor: "pointer", fontWeight: "600" }}
            >
              ⚙️ Engine Room Audit
            </button>
          )}
        </div>

        <div style={{ display: "flex", gap: "12px", flexWrap: "wrap", marginBottom: "12px" }}>
          <label style={{ flex: 1, minWidth: "220px", fontSize: "13px", color: "var(--muted)" }}>
            Select Official Scheme:
            <select
              value={useCustom ? "custom" : selectedScheme}
              onChange={(e) => {
                if (e.target.value === "custom") {
                  setUseCustom(true);
                } else {
                  setUseCustom(false);
                  setSelectedScheme(e.target.value);
                }
              }}
              style={{ width: "100%", marginTop: "4px" }}
            >
              {schemes.map((s) => (
                <option key={s.id} value={s.id}>{s.title}</option>
              ))}
              <option value="custom">✍️ Paste Custom Notice / Circular Text</option>
            </select>
          </label>

          <label style={{ width: "140px", fontSize: "13px", color: "var(--muted)" }}>
            Land (Acres):
            <input
              type="number"
              step="0.5"
              value={landAcres}
              onChange={(e) => setLandAcres(e.target.value)}
              style={{ width: "100%", marginTop: "4px" }}
            />
          </label>

          <label style={{ width: "160px", fontSize: "13px", color: "var(--muted)" }}>
            Farmer Category:
            <select value={category} onChange={(e) => setCategory(e.target.value)} style={{ width: "100%", marginTop: "4px" }}>
              <option value="Small / Marginal">Small / Marginal (&lt; 5 Acres)</option>
              <option value="Medium">Medium Farmer</option>
              <option value="Women Farmer">Women Farmer (महिला शेतकरी)</option>
              <option value="SC / ST">SC / ST Farmer</option>
            </select>
          </label>
        </div>

        {useCustom && (
          <div style={{ marginBottom: "12px" }}>
            <label style={{ fontSize: "13px", color: "var(--muted)" }}>
              Paste Notification / Order Text:
              <textarea
                rows={4}
                value={customText}
                onChange={(e) => setCustomText(e.target.value)}
                placeholder="Paste the official government resolution (GR), circular, or scheme guidelines here..."
                style={{ width: "100%", marginTop: "4px" }}
              />
            </label>
          </div>
        )}

        <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
          <button
            type="button"
            onClick={handleAnalyze}
            disabled={loading || (useCustom && !customText.trim())}
            style={{ minHeight: "44px", padding: "10px 20px" }}
          >
            {loading ? "Verifying Official Quotes..." : "🔍 Analyze & Check Eligibility"}
          </button>
          {error && <span style={{ color: "var(--bad)", fontSize: "13px" }}>{error}</span>}
        </div>
      </div>

      {result && (
        <div className="explainer-result" style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
          {/* Header Card */}
          <div className="card" style={{ background: "#111f18", border: "1px solid #1e452e", borderRadius: "14px", padding: "18px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "8px" }}>
              <div>
                <small style={{ color: "var(--accent)", textTransform: "uppercase", letterSpacing: ".06em", fontWeight: 700 }}>
                  {result.issuing_authority}
                </small>
                <h2 style={{ margin: "4px 0", fontSize: "20px", color: "var(--text)" }}>{result.scheme_name}</h2>
              </div>
              <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                <span className="receipt-badge"><i>✓</i> {result.quotes_verified_count} Quotes Verified</span>
                <span className="digest-code">{result.integrity_digest}</span>
              </div>
            </div>

            <p style={{ margin: "12px 0 14px", fontSize: "15px", lineHeight: "1.6", color: "#e2e8f0" }}>{result.summary}</p>

            {result.voice_script && (
              <div style={{ display: "flex", alignItems: "center", gap: "10px", background: "#172920", padding: "10px 14px", borderRadius: "8px" }}>
                <button
                  type="button"
                  className="ghost"
                  onClick={handleReadAloud}
                  style={{ background: speaking ? "var(--bad)" : "var(--accent)", color: "#111", fontWeight: 700, padding: "6px 14px" }}
                >
                  {speaking ? "■ Stop Voice" : "🔊 Listen in Your Language"}
                </button>
                <span style={{ fontSize: "13px", color: "var(--muted)" }}>Voice summary prepared for farmers</span>
              </div>
            )}
          </div>

          {/* Eligibility Section */}
          <div className="card" style={{ background: "var(--panel)", border: "1px solid var(--line)", borderRadius: "14px", padding: "16px" }}>
            <h3 style={{ margin: "0 0 12px", fontSize: "16px", color: "var(--accent)" }}>⚖️ Your Eligibility Check (पात्रता निकष)</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
              {result.eligibility.map((el, i) => (
                <div key={i} style={{ background: "#16212c", border: "1px solid var(--line)", borderRadius: "10px", padding: "12px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                    <b style={{ fontSize: "14px", color: "var(--text)" }}>{el.condition}</b>
                    <span style={{
                      fontWeight: 800,
                      fontSize: "12px",
                      padding: "2px 8px",
                      borderRadius: "6px",
                      background: el.met === "yes" ? "#12331f" : el.met === "no" ? "#3a1b1b" : "#2a2215",
                      color: el.met === "yes" ? "var(--ok)" : el.met === "no" ? "var(--bad)" : "var(--accent)"
                    }}>
                      {el.met === "yes" ? "✓ QUALIFIES (पात्र)" : el.met === "no" ? "✕ EXCLUDED (अपात्र)" : "? CHECK DETAILS"}
                    </span>
                  </div>
                  <p style={{ margin: "4px 0", fontSize: "13px", color: "#cbd5e1" }}>{el.reason}</p>
                  <blockquote style={{ margin: "8px 0 0", padding: "4px 10px", borderLeft: "3px solid var(--accent)", fontSize: "12px", color: "var(--muted)", fontStyle: "italic" }}>
                    “{el.quote}”
                  </blockquote>
                </div>
              ))}
            </div>
          </div>

          {/* Benefits & Subsidies */}
          <div className="card" style={{ background: "var(--panel)", border: "1px solid var(--line)", borderRadius: "14px", padding: "16px" }}>
            <h3 style={{ margin: "0 0 12px", fontSize: "16px", color: "var(--ok)" }}>💰 Direct Subsidies & Entitlements (अनुदान व फायदे)</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              {result.benefits.map((b) => (
                <div key={b.id} style={{ background: "#16212c", border: "1px solid var(--line)", borderRadius: "8px", padding: "10px 12px" }}>
                  <p style={{ margin: 0, fontSize: "14px", color: "var(--text)" }}><b>• {b.text}</b></p>
                  <blockquote style={{ margin: "6px 0 0", paddingLeft: "8px", borderLeft: "2px solid var(--ok)", fontSize: "12px", color: "var(--muted)" }}>
                    “{b.quote}”
                  </blockquote>
                </div>
              ))}
            </div>
          </div>

          {/* Deadlines & Required Documents */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "12px" }}>
            <div className="card" style={{ background: "var(--panel)", border: "1px solid var(--line)", borderRadius: "14px", padding: "16px" }}>
              <h3 style={{ margin: "0 0 10px", fontSize: "15px", color: "#ff8a3d" }}>⏰ Deadlines & Cutoffs (मुदत व वेळेची मर्यादा)</h3>
              {result.deadlines.map((d) => (
                <div key={d.id} style={{ marginBottom: "8px" }}>
                  <p style={{ margin: 0, fontSize: "13px", color: "var(--text)" }}>{d.text}</p>
                  <small style={{ color: "var(--muted)", display: "block", marginTop: "2px" }}>“{d.quote}”</small>
                </div>
              ))}
            </div>

            <div className="card" style={{ background: "var(--panel)", border: "1px solid var(--line)", borderRadius: "14px", padding: "16px" }}>
              <h3 style={{ margin: "0 0 10px", fontSize: "15px", color: "#7cc4ff" }}>📋 Required Documents (लागणारी कागदपत्रे)</h3>
              <ul style={{ margin: 0, paddingLeft: "18px", fontSize: "13px", color: "var(--text)" }}>
                {result.documents_required.map((doc, idx) => (
                  <li key={idx} style={{ marginBottom: "4px" }}>{doc}</li>
                ))}
              </ul>
            </div>
          </div>

          {onAsk && (
            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "8px" }}>
              <button
                type="button"
                onClick={() => onAsk(`Tell me more about how to apply for ${result.scheme_name} in my area.`)}
                style={{ background: "#15803d", color: "#fff", border: "none", padding: "10px 18px", borderRadius: "8px", fontWeight: "700", cursor: "pointer", fontSize: "13px" }}
              >
                💬 Ask Follow-up in Farm Advisory Chat →
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
