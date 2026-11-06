from __future__ import annotations
import threading
from app.grievance.models import FarmCrisisReport, FarmCrisisIn
from app.grievance.triage import triage_crisis

_LOCK = threading.Lock()
_REPORTS: dict[str, FarmCrisisReport] = {}
_COUNTER = 100


def create_report(inp: FarmCrisisIn) -> FarmCrisisReport:
    global _COUNTER
    with _LOCK:
        _COUNTER += 1
        rep_id = f"KISAN-2026-{_COUNTER:04d}"
        rep = triage_crisis(inp, rep_id)
        _REPORTS[rep_id] = rep
        return rep

def list_reports(status: str | None = None, urgency: str | None = None) -> list[FarmCrisisReport]:
    with _LOCK:
        reps = list(_REPORTS.values())
        if status:
            reps = [r for r in reps if r.status == status]
        if urgency:
            reps = [r for r in reps if r.urgency == urgency]
        # Order by urgency (P1 first, then P2, P3) then newest
        prio = {"P1": 1, "P2": 2, "P3": 3}
        return sorted(reps, key=lambda x: (prio.get(x.urgency, 9), x.id), reverse=False)

def get_report(report_id: str) -> FarmCrisisReport | None:
    with _LOCK:
        return _REPORTS.get(report_id)

def resolve_report(report_id: str, officer_name: str, notes: str, proof_url: str | None = None) -> FarmCrisisReport | None:
    with _LOCK:
        rep = _REPORTS.get(report_id)
        if not rep:
            return None
        rep.status = "RESOLVED"
        rep.resolution_notes = f"{officer_name}: {notes}"
        rep.resolution_proof_url = proof_url or None  # no invented evidence: unproven resolutions stay unproven
        return rep

def citizen_feedback(report_id: str, confirmed: bool) -> FarmCrisisReport | None:
    with _LOCK:
        rep = _REPORTS.get(report_id)
        if not rep:
            return None
        rep.citizen_confirmed = confirmed
        if not confirmed:
            rep.status = "DISPUTED"
        return rep

def get_board_stats() -> dict:
    with _LOCK:
        all_reps = list(_REPORTS.values())
        total = len(all_reps)
        open_p1 = len([r for r in all_reps if r.urgency == "P1" and r.status != "RESOLVED"])
        resolved = len([r for r in all_reps if r.status == "RESOLVED"])
        disputed = len([r for r in all_reps if r.status == "DISPUTED"])
        
        # Categorical counts
        by_category: dict[str, int] = {}
        for r in all_reps:
            by_category[r.category] = by_category.get(r.category, 0) + 1

        sla_compliant_pct = round((resolved / total * 100), 1) if total > 0 else 100.0

        return {
            "total_reports": total,
            "open_critical_p1": open_p1,
            "resolved_count": resolved,
            "disputed_count": disputed,
            "sla_compliance_rate_pct": sla_compliant_pct,
            "categories": by_category,
            "hotspots": [
                {
                    "id": r.id,
                    "lat": r.lat,
                    "lon": r.lon,
                    "category": r.category,
                    "place": r.place,
                    "urgency": r.urgency,
                    "status": r.status
                }
                for r in all_reps
            ]
        }
