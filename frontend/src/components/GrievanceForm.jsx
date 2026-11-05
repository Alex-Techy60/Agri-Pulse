import { useState } from "react";
import { fileGrievance } from "../api.js";
import { uiText } from "../i18n.js";
import { prepareImage } from "../image.js";

const CRISIS_CATEGORIES = [
  { id: "CROP_LOSS_HAIL", icon: "🌧️", labelEn: "Hailstorm / Unseasonal Crop Loss", labelMr: "गारपीट / अवेळी पाऊस नुकसान", labelHi: "ओलावृष्टि / बेमौसम फसल नुकसान", defaultP: "P1 (72h PMFBY)" },
  { id: "TRANSFORMER_PUMP_FAILURE", icon: "⚡", labelEn: "Agri Transformer / Pump Burnout", labelMr: "रोहित्र (ट्रान्सफॉर्मर) / कृषी पंप जळाला", labelHi: "ट्रांसफार्मर / कृषि पंप खराबी", defaultP: "P2 (48h MSEDCL)" },
  { id: "CANAL_WATER_DISPUTE", icon: "🌊", labelEn: "Canal Water Dispute / Tail Block", labelMr: "कालवा पाणी अडवणूक / टेल वाद", labelHi: "नहर जल विवाद / टेल एंड रुकावट", defaultP: "P1 (24h Irrigation)" },
  { id: "SPURIOUS_SEEDS_PESTICIDE", icon: "🧪", labelEn: "Spurious Seeds / Chemical Damage", labelMr: "बनावट बियाणे / औषध फसवणूक", labelHi: "नकली बीज / कीटनाशक नुकसान", defaultP: "P1 (24h Agri Dept)" },
  { id: "ANIMAL_CROP_RAID", icon: "🐗", labelEn: "Wild Boar / Animal Crop Devastation", labelMr: "रानडुक्कर / वन्यजीव पीक नुकसान", labelHi: "जंगली जानवर द्वारा फसल बर्बादी", defaultP: "P2 (36h Forest Dept)" },
  { id: "OTHER", icon: "🌾", labelEn: "Other Urgent Farm Crisis", labelMr: "इतर तातडीची शेती समस्या", labelHi: "अन्य कृषि समस्या", defaultP: "P3 (72h Desk)" },
];

export default function GrievanceForm({ lang, profile, onGoToBoard }) {
  const t = uiText(lang);
  const [category, setCategory] = useState("CROP_LOSS_HAIL");
  const [farmerName, setFarmerName] = useState("Sunita Shinde");
  const [mobile, setMobile] = useState("9822012345");
  const [district, setDistrict] = useState("Nashik");
  const [taluka, setTaluka] = useState("Niphad");
  const [village, setVillage] = useState("Sukene");
  const [surveyNo, setSurveyNo] = useState("142/2A");
  const [crop, setCrop] = useState("Onion");
  const [affectedAcres, setAffectedAcres] = useState("2.0");
  const [description, setDescription] = useState(
    "काल संध्याकाळी अचानक गारपीट झाली. २ एकर कांद्याचे पीक जमिनीवर आडवे झाले असून सडण्याची शक्यता आहे. तातडीने पंचनामा व्हावा."
  );
  const [photo, setPhoto] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [submittedReport, setSubmittedReport] = useState(null);
  const [error, setError] = useState("");

  const handlePhotoUpload = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    try {
      const p = await prepareImage(f);
      setPhoto(p);
    } catch {
      setError("Failed to process photo. Please choose a valid image.");
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const payload = {
        farmer_name: farmerName.trim(),
        farmer_phone: mobile.trim(),
        mobile: mobile.trim(),
        place: [village.trim(), taluka.trim(), district.trim()].filter(Boolean).join(", "),
        village: village.trim(),
        taluka: taluka.trim(),
        district: district.trim(),
        survey_no: surveyNo.trim(),
        category,
        crop: crop.trim(),
        affected_acres: Number(affectedAcres) || 1.0,
        description: description.trim(),
        language: lang,
        photo_b64: photo?.b64 || null,
        damage_photo_b64: photo?.b64 || null,
      };

      const res = await fileGrievance(payload);
      setSubmittedReport(res?.report || res);
    } catch (err) {
      setError("Failed to register grievance. Please verify server connection.");
    } finally {
      setSubmitting(false);
    }
  };

  const resetForm = () => {
    setSubmittedReport(null);
    setPhoto(null);
  };

  return (
    <div className="grievance-container" style={{ display: "flex", flexDirection: "column", gap: "16px", padding: "12px 0" }}>
      {submittedReport ? (
        <div className="card" style={{ background: "var(--panel)", border: "2px solid #2ecc71", borderRadius: "14px", padding: "20px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "12px" }}>
            <span style={{ fontSize: "28px" }}>✅</span>
            <div>
              <h2 style={{ fontSize: "18px", color: "var(--ok)", margin: 0, textTransform: "none" }}>
                Farm Crisis Grievance Registered Successfully!
              </h2>
              <p style={{ margin: "2px 0 0", color: "var(--muted)", fontSize: "13px" }}>
                Official Ticket ID: <strong style={{ color: "var(--text)", fontFamily: "var(--font-mono)" }}>{submittedReport.id}</strong>
              </p>
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "12px", margin: "16px 0" }}>
            <div style={{ background: "#101820", padding: "12px", borderRadius: "10px", border: "1px solid var(--line)" }}>
              <span style={{ fontSize: "11px", color: "var(--muted)", textTransform: "uppercase" }}>Deterministic Triage</span>
              <div style={{ fontSize: "16px", fontWeight: "700", color: submittedReport.urgency === "P1" ? "#ff5d5d" : submittedReport.urgency === "P2" ? "#ff9933" : "#7cc4ff", marginTop: "4px" }}>
                🚨 {submittedReport.urgency} ({submittedReport.urgency === "P1" ? "CRITICAL PRIORITY" : submittedReport.urgency === "P2" ? "HIGH PRIORITY" : "STANDARD"})
              </div>
            </div>

            <div style={{ background: "#101820", padding: "12px", borderRadius: "10px", border: "1px solid var(--line)" }}>
              <span style={{ fontSize: "11px", color: "var(--muted)", textTransform: "uppercase" }}>SLA Deadline</span>
              <div style={{ fontSize: "15px", fontWeight: "700", color: "var(--accent)", marginTop: "4px" }}>
                ⏱️ {new Date(submittedReport.sla_deadline).toLocaleString()}
              </div>
            </div>

            <div style={{ background: "#101820", padding: "12px", borderRadius: "10px", border: "1px solid var(--line)" }}>
              <span style={{ fontSize: "11px", color: "var(--muted)", textTransform: "uppercase" }}>Assigned Department</span>
              <div style={{ fontSize: "14px", fontWeight: "600", color: "var(--text)", marginTop: "4px" }}>
                🏛️ {submittedReport.assigned_department}
              </div>
            </div>
          </div>

          <div style={{ background: "#16212c", padding: "14px", borderRadius: "10px", marginBottom: "16px", borderLeft: "4px solid var(--accent)" }}>
            <div style={{ fontSize: "12px", color: "var(--muted)", fontWeight: "600", marginBottom: "4px" }}>
              OFFICER DISPATCH SUMMARY (English Auto-Triage)
            </div>
            <div style={{ fontSize: "14px", color: "var(--text)", lineHeight: "1.5" }}>
              {submittedReport.translated_summary_en}
            </div>
          </div>

          <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
            <button
              type="button"
              onClick={onGoToBoard}
              style={{ background: "var(--accent)", color: "#111", padding: "10px 18px", borderRadius: "8px", fontWeight: "700" }}
            >
              📊 View on Public Accountability Board
            </button>
            <button
              type="button"
              onClick={resetForm}
              style={{ background: "transparent", color: "var(--text)", border: "1px solid var(--line)", padding: "10px 18px", borderRadius: "8px" }}
            >
              ➕ File Another Grievance
            </button>
          </div>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="card" style={{ background: "var(--panel)", border: "1px solid var(--line)", borderRadius: "14px", padding: "18px" }}>
          <div style={{ marginBottom: "14px" }}>
            <h2 style={{ fontSize: "18px", margin: "0 0 6px", color: "var(--text)", textTransform: "none" }}>
              🚨 Farm Crisis & Grievance Reporting (शेतकरी तक्रार निवारण)
            </h2>
            <p style={{ margin: 0, fontSize: "13px", color: "var(--muted)" }}>
              Report unseasonal crop losses, transformer burnouts, spurious seeds, or irrigation disputes. <b>Deterministic SLA triage dispatches tickets directly to designated Krishi & Electricity Officers with legally tracked response times.</b>
            </p>
          </div>

          {error && (
            <div style={{ background: "#3a1b1b", color: "#ff9b9b", padding: "10px 14px", borderRadius: "8px", fontSize: "13px", marginBottom: "12px" }}>
              {error}
            </div>
          )}

          {/* Category selection */}
          <div style={{ marginBottom: "16px" }}>
            <label style={{ display: "block", fontSize: "13px", fontWeight: "600", color: "var(--muted)", marginBottom: "8px" }}>
              1. Select Crisis Category (समस्येचा प्रकार):
            </label>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "10px" }}>
              {CRISIS_CATEGORIES.map((c) => {
                const active = category === c.id;
                return (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => setCategory(c.id)}
                    style={{
                      textAlign: "left",
                      background: active ? "#1d2b3a" : "#101820",
                      border: active ? "2px solid var(--accent)" : "1px solid var(--line)",
                      borderRadius: "10px",
                      padding: "10px 12px",
                      cursor: "pointer",
                      color: active ? "var(--text)" : "var(--muted)",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
                      <span style={{ fontSize: "20px" }}>{c.icon}</span>
                      <strong style={{ fontSize: "13px", color: active ? "var(--text)" : "var(--muted)" }}>
                        {lang === "mr" ? c.labelMr : lang === "hi" ? c.labelHi : c.labelEn}
                      </strong>
                    </div>
                    <span style={{ fontSize: "11px", color: active ? "var(--accent)" : "#6a7d92" }}>{c.defaultP}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Farmer & Location details */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "12px", marginBottom: "14px" }}>
            <label style={{ fontSize: "13px", color: "var(--muted)" }}>
              Farmer Name:
              <input
                type="text"
                value={farmerName}
                onChange={(e) => setFarmerName(e.target.value)}
                required
                style={{ width: "100%", marginTop: "4px" }}
              />
            </label>

            <label style={{ fontSize: "13px", color: "var(--muted)" }}>
              Mobile Number:
              <input
                type="text"
                value={mobile}
                onChange={(e) => setMobile(e.target.value)}
                required
                placeholder="10-digit mobile"
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
              Taluka:
              <input
                type="text"
                value={taluka}
                onChange={(e) => setTaluka(e.target.value)}
                required
                style={{ width: "100%", marginTop: "4px" }}
              />
            </label>

            <label style={{ fontSize: "13px", color: "var(--muted)" }}>
              Village (गाव):
              <input
                type="text"
                value={village}
                onChange={(e) => setVillage(e.target.value)}
                required
                style={{ width: "100%", marginTop: "4px" }}
              />
            </label>

            <label style={{ fontSize: "13px", color: "var(--muted)" }}>
              Survey / Gat No:
              <input
                type="text"
                value={surveyNo}
                onChange={(e) => setSurveyNo(e.target.value)}
                placeholder="e.g. 142/2A"
                style={{ width: "100%", marginTop: "4px" }}
              />
            </label>

            <label style={{ fontSize: "13px", color: "var(--muted)" }}>
              Crop (पीक):
              <input
                type="text"
                value={crop}
                onChange={(e) => setCrop(e.target.value)}
                placeholder="e.g. Onion, Grapes, Cotton"
                style={{ width: "100%", marginTop: "4px" }}
              />
            </label>

            <label style={{ fontSize: "13px", color: "var(--muted)" }}>
              Affected Area (Acres):
              <input
                type="number"
                step="0.1"
                min="0.1"
                value={affectedAcres}
                onChange={(e) => setAffectedAcres(e.target.value)}
                style={{ width: "100%", marginTop: "4px" }}
              />
            </label>
          </div>

          {/* Description & Photo */}
          <div style={{ marginBottom: "16px" }}>
            <label style={{ display: "block", fontSize: "13px", color: "var(--muted)", marginBottom: "6px" }}>
              Incident Description (तक्रारीचे सविस्तर वर्णन):
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={4}
              required
              style={{
                width: "100%",
                background: "var(--panel)",
                color: "var(--text)",
                border: "1px solid var(--line)",
                borderRadius: "10px",
                padding: "10px",
                font: "inherit",
                fontSize: "14px",
                lineHeight: "1.5",
              }}
            />
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "14px", flexWrap: "wrap", marginBottom: "18px" }}>
            <label className="photo" style={{ border: "1px dashed var(--line)", background: "#101820" }}>
              📷 Upload Farm Damage Photo (पुराव्यासाठी फोटो)
              <input type="file" accept="image/*" onChange={handlePhotoUpload} />
            </label>
            {photo && (
              <div style={{ display: "flex", alignItems: "center", gap: "8px", background: "#17304a", padding: "6px 10px", borderRadius: "8px", fontSize: "12px" }}>
                <span>✅ Photo attached ({photo.name})</span>
                <button
                  type="button"
                  onClick={() => setPhoto(null)}
                  style={{ background: "transparent", color: "var(--bad)", padding: "2px 6px", fontSize: "12px" }}
                >
                  ✕
                </button>
              </div>
            )}
          </div>

          <button
            type="submit"
            disabled={submitting}
            style={{
              background: "var(--accent)",
              color: "#111",
              padding: "12px 24px",
              borderRadius: "8px",
              fontSize: "15px",
              fontWeight: "700",
              cursor: submitting ? "not-allowed" : "pointer",
            }}
          >
            {submitting ? "🚨 Lodging Grievance & Triage..." : "🚨 Register Emergency Farm Grievance"}
          </button>
        </form>
      )}
    </div>
  );
}
