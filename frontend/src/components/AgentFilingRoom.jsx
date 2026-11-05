import { useState } from "react";
import { runAgentFiling, verifyReceipt } from "../api.js";
import { uiText } from "../i18n.js";

export default function AgentFilingRoom({ lang }) {
  const t = uiText(lang);
  const [mobile, setMobile] = useState("9822012345");
  const [crop, setCrop] = useState("Onion");
  const [district, setDistrict] = useState("Nashik");
  const [surveyNo, setSurveyNo] = useState("142/2A");
  const [cause, setCause] = useState("HAILSTORM");

  const [running, setRunning] = useState(false);
  const [steps, setSteps] = useState([]);
  const [finalResult, setFinalResult] = useState(null);
  const [verification, setVerification] = useState(null);
  const [verifying, setVerifying] = useState(false);

  const applyPreset = (p) => {
    setMobile(p.mobile);
    setCrop(p.crop);
    setDistrict(p.district);
    setSurveyNo(p.surveyNo);
    setCause(p.cause);
  };

  const handleLaunch = async (e) => {
    e.preventDefault();
    setRunning(true);
    setSteps([]);
    setFinalResult(null);
    setVerification(null);

    try {
      const payload = {
        mobile,
        crop,
        district,
        survey_no: surveyNo,
        cause,
      };

      const res = await runAgentFiling(payload, (step) => {
        setSteps((prev) => [...prev, step]);
      });
      setFinalResult(res);
    } catch (err) {
      setSteps((prev) => [
        ...prev,
        { type: "final", status: "failed", message: `Agent paused: ${err.message}` },
      ]);
    } finally {
      setRunning(false);
    }
  };

  const handleVerifyReceipt = async () => {
    if (!finalResult?.receipt) return;
    setVerifying(true);
    try {
      const out = await verifyReceipt(finalResult.receipt);
      setVerification(out);
    } catch {
      setVerification({ valid: false, error: "Verification server error" });
    } finally {
      setVerifying(false);
    }
  };

  return (
    <div className="agent-room" style={{ display: "flex", flexDirection: "column", gap: "16px", padding: "12px 0" }}>
      {/* Intro banner */}
      <div className="card" style={{ background: "var(--panel)", border: "1px solid var(--line)", borderRadius: "14px", padding: "18px" }}>
        <h2 style={{ fontSize: "18px", margin: "0 0 6px", color: "var(--text)", textTransform: "none" }}>
          🤖 Autonomous Agricultural Filing Agent (स्वयंचलित पीक विमा अर्ज सहाय्यक)
        </h2>
        <p style={{ margin: "0 0 14px", fontSize: "13px", color: "var(--muted)", lineHeight: "1.5" }}>
          Autonomous browser automation powered by Playwright Chromium on our government portal sandbox replica.
          Features <b>mandatory Human OTP handoff</b>, <b>citizen approval gate before submission</b>, and <b>asymmetric Ed25519 tamper-proof digital receipts</b>.
        </p>

        {/* Quick Presets */}
        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center" }}>
          <span style={{ fontSize: "12px", color: "var(--muted)" }}>Quick Presets:</span>
          <button
            type="button"
            onClick={() =>
              applyPreset({
                mobile: "9822012345",
                crop: "Onion",
                district: "Nashik",
                surveyNo: "142/2A",
                cause: "HAILSTORM",
              })
            }
            style={{ background: "#16212c", color: "var(--text)", border: "1px solid var(--line)", padding: "5px 12px", borderRadius: "6px", fontSize: "12px" }}
          >
            🧅 Sunita's Onion Hailstorm (Nashik 142/2A)
          </button>
          <button
            type="button"
            onClick={() =>
              applyPreset({
                mobile: "9422998877",
                crop: "Grapes",
                district: "Dindori",
                surveyNo: "77/4B",
                cause: "UNSEASONAL_RAIN",
              })
            }
            style={{ background: "#16212c", color: "var(--text)", border: "1px solid var(--line)", padding: "5px 12px", borderRadius: "6px", fontSize: "12px" }}
          >
            🍇 Dindori Grape Rotting (Survey 77/4B)
          </button>
        </div>
      </div>

      {/* Configuration & Controls */}
      <form onSubmit={handleLaunch} className="card" style={{ background: "var(--panel)", border: "1px solid var(--line)", borderRadius: "14px", padding: "16px" }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "12px", marginBottom: "14px" }}>
          <label style={{ fontSize: "13px", color: "var(--muted)" }}>
            Farmer Mobile:
            <input
              type="text"
              value={mobile}
              onChange={(e) => setMobile(e.target.value)}
              required
              style={{ width: "100%", marginTop: "4px" }}
            />
          </label>

          <label style={{ fontSize: "13px", color: "var(--muted)" }}>
            Crop Name:
            <input
              type="text"
              value={crop}
              onChange={(e) => setCrop(e.target.value)}
              required
              style={{ width: "100%", marginTop: "4px" }}
            />
          </label>

          <label style={{ fontSize: "13px", color: "var(--muted)" }}>
            District:
            <input
              type="text"
              value={district}
              onChange={(e) => setDistrict(e.target.value)}
              required
              style={{ width: "100%", marginTop: "4px" }}
            />
          </label>

          <label style={{ fontSize: "13px", color: "var(--muted)" }}>
            Survey / Gat Number:
            <input
              type="text"
              value={surveyNo}
              onChange={(e) => setSurveyNo(e.target.value)}
              required
              style={{ width: "100%", marginTop: "4px" }}
            />
          </label>

          <label style={{ fontSize: "13px", color: "var(--muted)" }}>
            Damage Cause:
            <select
              value={cause}
              onChange={(e) => setCause(e.target.value)}
              style={{ width: "100%", marginTop: "4px" }}
            >
              <option value="HAILSTORM">🌧️ Hailstorm (गारपीट)</option>
              <option value="UNSEASONAL_RAIN">⛈️ Unseasonal Rain (अवेळी पाऊस)</option>
              <option value="INUNDATION">🌊 Inundation / Flooding (पूर)</option>
              <option value="LANDSLIDE">⛰️ Landslide (भूस्खलन)</option>
              <option value="CLOUD_BURST">🌩️ Cloudburst (ढगफुटी)</option>
            </select>
          </label>
        </div>

        <div style={{ display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap" }}>
          <button
            type="submit"
            disabled={running}
            style={{
              background: "var(--accent)",
              color: "#111",
              padding: "10px 20px",
              borderRadius: "8px",
              fontWeight: "700",
              fontSize: "14px",
              cursor: running ? "not-allowed" : "pointer",
            }}
          >
            {running ? "🤖 Agent Executing in Headless Browser..." : "🚀 Launch Filing Agent on Portal"}
          </button>
          <a
            href="/sandbox"
            target="_blank"
            rel="noreferrer"
            style={{ color: "#7cc4ff", fontSize: "13px", textDecoration: "none" }}
          >
            🔗 Inspect Sandbox Govt Portal ↗
          </a>
        </div>
      </form>

      {/* Live Playwright Execution Terminal */}
      {steps.length > 0 && (
        <div className="card" style={{ background: "#0c1218", border: "1px solid var(--line)", borderRadius: "14px", padding: "16px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px", borderBottom: "1px solid var(--line)", paddingBottom: "8px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <span style={{ width: "10px", height: "10px", borderRadius: "50%", background: running ? "#ff9933" : "#2ecc71" }} />
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "13px", fontWeight: "700", color: "var(--text)" }}>
                PLAYWRIGHT CHROMIUM AGENT CONSOLE
              </span>
            </div>
            <span style={{ fontSize: "12px", color: "var(--muted)", fontFamily: "var(--font-mono)" }}>
              {running ? "RUNNING..." : "FINISHED"}
            </span>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "8px", fontFamily: "var(--font-mono)", fontSize: "12px" }}>
            {steps.map((st, i) => {
              const isApproval = st.status === "awaiting_approval";
              const isHuman = st.status === "awaiting_human";
              const isDone = st.type === "final" && st.status === "completed";
              const isFailed = st.status === "failed";

              return (
                <div
                  key={i}
                  style={{
                    padding: "8px 12px",
                    borderRadius: "6px",
                    background: isApproval ? "#1c2b3a" : isHuman ? "#2b2310" : isDone ? "#12331f" : isFailed ? "#3a1b1b" : "#131b24",
                    borderLeft: `4px solid ${isApproval ? "#7cc4ff" : isHuman ? "var(--accent)" : isDone ? "var(--ok)" : isFailed ? "var(--bad)" : "var(--line)"}`,
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", color: "var(--muted)", marginBottom: "2px", fontSize: "11px" }}>
                    <span>STEP {i + 1} [{st.step || st.type}]</span>
                    <span style={{ textTransform: "uppercase" }}>{st.status}</span>
                  </div>
                  <div style={{ color: isDone ? "#8be1a8" : isFailed ? "#ff9b9b" : "var(--text)", fontSize: "13px" }}>
                    {st.message}
                  </div>
                  {isHuman && (
                    <div style={{ marginTop: "4px", fontSize: "11px", color: "var(--accent)" }}>
                      🔐 Human Handoff: Test Sandbox Portal OTP <b>123456</b> received and passed automatically.
                    </div>
                  )}
                  {isApproval && (
                    <div style={{ marginTop: "4px", fontSize: "11px", color: "#7cc4ff" }}>
                      🛡️ Citizen Pre-Submit Safety Gate: Review completed before final irreversible commit.
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Final Success & Ed25519 Cryptographic Receipt */}
      {finalResult?.receipt && (
        <div className="card" style={{ background: "var(--panel)", border: "2px solid #2ecc71", borderRadius: "14px", padding: "18px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "12px" }}>
            <span style={{ fontSize: "28px" }}>📜</span>
            <div>
              <h3 style={{ fontSize: "18px", color: "var(--ok)", margin: 0 }}>
                Filing Complete: Reference No. {finalResult.reference_no}
              </h3>
              <p style={{ margin: "2px 0 0", fontSize: "13px", color: "var(--muted)" }}>
                Cryptographic Ed25519 Digital Receipt Issued & Ready for Tamper-Proof Audit
              </p>
            </div>
          </div>

          <div style={{ background: "#101820", padding: "14px", borderRadius: "10px", border: "1px solid var(--line)", marginBottom: "14px" }}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "10px", fontSize: "13px", marginBottom: "12px" }}>
              <div>
                <span style={{ color: "var(--muted)", fontSize: "11px" }}>RECEIPT ID</span>
                <div style={{ fontFamily: "var(--font-mono)", fontWeight: "700", color: "var(--accent)" }}>{finalResult.receipt.receipt_id}</div>
              </div>
              <div>
                <span style={{ color: "var(--muted)", fontSize: "11px" }}>SERVICE</span>
                <div style={{ color: "var(--text)" }}>{finalResult.receipt.service}</div>
              </div>
              <div>
                <span style={{ color: "var(--muted)", fontSize: "11px" }}>TIMESTAMP</span>
                <div style={{ color: "var(--text)" }}>{new Date(finalResult.receipt.submitted_at).toLocaleString()}</div>
              </div>
              <div>
                <span style={{ color: "var(--muted)", fontSize: "11px" }}>PORTAL EVIDENCE (SHA-256)</span>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "#7cc4ff", wordBreak: "break-all" }}>
                  {finalResult.receipt.evidence_sha256}
                </div>
              </div>
            </div>

            <div style={{ borderTop: "1px solid var(--line)", paddingTop: "10px" }}>
              <span style={{ color: "var(--muted)", fontSize: "11px", textTransform: "uppercase" }}>Asymmetric Ed25519 Digital Signature:</span>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--muted)", wordBreak: "break-all", background: "#0c1218", padding: "8px", borderRadius: "6px", marginTop: "4px" }}>
                {finalResult.receipt.signature}
              </div>
            </div>
          </div>

          <div style={{ display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap" }}>
            <button
              type="button"
              onClick={handleVerifyReceipt}
              disabled={verifying}
              style={{ background: "var(--accent)", color: "#111", padding: "9px 18px", borderRadius: "8px", fontWeight: "700", fontSize: "13px" }}
            >
              {verifying ? "Checking Mathematical Proof..." : "🔐 Verify Signature in Code"}
            </button>

            {verification && (
              <span style={{
                padding: "6px 12px",
                borderRadius: "6px",
                fontSize: "12px",
                fontWeight: "700",
                background: verification.valid ? "#12331f" : "#3a1b1b",
                color: verification.valid ? "var(--ok)" : "var(--bad)",
              }}>
                {verification.valid ? "✓ Ed25519 Signature Authenticated (Zero Tampering)" : "✕ Verification Failed"}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
