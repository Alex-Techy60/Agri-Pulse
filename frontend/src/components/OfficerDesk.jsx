import { useState, useEffect } from "react";
import { listGrievances, resolveGrievance, sendGrievanceFeedback } from "../api.js";
import { uiText } from "../i18n.js";
import { prepareImage } from "../image.js";

export default function OfficerDesk({ lang, onGoToBoard }) {
  const t = uiText(lang);
  const [reports, setReports] = useState([]);
  const [selectedReport, setSelectedReport] = useState(null);
  const [officerName, setOfficerName] = useState("Dr. S. K. Jadhav (Taluka Krishi Adhikari, Niphad)");
  const [resolutionNotes, setResolutionNotes] = useState(
    "Joint field inspection (पंचनामा) completed with Revenue Talathi. 75% crop lodging verified due to hailstorm. PMFBY claim intimation registered with insurance surveyor."
  );
  const [proofPhoto, setProofPhoto] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [feedbackStatus, setFeedbackStatus] = useState({});
  const [filter, setFilter] = useState("ALL"); // ALL, P1, OPEN, RESOLVED

  const refreshList = async () => {
    try {
      const data = await listGrievances();
      setReports(data);
      if (selectedReport) {
        const updated = data.find((r) => r.id === selectedReport.id);
        if (updated) setSelectedReport(updated);
      }
    } catch (e) {
      // offline
    }
  };

  useEffect(() => {
    refreshList();
  }, []);

  const handleProofPhoto = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    try {
      const p = await prepareImage(f);
      setProofPhoto(p);
    } catch {}
  };

  const handleResolve = async (e) => {
    e.preventDefault();
    if (!selectedReport) return;
    setSubmitting(true);
    try {
      await resolveGrievance(selectedReport.id, {
        officer_name: officerName,
        resolution_notes: resolutionNotes,
        proof_photo_b64: proofPhoto?.b64 || "data:image/jpeg;base64,mock_panchnama_proof",
      });
      await refreshList();
    } catch (e) {
      alert("Resolution failed. Please check connection.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleFarmerFeedback = async (id, confirmed) => {
    try {
      await sendGrievanceFeedback(id, confirmed);
      setFeedbackStatus((prev) => ({ ...prev, [id]: confirmed ? "CONFIRMED" : "DISPUTED" }));
      await refreshList();
    } catch (e) {
      alert("Feedback update failed.");
    }
  };

  const filteredReports = reports.filter((r) => {
    if (filter === "P1") return r.urgency === "P1";
    if (filter === "OPEN") return r.status !== "RESOLVED";
    if (filter === "RESOLVED") return r.status === "RESOLVED";
    return true;
  });

  return (
    <div className="officer-desk" style={{ display: "flex", flexDirection: "column", gap: "16px", padding: "12px 0" }}>
      {/* Officer Header */}
      <div className="card" style={{ background: "var(--panel)", border: "1px solid var(--line)", borderRadius: "14px", padding: "18px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "12px" }}>
          <div>
            <h2 style={{ fontSize: "18px", margin: "0 0 6px", color: "var(--text)", textTransform: "none" }}>
              🏛️ Krishi Officer & Nodal Desk (कृषी व महावितरण अधिकारी कक्ष)
            </h2>
            <p style={{ margin: 0, fontSize: "13px", color: "var(--muted)" }}>
              Authenticated officer console to triage farmer complaints, conduct field panchnama, and upload proof-of-work before SLA expiration.
            </p>
          </div>

          <div style={{ display: "flex", gap: "8px" }}>
            {onGoToBoard && (
              <button
                type="button"
                onClick={onGoToBoard}
                style={{ background: "#1c2b3a", color: "#7cc4ff", border: "1px solid #2a4365", padding: "8px 14px", borderRadius: "8px", fontSize: "13px", fontWeight: "600" }}
              >
                📊 Public Board
              </button>
            )}
            <button
              type="button"
              onClick={refreshList}
              style={{ background: "#101820", color: "var(--text)", border: "1px solid var(--line)", padding: "8px 14px", borderRadius: "8px", fontSize: "13px" }}
            >
              🔄 Refresh Queue
            </button>
          </div>
        </div>

        {/* Filter Pills */}
        <div style={{ display: "flex", gap: "8px", marginTop: "14px", flexWrap: "wrap" }}>
          {[
            { id: "ALL", label: `All Incidents (${reports.length})` },
            { id: "P1", label: `🚨 Urgent P1 (${reports.filter((r) => r.urgency === "P1").length})` },
            { id: "OPEN", label: `⏳ Open / In-Progress (${reports.filter((r) => r.status !== "RESOLVED").length})` },
            { id: "RESOLVED", label: `✓ Resolved (${reports.filter((r) => r.status === "RESOLVED").length})` },
          ].map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setFilter(item.id)}
              style={{
                background: filter === item.id ? "var(--accent)" : "#101820",
                color: filter === item.id ? "#111" : "var(--muted)",
                border: "1px solid var(--line)",
                padding: "6px 12px",
                borderRadius: "20px",
                fontSize: "12px",
                fontWeight: "600",
                cursor: "pointer",
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      {/* Main Two-Column Layout */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "16px" }}>
        {/* Left: Queue List */}
        <div className="card" style={{ background: "var(--panel)", border: "1px solid var(--line)", borderRadius: "14px", padding: "14px", maxHeight: "680px", overflowY: "auto" }}>
          <h3 style={{ fontSize: "14px", margin: "0 0 12px", color: "var(--muted)", textTransform: "uppercase" }}>
            Assigned Queue ({filteredReports.length})
          </h3>

          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            {filteredReports.map((r) => {
              const selected = selectedReport?.id === r.id;
              const isP1 = r.urgency === "P1";
              const isResolved = r.status === "RESOLVED";

              return (
                <div
                  key={r.id}
                  onClick={() => setSelectedReport(r)}
                  style={{
                    background: selected ? "#1d2b3a" : "#101820",
                    border: selected ? "2px solid var(--accent)" : isP1 && !isResolved ? "1px solid #6a2a2a" : "1px solid var(--line)",
                    borderRadius: "10px",
                    padding: "12px",
                    cursor: "pointer",
                    transition: "all 0.15s ease",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: "12px", fontWeight: "700", color: "var(--accent)" }}>
                      {r.id}
                    </span>
                    <span style={{
                      padding: "2px 8px",
                      borderRadius: "99px",
                      fontSize: "11px",
                      fontWeight: "700",
                      background: isP1 ? "#3a1b1b" : "#3a2a10",
                      color: isP1 ? "#ff9b9b" : "var(--accent)",
                    }}>
                      {r.urgency} ({r.urgency === "P1" ? "24h SLA" : "48h SLA"})
                    </span>
                  </div>

                  <div style={{ fontSize: "14px", fontWeight: "600", color: "var(--text)", marginBottom: "4px" }}>
                    {r.farmer_name} • {r.place}
                  </div>

                  <div style={{ fontSize: "12px", color: "var(--muted)", marginBottom: "6px", display: "flex", gap: "10px" }}>
                    <span>🌾 {r.crop || "Kharif Crop"}</span>
                    <span>📞 {r.farmer_phone || r.farmer_phone_masked || "Confidential"}</span>
                  </div>

                  <div style={{ fontSize: "12px", color: isResolved ? "var(--ok)" : "#ff9b9b" }}>
                    Status: <strong>{isResolved ? "✓ RESOLVED" : (() => {
                      const dt = r.sla_deadline ? new Date(r.sla_deadline) : r.created_at ? new Date(new Date(r.created_at).getTime() + (r.sla_deadline_hours || 48) * 3600000) : null;
                      return dt && !isNaN(dt.getTime())
                        ? `⏳ SLA Target: ${dt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`
                        : `⏳ SLA: ${r.sla_deadline_hours || 48}h`;
                    })()}</strong>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right: Inspection & Action Card */}
        <div className="card" style={{ background: "var(--panel)", border: "1px solid var(--line)", borderRadius: "14px", padding: "16px" }}>
          {selectedReport ? (
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "14px" }}>
                <div>
                  <div style={{ fontSize: "11px", color: "var(--muted)", textTransform: "uppercase" }}>Incident File</div>
                  <h3 style={{ fontSize: "18px", margin: "2px 0 0", color: "var(--text)" }}>
                    {selectedReport.id} — {selectedReport.farmer_name}
                  </h3>
                </div>
                <span style={{
                  padding: "4px 10px",
                  borderRadius: "6px",
                  fontSize: "12px",
                  fontWeight: "700",
                  background: selectedReport.status === "RESOLVED" ? "#12331f" : "#3a1b1b",
                  color: selectedReport.status === "RESOLVED" ? "var(--ok)" : "#ff9b9b",
                }}>
                  {selectedReport.status}
                </span>
              </div>

              {/* Farmer's Original Language Complaint */}
              <div style={{ background: "#101820", padding: "12px", borderRadius: "8px", border: "1px solid var(--line)", marginBottom: "12px" }}>
                <div style={{ fontSize: "11px", color: "var(--muted)", fontWeight: "600", marginBottom: "4px" }}>
                  FARMER'S ORIGINAL STATEMENT ({selectedReport.language?.toUpperCase() || "MR"})
                </div>
                <div style={{ fontSize: "13px", color: "var(--text)", lineHeight: "1.5", fontStyle: "italic" }}>
                  "{selectedReport.description}"
                </div>
              </div>I can copy everything into phase2_results/rescore_5000/ and re-run the analysis if you want.

              {/* Triage English Summary */}
              <div style={{ background: "#16212c", padding: "12px", borderRadius: "8px", borderLeft: "4px solid var(--accent)", marginBottom: "14px" }}>
                <div style={{ fontSize: "11px", color: "var(--muted)", fontWeight: "600", marginBottom: "4px" }}>
                  DETERMINISTIC AUTO-TRIAGE BRIEF (FOR HIGHER AUTHORITIES)
                </div>
                <div style={{ fontSize: "13px", color: "var(--text)", lineHeight: "1.5" }}>
                  {selectedReport.translated_summary_en}
                </div>
              </div>

              {/* Action Form: Panchnama Proof of Work */}
              {selectedReport.status === "RESOLVED" ? (
                <div style={{ background: "#12331f", padding: "16px", borderRadius: "10px", border: "1px solid #1c4b2c" }}>
                  <div style={{ fontSize: "14px", fontWeight: "700", color: "var(--ok)", marginBottom: "8px" }}>
                    ✓ Panchnama & Proof-of-Work Logged
                  </div>
                  <div style={{ fontSize: "13px", color: "var(--text)", marginBottom: "10px" }}>
                    {selectedReport.resolution_notes}
                  </div>
                  <div style={{ fontSize: "11px", color: "var(--muted)", marginBottom: "14px" }}>
                    Proof Document: <code style={{ color: "#7cc4ff" }}>{selectedReport.resolution_proof_url}</code>
                  </div>

                  {/* Citizen Feedback simulation */}
                  <div style={{ borderTop: "1px solid #1c4b2c", paddingTop: "12px", marginTop: "12px" }}>
                    <div style={{ fontSize: "12px", color: "var(--muted)", marginBottom: "8px" }}>
                      Farmer Accountability Gate (Citizen Confirmation):
                    </div>
                    {selectedReport.citizen_confirmed === true ? (
                      <div style={{ color: "var(--ok)", fontSize: "13px", fontWeight: "600" }}>
                        ✅ Farmer confirmed resolution in field.
                      </div>
                    ) : selectedReport.citizen_confirmed === false ? (
                      <div style={{ color: "var(--bad)", fontSize: "13px", fontWeight: "600" }}>
                        ⚠️ Farmer disputed resolution! Ticket reopened for appellate review.
                      </div>
                    ) : (
                      <div style={{ display: "flex", gap: "8px" }}>
                        <button
                          type="button"
                          onClick={() => handleFarmerFeedback(selectedReport.id, true)}
                          style={{ background: "var(--ok)", color: "#111", fontSize: "12px", padding: "6px 12px", borderRadius: "6px" }}
                        >
                          👍 Simulate Farmer Confirm
                        </button>
                        <button
                          type="button"
                          onClick={() => handleFarmerFeedback(selectedReport.id, false)}
                          style={{ background: "#3a1b1b", color: "#ff9b9b", border: "1px solid #6a2a2a", fontSize: "12px", padding: "6px 12px", borderRadius: "6px" }}
                        >
                          👎 Simulate Farmer Dispute
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <form onSubmit={handleResolve} style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                  <div style={{ fontSize: "13px", fontWeight: "700", color: "var(--text)" }}>
                    Lodge Official Resolution & Panchnama:
                  </div>

                  <label style={{ fontSize: "12px", color: "var(--muted)" }}>
                    Officer Name & Designation:
                    <input
                      type="text"
                      value={officerName}
                      onChange={(e) => setOfficerName(e.target.value)}
                      required
                      style={{ width: "100%", marginTop: "4px" }}
                    />
                  </label>

                  <label style={{ fontSize: "12px", color: "var(--muted)" }}>
                    Field Panchnama Notes / Action Report:
                    <textarea
                      value={resolutionNotes}
                      onChange={(e) => setResolutionNotes(e.target.value)}
                      rows={3}
                      required
                      style={{ width: "100%", background: "#101820", color: "var(--text)", border: "1px solid var(--line)", borderRadius: "8px", padding: "8px", fontSize: "13px" }}
                    />
                  </label>

                  <label className="photo" style={{ border: "1px dashed var(--line)", background: "#101820", fontSize: "12px" }}>
                    📷 Upload Inspection Photo / Signed Panchnama
                    <input type="file" accept="image/*" onChange={handleProofPhoto} />
                  </label>

                  <button
                    type="submit"
                    disabled={submitting}
                    style={{
                      background: "var(--ok)",
                      color: "#111",
                      padding: "10px 18px",
                      borderRadius: "8px",
                      fontWeight: "700",
                      fontSize: "14px",
                      marginTop: "4px",
                    }}
                  >
                    {submitting ? "Logging Panchnama..." : "✓ Sign & Close Incident with Proof"}
                  </button>
                </form>
              )}
            </div>
          ) : (
            <div style={{ textAlign: "center", padding: "40px 20px", color: "var(--muted)", fontSize: "14px" }}>
              👈 Select a crisis ticket from the queue on the left to inspect and conduct field panchnama.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
