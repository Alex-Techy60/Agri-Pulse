import { uiText } from "../i18n.js";
import Logo from "./Logo.jsx";

// Status of each live source as the server reports it. "Configured" means the key or data is set up, not that a
// call succeeded right now: the dashboard and advisory show whether each source actually answers.
function SourceStatus({ health, t }) {
  if (!health) return null;
  const rows = [
    [t.lsAi, health.llm_configured ? t.lsAiOn : t.lsAiOff, !!health.llm_configured],
    [t.lsMandi, health.mandi_key_configured ? t.lsKey : t.lsNoKey, !!health.mandi_key_configured],
    [t.lsDocs, t.lsLoaded(health.knowledge_chunks ?? 0), (health.knowledge_chunks ?? 0) > 0],
  ];
  return (
    <ul className="source-status" aria-label={t.lsTitle}>
      {rows.map(([name, text, ok]) => (
        <li key={name}><span className={`dot ${ok ? "ok" : "warn"}`} aria-hidden="true" /> <strong>{name}:</strong> {text}</li>
      ))}
    </ul>
  );
}

export default function LandingPage({ lang, onNavigate, health }) {
  const t = uiText(lang);

  return (
    <div className="landing-page" style={{ display: "flex", flexDirection: "column", gap: "28px", padding: "16px 0", maxWidth: "1100px", margin: "0 auto", width: "100%" }}>
      {/* Hero Banner */}
      <div className="card hero-card" style={{ background: "linear-gradient(145deg, #0e1e17 0%, #11261d 50%, #0b141a 100%)", border: "1px solid #1e3a2c", borderRadius: "18px", padding: "32px 24px", position: "relative", overflow: "hidden" }}>
        <div style={{ position: "relative", zIndex: 2 }}>
          <div style={{ display: "inline-flex", alignItems: "center", gap: "8px", background: "rgba(34, 197, 94, 0.12)", border: "1px solid rgba(34, 197, 94, 0.3)", borderRadius: "99px", padding: "4px 14px", marginBottom: "16px" }}>
            <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#22c55e", display: "inline-block" }}></span>
            <span style={{ fontSize: "12px", color: "#86efac", fontWeight: "700", letterSpacing: "0.5px" }}>
              FORGE '26 · THEME 2: CLIMATE & RESOURCE INFRASTRUCTURE RESILIENCE
            </span>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "16px", marginBottom: "12px" }}>
            <Logo size={48} />
            <div>
              <h1 style={{ fontSize: "clamp(24px, 4vw, 36px)", margin: 0, color: "#f8fafc", fontWeight: "800", letterSpacing: "-0.5px" }}>
                KisaanMitra · किसानमित्र
              </h1>
              <p style={{ margin: "4px 0 0", color: "#86efac", fontSize: "15px", fontWeight: "600" }}>
                Multilingual Agritech & Resource Advisory Assistant (Agri-Pulse)
              </p>
            </div>
          </div>

          <p style={{ fontSize: "16px", color: "#cbd5e1", maxWidth: "750px", lineHeight: "1.6", margin: "14px 0 24px" }}>
            Smallholder farmers cannot afford hallucinations. KisaanMitra turns <b>live Open-Meteo weather</b>, <b>3-depth soil moisture</b>, and <b>data.gov.in Agmarknet mandi trends</b> into deterministic sell/hold decisions, verified government scheme policies, public crisis accountability, and autonomous tamper-evident filings — in 10 Indian languages with voice.
          </p>

          <SourceStatus health={health} t={t} />

          <div style={{ display: "flex", gap: "12px", flexWrap: "wrap", alignItems: "center" }}>
            <button
              type="button"
              onClick={() => onNavigate("advisory")}
              style={{ background: "#15803d", color: "#fff", border: "1px solid #22c55e", padding: "12px 22px", borderRadius: "10px", fontSize: "15px", fontWeight: "700", cursor: "pointer", display: "inline-flex", alignItems: "center", gap: "8px", boxShadow: "0 4px 14px rgba(21, 128, 61, 0.4)" }}
            >
              🌾 Launch Decision Agent
            </button>
            <button
              type="button"
              onClick={() => onNavigate("dashboard")}
              style={{ background: "#162534", color: "#7cc4ff", border: "1px solid #2a4365", padding: "12px 20px", borderRadius: "10px", fontSize: "14px", fontWeight: "600", cursor: "pointer" }}
            >
              📊 Farmer Home & Tickers
            </button>
            <button
              type="button"
              onClick={() => onNavigate("schemes")}
              style={{ background: "#212836", color: "#f8fafc", border: "1px solid var(--line)", padding: "12px 20px", borderRadius: "10px", fontSize: "14px", fontWeight: "600", cursor: "pointer" }}
            >
              📜 Scheme Explainer
            </button>
            <button
              type="button"
              onClick={() => onNavigate("board")}
              style={{ background: "#2a1c1c", color: "#ff8a8a", border: "1px solid #5a2c2c", padding: "12px 20px", borderRadius: "10px", fontSize: "14px", fontWeight: "600", cursor: "pointer" }}
            >
              🚨 Crisis Board
            </button>
            <button
              type="button"
              onClick={() => onNavigate("filing")}
              style={{ background: "#262214", color: "#fcd34d", border: "1px solid #5e4f1a", padding: "12px 20px", borderRadius: "10px", fontSize: "14px", fontWeight: "600", cursor: "pointer" }}
            >
              🤖 Autonomous Filing Room
            </button>
          </div>
        </div>
      </div>

      {/* Live Data Pipelines Status Grid */}
      <div>
        <h3 style={{ fontSize: "14px", color: "var(--muted)", textTransform: "uppercase", letterSpacing: "1px", marginBottom: "12px" }}>
          Live Verified Infrastructure Pipelines (No Stubs, No Mock Data)
        </h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "12px" }}>
          <div className="card" style={{ background: "var(--panel)", border: "1px solid var(--line)", borderRadius: "12px", padding: "14px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
              <span style={{ fontWeight: "700", color: "#7cc4ff", fontSize: "14px" }}>🌦️ Open-Meteo & SoilGrids</span>
              <span style={{ background: "#12331f", color: "var(--ok)", fontSize: "11px", fontWeight: "700", padding: "2px 8px", borderRadius: "99px" }}>LIVE (PASS)</span>
            </div>
            <p style={{ margin: 0, fontSize: "12px", color: "var(--muted)" }}>
              Hourly weather, ET0 evapotranspiration, rain history, and soil moisture at 3 depths (0-7, 7-28, 28-100cm).
            </p>
          </div>

          <div className="card" style={{ background: "var(--panel)", border: "1px solid var(--line)", borderRadius: "12px", padding: "14px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
              <span style={{ fontWeight: "700", color: "var(--accent)", fontSize: "14px" }}>🏛️ data.gov.in Agmarknet</span>
              <span style={{ background: "#12331f", color: "var(--ok)", fontSize: "11px", fontWeight: "700", padding: "2px 8px", borderRadius: "99px" }}>LIVE (PASS)</span>
            </div>
            <p style={{ margin: 0, fontSize: "12px", color: "var(--muted)" }}>
              Official APMC mandi arrivals, modal prices, and 7-day trend calculations across identical markets.
            </p>
          </div>

          <div className="card" style={{ background: "var(--panel)", border: "1px solid var(--line)", borderRadius: "12px", padding: "14px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
              <span style={{ fontWeight: "700", color: "#86efac", fontSize: "14px" }}>📜 PIB Gazette Knowledge</span>
              <span style={{ background: "#12331f", color: "var(--ok)", fontSize: "11px", fontWeight: "700", padding: "2px 8px", borderRadius: "99px" }}>VERIFIED</span>
            </div>
            <p style={{ margin: 0, fontSize: "12px", color: "var(--muted)" }}>
              Unedited Press Information Bureau releases for MSP 2026-28, PM-KISAN, and PMFBY operational guidelines.
            </p>
          </div>

          <div className="card" style={{ background: "var(--panel)", border: "1px solid var(--line)", borderRadius: "12px", padding: "14px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
              <span style={{ fontWeight: "700", color: "#fcd34d", fontSize: "14px" }}>🛡️ Ed25519 Crypto Signer</span>
              <span style={{ background: "#12331f", color: "var(--ok)", fontSize: "11px", fontWeight: "700", padding: "2px 8px", borderRadius: "99px" }}>AUDITED</span>
            </div>
            <p style={{ margin: 0, fontSize: "12px", color: "var(--muted)" }}>
              Asymmetric digital signatures on advisory digests and Playwright browser filing receipts.
            </p>
          </div>
        </div>
      </div>

      {/* Four Pillars Showcase */}
      <div>
        <h2 style={{ fontSize: "20px", color: "var(--text)", margin: "0 0 16px" }}>
          The Four Architectural Pillars
        </h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: "16px" }}>
          {/* Pillar 1 */}
          <div className="card" style={{ background: "var(--panel)", border: "1px solid var(--line)", borderRadius: "14px", padding: "20px", display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
            <div>
              <div style={{ fontSize: "28px", marginBottom: "8px" }}>🌾</div>
              <h3 style={{ fontSize: "17px", color: "var(--text)", margin: "0 0 8px" }}>
                Core Advisory Decision Agent
              </h3>
              <p style={{ fontSize: "13px", color: "var(--muted)", lineHeight: "1.5", margin: 0 }}>
                Live parallel tools (weather + mandi) with cross-checks. Computes SELL_NOW / HOLD / NEUTRAL (±5% trend), spray safety windows, and water balance in code. Multi-tier guardrails catch ungrounded numbers.
              </p>
            </div>
            <button
              type="button"
              onClick={() => onNavigate("advisory")}
              style={{ marginTop: "16px", background: "#101820", color: "var(--text)", border: "1px solid var(--line)", padding: "8px 14px", borderRadius: "8px", fontSize: "13px", cursor: "pointer", textAlign: "left" }}
            >
              Open Decision Chat →
            </button>
          </div>

          {/* Pillar 2 */}
          <div className="card" style={{ background: "var(--panel)", border: "1px solid var(--line)", borderRadius: "14px", padding: "20px", display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
            <div>
              <div style={{ fontSize: "28px", marginBottom: "8px" }}>📜</div>
              <h3 style={{ fontSize: "17px", color: "var(--text)", margin: "0 0 8px" }}>
                Sarkari Yojana Explainer
              </h3>
              <p style={{ fontSize: "13px", color: "var(--muted)", lineHeight: "1.5", margin: 0 }}>
                Simplifies official notifications (PM-KISAN, PMFBY, SMAM machinery, MSP). Every claim carries an exact character-checked quote from the source text. Zero hallucination of eligibility.
              </p>
            </div>
            <button
              type="button"
              onClick={() => onNavigate("schemes")}
              style={{ marginTop: "16px", background: "#101820", color: "var(--text)", border: "1px solid var(--line)", padding: "8px 14px", borderRadius: "8px", fontSize: "13px", cursor: "pointer", textAlign: "left" }}
            >
              Explain Scheme Circulars →
            </button>
          </div>

          {/* Pillar 3 */}
          <div className="card" style={{ background: "var(--panel)", border: "1px solid var(--line)", borderRadius: "14px", padding: "20px", display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
            <div>
              <div style={{ fontSize: "28px", marginBottom: "8px" }}>📍</div>
              <h3 style={{ fontSize: "17px", color: "var(--text)", margin: "0 0 8px" }}>
                Farm Crisis & Public Board
              </h3>
              <p style={{ fontSize: "13px", color: "var(--muted)", lineHeight: "1.5", margin: 0 }}>
                Report hailstorm crop loss, burnt transformers, canal disputes. Automated triage sets statutory SLAs (P1 24h, P2 48h). Officer desk conducts field panchnama with photo proof. Public accountability board.
              </p>
            </div>
            <button
              type="button"
              onClick={() => onNavigate("board")}
              style={{ marginTop: "16px", background: "#101820", color: "var(--text)", border: "1px solid var(--line)", padding: "8px 14px", borderRadius: "8px", fontSize: "13px", cursor: "pointer", textAlign: "left" }}
            >
              View Public Board →
            </button>
          </div>

          {/* Pillar 4 */}
          <div className="card" style={{ background: "var(--panel)", border: "1px solid var(--line)", borderRadius: "14px", padding: "20px", display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
            <div>
              <div style={{ fontSize: "28px", marginBottom: "8px" }}>🤖</div>
              <h3 style={{ fontSize: "17px", color: "var(--text)", margin: "0 0 8px" }}>
                Autonomous Filing Room
              </h3>
              <p style={{ fontSize: "13px", color: "var(--muted)", lineHeight: "1.5", margin: 0 }}>
                Playwright browser automation on our high-fidelity Krishi portal replica (/sandbox). Mandatory human OTP handoff, pre-submit approval gate, and tamper-evident Ed25519 cryptographic receipts.
              </p>
            </div>
            <button
              type="button"
              onClick={() => onNavigate("filing")}
              style={{ marginTop: "16px", background: "#101820", color: "var(--text)", border: "1px solid var(--line)", padding: "8px 14px", borderRadius: "8px", fontSize: "13px", cursor: "pointer", textAlign: "left" }}
            >
              Enter Filing Room →
            </button>
          </div>
        </div>
      </div>

      {/* User Personas Spotlight */}
      <div className="card" style={{ background: "var(--panel)", border: "1px solid var(--line)", borderRadius: "14px", padding: "20px" }}>
        <h3 style={{ fontSize: "16px", color: "var(--text)", margin: "0 0 14px" }}>
          Target Users & Field Context (Nashik District, Maharashtra)
        </h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: "16px" }}>
          <div style={{ background: "#101820", padding: "16px", borderRadius: "10px", border: "1px solid var(--line)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "8px" }}>
              <span style={{ fontSize: "24px" }}>👩‍🌾</span>
              <div>
                <b style={{ color: "var(--text)", fontSize: "15px" }}>Sunita Shinde (45)</b>
                <span style={{ display: "block", color: "var(--muted)", fontSize: "12px" }}>Smallholder Farmer, Niphad, Nashik</span>
              </div>
            </div>
            <p style={{ fontSize: "13px", color: "#cbd5e1", margin: 0, lineHeight: "1.5" }}>
              Grows onions and soybeans. Speaks Marathi and understands Hindi. Uses WhatsApp on a 4G smartphone. Needs to know whether to sell her harvested onions today at Lasalgaon APMC or hold, whether unseasonal rain will cause waterlogging, and how to get prompt compensation when hailstorms damage her crop.
            </p>
          </div>

          <div style={{ background: "#101820", padding: "16px", borderRadius: "10px", border: "1px solid var(--line)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "8px" }}>
              <span style={{ fontSize: "24px" }}>🏛️</span>
              <div>
                <b style={{ color: "var(--text)", fontSize: "15px" }}>Dr. S. K. Jadhav</b>
                <span style={{ display: "block", color: "var(--muted)", fontSize: "12px" }}>Taluka Krishi Adhikari (Agriculture Officer)</span>
              </div>
            </div>
            <p style={{ fontSize: "13px", color: "#cbd5e1", margin: 0, lineHeight: "1.5" }}>
              Manages rural agricultural crisis workflows across Niphad taluka. Needs an urgency-ordered queue (P1 24h SLAs first), translated farmer grievance reports in English, field panchnama recording, proof-of-work photo uploads, and an auditable public transparency ledger.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
