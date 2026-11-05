import { useState, useEffect } from "react";
import { getBoardStats, listGrievances } from "../api.js";
import { uiText } from "../i18n.js";

const CATEGORY_NAMES = {
  CROP_LOSS_HAIL: "🌧️ Hailstorm / Crop Loss",
  TRANSFORMER_PUMP_FAILURE: "⚡ Transformer / Pump Burnout",
  CANAL_WATER_DISPUTE: "🌊 Canal Water Dispute",
  SPURIOUS_SEEDS_PESTICIDE: "🧪 Spurious Seeds / Chemical",
  PEST_OUTBREAK: "🐛 Pest Outbreak",
  ANIMAL_CROP_RAID: "🐗 Animal Crop Devastation",
  OTHER: "🌾 General Farm Crisis",
};

export default function AccountabilityBoard({ lang, onReportNew, onOpenOfficerDesk }) {
  const t = uiText(lang);
  const [stats, setStats] = useState(null);
  const [reports, setReports] = useState([]);
  const [filterUrgency, setFilterUrgency] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [loading, setLoading] = useState(true);

  const loadData = async () => {
    setLoading(true);
    try {
      const [s, r] = await Promise.all([
        getBoardStats(),
        listGrievances(filterStatus, filterUrgency)
      ]);
      setStats(s);
      setReports(r);
    } catch (e) {
      // offline fallback
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [filterUrgency, filterStatus]);

  return (
    <div className="accountability-board" style={{ display: "flex", flexDirection: "column", gap: "16px", padding: "12px 0" }}>
      {/* Header bar */}
      <div className="card" style={{ background: "var(--panel)", border: "1px solid var(--line)", borderRadius: "14px", padding: "18px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "12px" }}>
          <div>
            <h2 style={{ fontSize: "18px", margin: "0 0 6px", color: "var(--text)", textTransform: "none" }}>
              📊 Public Farm Crisis Accountability Board (सार्वजनिक कृषी तक्रार फलक)
            </h2>
            <p style={{ margin: 0, fontSize: "13px", color: "var(--muted)" }}>
              Every farmer report is publicly tracked with statutory response SLA. <b>Resolutions require field panchnama proof-of-work with citizen verification.</b>
            </p>
          </div>
          <div style={{ display: "flex", gap: "8px" }}>
            <button
              type="button"
              onClick={loadData}
              style={{ background: "#101820", color: "var(--text)", border: "1px solid var(--line)", padding: "8px 14px", borderRadius: "8px", fontSize: "13px" }}
            >
              🔄 Refresh Live Data
            </button>
            <button
              type="button"
              onClick={onReportNew}
              style={{ background: "var(--accent)", color: "#111", padding: "8px 14px", borderRadius: "8px", fontSize: "13px", fontWeight: "700" }}
            >
              🚨 Report Incident
            </button>
            {onOpenOfficerDesk && (
              <button
                type="button"
                onClick={onOpenOfficerDesk}
                style={{ background: "#1c2b3a", color: "#7cc4ff", border: "1px solid #2a4365", padding: "8px 14px", borderRadius: "8px", fontSize: "13px", fontWeight: "600" }}
              >
                🏛️ Krishi Desk
              </button>
            )}
          </div>
        </div>

        {/* Top KPIs */}
        {stats && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: "12px", marginTop: "16px" }}>
            <div style={{ background: "#101820", padding: "12px", borderRadius: "10px", border: "1px solid var(--line)" }}>
              <span style={{ fontSize: "11px", color: "var(--muted)", textTransform: "uppercase" }}>Total Filed</span>
              <div style={{ fontSize: "24px", fontWeight: "800", color: "var(--text)", marginTop: "4px" }}>
                {stats.total_reports}
              </div>
            </div>

            <div style={{ background: "#101820", padding: "12px", borderRadius: "10px", border: "1px solid #6a2a2a" }}>
              <span style={{ fontSize: "11px", color: "#ff9b9b", textTransform: "uppercase" }}>Critical P1 Active</span>
              <div style={{ fontSize: "24px", fontWeight: "800", color: "#ff5d5d", marginTop: "4px" }}>
                {stats.open_critical_p1}
              </div>
            </div>

            <div style={{ background: "#101820", padding: "12px", borderRadius: "10px", border: "1px solid #1c4b2c" }}>
              <span style={{ fontSize: "11px", color: "#8be1a8", textTransform: "uppercase" }}>Resolved (Panchnama)</span>
              <div style={{ fontSize: "24px", fontWeight: "800", color: "var(--ok)", marginTop: "4px" }}>
                {stats.resolved_count}
              </div>
            </div>

            <div style={{ background: "#101820", padding: "12px", borderRadius: "10px", border: "1px solid var(--line)" }}>
              <span style={{ fontSize: "11px", color: "var(--muted)", textTransform: "uppercase" }}>SLA Compliance Rate</span>
              <div style={{ fontSize: "24px", fontWeight: "800", color: "var(--accent)", marginTop: "4px" }}>
                {stats.sla_compliance_rate_pct}%
              </div>
            </div>

            <div style={{ background: "#101820", padding: "12px", borderRadius: "10px", border: "1px solid var(--line)" }}>
              <span style={{ fontSize: "11px", color: "var(--muted)", textTransform: "uppercase" }}>Citizen Disputed</span>
              <div style={{ fontSize: "24px", fontWeight: "800", color: stats.disputed_count > 0 ? "#ff9933" : "var(--muted)", marginTop: "4px" }}>
                {stats.disputed_count}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Categories Breakdown */}
      {stats?.categories && (
        <div className="card" style={{ background: "var(--panel)", border: "1px solid var(--line)", borderRadius: "14px", padding: "16px" }}>
          <h3 style={{ fontSize: "14px", margin: "0 0 12px", color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
            Crisis Distribution by Incident Type (Nashik Agrarian Cluster)
          </h3>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "10px" }}>
            {Object.entries(stats.categories).map(([cat, count]) => {
              const pct = stats.total_reports > 0 ? Math.round((count / stats.total_reports) * 100) : 0;
              return (
                <div key={cat} style={{ background: "#101820", padding: "10px 14px", borderRadius: "8px", border: "1px solid var(--line)" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: "13px", marginBottom: "6px" }}>
                    <span>{CATEGORY_NAMES[cat] || cat}</span>
                    <strong style={{ color: "var(--accent)" }}>{count} ({pct}%)</strong>
                  </div>
                  <div style={{ height: "6px", background: "#1a2530", borderRadius: "3px", overflow: "hidden" }}>
                    <div style={{ width: `${pct}%`, height: "100%", background: "var(--accent)", borderRadius: "3px" }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Incidents Live Table */}
      <div className="card" style={{ background: "var(--panel)", border: "1px solid var(--line)", borderRadius: "14px", padding: "16px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "10px", marginBottom: "14px" }}>
          <h3 style={{ fontSize: "15px", margin: 0, color: "var(--text)" }}>
            🚨 Live Incident Hotspot Log ({reports.length} Incidents)
          </h3>

          <div style={{ display: "flex", gap: "8px" }}>
            <select
              value={filterUrgency}
              onChange={(e) => setFilterUrgency(e.target.value)}
              style={{ fontSize: "12px", padding: "6px 10px" }}
            >
              <option value="">All Urgencies</option>
              <option value="P1">🚨 P1 (Critical - 24h)</option>
              <option value="P2">⚠️ P2 (High - 48h)</option>
              <option value="P3">ℹ️ P3 (Standard)</option>
            </select>

            <select
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
              style={{ fontSize: "12px", padding: "6px 10px" }}
            >
              <option value="">All Statuses</option>
              <option value="PENDING">PENDING</option>
              <option value="TRIAGED">TRIAGED</option>
              <option value="RESOLVED">RESOLVED</option>
              <option value="DISPUTED">DISPUTED</option>
            </select>
          </div>
        </div>

        {reports.length === 0 ? (
          <div style={{ textAlign: "center", padding: "30px", color: "var(--muted)", fontSize: "14px" }}>
            No incident reports matching filters.
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "13px" }}>
              <thead>
                <tr style={{ background: "#101820", textAlign: "left", color: "var(--muted)", borderBottom: "1px solid var(--line)" }}>
                  <th style={{ padding: "10px" }}>Ticket ID</th>
                  <th style={{ padding: "10px" }}>Priority</th>
                  <th style={{ padding: "10px" }}>Location</th>
                  <th style={{ padding: "10px" }}>Category</th>
                  <th style={{ padding: "10px" }}>Department</th>
                  <th style={{ padding: "10px" }}>SLA Deadline</th>
                  <th style={{ padding: "10px" }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {reports.map((r) => {
                  const isP1 = r.urgency === "P1";
                  const isResolved = r.status === "RESOLVED";
                  const isDisputed = r.status === "DISPUTED";
                  return (
                    <tr key={r.id} style={{ borderBottom: "1px solid var(--line)", background: isP1 && !isResolved ? "#1e1416" : "transparent" }}>
                      <td style={{ padding: "10px", fontFamily: "var(--font-mono)", fontWeight: "700", color: "var(--accent)" }}>
                        {r.id}
                      </td>
                      <td style={{ padding: "10px" }}>
                        <span style={{
                          padding: "2px 8px",
                          borderRadius: "99px",
                          fontSize: "11px",
                          fontWeight: "700",
                          background: isP1 ? "#3a1b1b" : r.urgency === "P2" ? "#3a2a10" : "#1d2b3a",
                          color: isP1 ? "#ff9b9b" : r.urgency === "P2" ? "var(--accent)" : "#7cc4ff",
                        }}>
                          {r.urgency}
                        </span>
                      </td>
                      <td style={{ padding: "10px", color: "var(--text)" }}>
                        {r.place}
                      </td>
                      <td style={{ padding: "10px" }}>
                        {CATEGORY_NAMES[r.category] || r.category}
                      </td>
                      <td style={{ padding: "10px", color: "var(--muted)", fontSize: "12px" }}>
                        {r.assigned_department}
                      </td>
                      <td style={{ padding: "10px", fontSize: "12px", color: isP1 ? "#ff9b9b" : "var(--muted)" }}>
                        {(() => {
                          const dt = r.sla_deadline ? new Date(r.sla_deadline) : r.created_at ? new Date(new Date(r.created_at).getTime() + (r.sla_deadline_hours || 48) * 3600000) : null;
                          return dt && !isNaN(dt.getTime())
                            ? dt.toLocaleDateString([], { month: "short", day: "numeric" }) + " " + dt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
                            : `Within ${r.sla_deadline_hours || 48}h`;
                        })()}
                      </td>
                      <td style={{ padding: "10px" }}>
                        <span style={{
                          padding: "3px 8px",
                          borderRadius: "4px",
                          fontSize: "11px",
                          fontWeight: "700",
                          background: isResolved ? "#12331f" : isDisputed ? "#3a1b1b" : "#1f2a37",
                          color: isResolved ? "var(--ok)" : isDisputed ? "#ff5d5d" : "var(--text)",
                        }}>
                          {isResolved ? "✓ RESOLVED" : isDisputed ? "⚠ DISPUTED" : r.status}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
