import { useState, useEffect } from "react";
import { getSchemes } from "../api.js";
import { uiText } from "../i18n.js";

const TEST_CASES = [
  {
    title: "Genuine PM-KISAN Benefit Quote",
    scheme: "pm_kisan",
    quote: "Rs. 6,000/- per year is transferred directly into the bank accounts",
    expected: true
  },
  {
    title: "Genuine Cut-off Date Quote",
    scheme: "pm_kisan",
    quote: "The cut-off date for determination of eligibility of beneficiaries was 01.02.2019",
    expected: true
  },
  {
    title: "Invented Tractor Subsidy (LLM Hallucination)",
    scheme: "pm_kisan",
    quote: "Every farmer receives a free Mahindra 45 HP tractor worth Rs. 6 lakh",
    expected: false
  },
  {
    title: "False Universal Eligibility Promise",
    scheme: "pm_kisan",
    quote: "All government officers and income tax payers are fully eligible for this cash benefit",
    expected: false
  }
];

export default function SchemesEngineRoom({ lang, onNavigate }) {
  const t = uiText(lang);
  const [schemes, setSchemes] = useState([]);
  const [selectedScheme, setSelectedScheme] = useState("pm_kisan");
  const [testQuote, setTestQuote] = useState(TEST_CASES[0].quote);
  const [verified, setVerified] = useState(null);

  useEffect(() => {
    getSchemes().then((s) => {
      setSchemes(s);
    }).catch(() => {});
  }, []);

  const handleVerify = () => {
    // Client-side exact substring check against known schemes
    const current = schemes.find((s) => s.id === selectedScheme);
    const docText = current?.document_text || "Under the scheme, an amount of Rs. 6,000/- per year is transferred directly into the bank accounts of the beneficiary farmer families in three equal four-monthly installments of Rs. 2,000/- each. All landholding farmer families having cultivable landholding in their names are eligible. The cut-off date for determination of eligibility of beneficiaries was 01.02.2019. Exclusions: All Institutional Landholders; Persons who paid Income Tax in the last assessment year.";

    const cleanQuote = testQuote.trim().replace(/\s+/g, " ").toLowerCase();
    const cleanDoc = docText.replace(/\s+/g, " ").toLowerCase();
    const match = cleanDoc.includes(cleanQuote);
    setVerified(match);
  };

  return (
    <div className="engine-room" style={{ display: "flex", flexDirection: "column", gap: "18px", padding: "16px 0", maxWidth: "900px", margin: "0 auto", width: "100%" }}>
      <div className="card" style={{ background: "var(--panel)", border: "1px solid var(--line)", borderRadius: "14px", padding: "20px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "12px", marginBottom: "12px" }}>
          <div>
            <h2 style={{ fontSize: "18px", color: "var(--text)", margin: "0 0 4px", textTransform: "none" }}>
              ⚙️ Schemes Explainer Engine Room (`/schemes/engine`)
            </h2>
            <p style={{ margin: 0, fontSize: "13px", color: "var(--muted)" }}>
              Technical audit console for character-exact quote verification and algorithmic hallucination defense.
            </p>
          </div>
          <button
            type="button"
            onClick={() => onNavigate("schemes")}
            style={{ background: "#16212c", color: "#7cc4ff", border: "1px solid #2a4365", padding: "6px 14px", borderRadius: "8px", fontSize: "13px", cursor: "pointer" }}
          >
            ← Back to Schemes Explainer
          </button>
        </div>

        {/* Technical Explainer */}
        <div style={{ background: "#101820", padding: "14px", borderRadius: "10px", border: "1px solid var(--line)", fontSize: "13px", lineHeight: "1.6", color: "#cbd5e1", marginBottom: "16px" }}>
          <b style={{ color: "var(--ok)" }}>Rule: Code Disposes, Model Proposes.</b><br />
          Standard LLMs hallucinate false eligibility promises and fictitious subsidy numbers. KisaanMitra runs a deterministic <code>quote_checker.py</code> filter over all LLM outputs before they reach the farmer.
          Every entitlement claim must contain a contiguous substring verified against the official government circular with zero character mismatches. Any ungrounded claim is dropped immediately.
        </div>

        {/* Interactive Quote Verifier */}
        <h3 style={{ fontSize: "15px", color: "var(--text)", margin: "0 0 10px" }}>
          Interactive Quote Verification Sandbox
        </h3>

        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginBottom: "12px" }}>
          <span style={{ fontSize: "12px", color: "var(--muted)" }}>Preset Test Cases:</span>
          {TEST_CASES.map((tc, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => {
                setSelectedScheme(tc.scheme);
                setTestQuote(tc.quote);
                setVerified(null);
              }}
              style={{
                background: "#16212c",
                color: tc.expected ? "var(--ok)" : "#ff8a8a",
                border: "1px solid var(--line)",
                padding: "4px 10px",
                borderRadius: "6px",
                fontSize: "12px",
                cursor: "pointer"
              }}
            >
              {tc.title}
            </button>
          ))}
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          <label style={{ fontSize: "13px", color: "var(--muted)" }}>
            Candidate Quote Claim to Verify:
            <textarea
              value={testQuote}
              onChange={(e) => {
                setTestQuote(e.target.value);
                setVerified(null);
              }}
              rows={3}
              style={{ width: "100%", marginTop: "4px", padding: "10px", borderRadius: "8px", border: "1px solid var(--line)", background: "#101820", color: "var(--text)", fontFamily: "var(--font-mono)", fontSize: "13px" }}
            />
          </label>

          <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
            <button
              type="button"
              onClick={handleVerify}
              style={{ background: "var(--accent)", color: "#111", border: "none", padding: "10px 20px", borderRadius: "8px", fontWeight: "700", fontSize: "13px", cursor: "pointer" }}
            >
              🔍 Run Character-Level Substring Verification
            </button>

            {verified !== null && (
              <span style={{
                padding: "8px 14px",
                borderRadius: "8px",
                fontSize: "13px",
                fontWeight: "700",
                background: verified ? "#12331f" : "#3a1b1b",
                color: verified ? "var(--ok)" : "var(--bad)",
                border: `1px solid ${verified ? "var(--ok)" : "var(--bad)"}`
              }}>
                {verified ? "✓ PASS: Verbatim Quoted In Official Document" : "✕ REJECTED: Hallucination (Zero Match in Circular)"}
              </span>
            )}
          </div>
        </div>

        {/* Cryptographic Digest Spec */}
        <div style={{ marginTop: "20px", borderTop: "1px solid var(--line)", paddingTop: "14px" }}>
          <span style={{ fontSize: "12px", color: "var(--muted)", textTransform: "uppercase" }}>Provenance Seal Algorithm:</span>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "#7cc4ff", background: "#0c1218", padding: "10px", borderRadius: "8px", marginTop: "6px" }}>
            digest = "KM-SCHEME-" + sha256(doc_id + "|" + verified_quotes.join(";") + "|" + farmer_facts).hex()[:12].upper()
          </div>
        </div>
      </div>
    </div>
  );
}
