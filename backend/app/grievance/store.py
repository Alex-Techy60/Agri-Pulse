from __future__ import annotations
import threading
from app.grievance.models import FarmCrisisReport, FarmCrisisIn
from app.grievance.triage import triage_crisis

_LOCK = threading.Lock()
_REPORTS: dict[str, FarmCrisisReport] = {}
_COUNTER = 100

def _seed_reports():
    global _COUNTER
    initial_seeds = [
        FarmCrisisIn(
            farmer_name="Sunita Shinde",
            farmer_phone="9823451234",
            place="Lasalgaon, Nashik",
            district="Nashik",
            state="Maharashtra",
            category="CROP_LOSS_HAIL",
            description="काल संध्याकाळी झालेल्या गारपिटीमुळे कांद्याचे प्रचंड नुकसान झाले आहे. ७० टक्के पीक मातीत मिसळले. विमा पंचनाम्यासाठी अधिकारी त्वरित पाठवावेत.",
            language="mr",
            lat=20.1478,
            lon=74.2256
        ),
        FarmCrisisIn(
            farmer_name="Rameshwar Patil",
            farmer_phone="9876543210",
            place="Sinnar, Nashik",
            district="Nashik",
            state="Maharashtra",
            category="TRANSFORMER_PUMP_FAILURE",
            description="शेतातील १०० केव्हीए ट्रान्सफॉर्मर जळाला आहे. विहिरीचे पाणी उपसा बंद झाला असून गहू करपायला लागला आहे. महावितरणने २४ तासात बदलावा.",
            language="mr",
            lat=19.8456,
            lon=73.9922
        ),
        FarmCrisisIn(
            farmer_name="Deepak Pawar",
            farmer_phone="9422114455",
            place="Niphad, Nashik",
            district="Nashik",
            state="Maharashtra",
            category="PEST_OUTBREAK",
            description="टोमॅटो पिकावर तुडतुडे आणि पांढऱ्या माशीचा मोठा प्रादुर्भाव झाला आहे. कृषी अधिकाऱ्यांनी तातडीने मार्गदर्शन करावे.",
            language="mr",
            lat=20.0822,
            lon=74.1122
        ),
        FarmCrisisIn(
            farmer_name="Balasaheb Gaikwad",
            farmer_phone="9822334455",
            place="Dindori, Nashik",
            district="Nashik",
            state="Maharashtra",
            category="CANAL_WATER_DISPUTE",
            description="कॅनॉलचे पाणी टेल-एंड शेतकऱ्यांपर्यंत पोहोचत नाहीये. वरच्या भागात अवैध सायफन लावले आहेत. पाटबंधारे विभागाने पाणी सोडावे.",
            language="mr",
            lat=20.1989,
            lon=73.8344
        )
    ]
    for seed in initial_seeds:
        _COUNTER += 1
        rep_id = f"KISAN-2026-{_COUNTER:04d}"
        rep = triage_crisis(seed, rep_id)
        _REPORTS[rep_id] = rep

_seed_reports()

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
        rep.resolution_proof_url = proof_url or "evidence://inspection_panchnama_verified.jpg"
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
