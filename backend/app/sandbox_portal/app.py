from __future__ import annotations
import random
from fastapi import FastAPI, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

sandbox_app = FastAPI(title="Sarkari Agri Portal Sandbox Replica")

# In-memory test state
_LAST_OTP = "123456"
_CONFIG = {
    "test_mode": True,
    "captcha_code": "7KQ2M"
}

@sandbox_app.get("/")
def root():
    return RedirectResponse(url="/sandbox/login")

@sandbox_app.get("/__sms")
def read_sms():
    """Citizens or automated test harness can read the last sent SMS OTP here."""
    return {"latest_sms": f"Your Krishi DBT Portal OTP is: {_LAST_OTP}. Valid for 10 minutes. Do not share with anyone."}

@sandbox_app.get("/login", response_class=HTMLResponse)
def login_page():
    return HTMLResponse(content="""<!doctype html>
<html>
<head><title>Krishi Portal Replica</title><style>body{font-family:sans-serif;padding:24px;background:#f8fafc;} .banner{background:#fff3cd;padding:10px;border:1px solid #ffeeba;border-radius:6px;margin-bottom:16px;} .card{background:#fff;padding:20px;border-radius:8px;max-width:400px;border:1px solid #e2e8f0;}</style></head>
<body>
<div class="banner">⚠️ <b>SANDBOX REPLICA</b> — Simulated Indian Agriculture Portal for Safe Demonstrations.</div>
<div class="card">
  <h2>Farmer Sign-In</h2>
  <form action="/sandbox/login/send-otp" method="post">
    <label>Mobile Number: <input type="tel" name="mobile" required placeholder="10-digit mobile" style="width:100%;padding:8px;margin:8px 0;"></label>
    <button type="submit" style="background:#2e7d32;color:#fff;border:none;padding:10px 16px;border-radius:6px;cursor:pointer;">Send OTP</button>
  </form>
</div>
</body></html>""")

@sandbox_app.post("/login/send-otp", response_class=HTMLResponse)
def send_otp(mobile: str = Form(...)):
    global _LAST_OTP
    _LAST_OTP = "123456" if _CONFIG["test_mode"] else f"{random.randint(100000, 999999)}"
    return HTMLResponse(content=f"""<!doctype html>
<html><head><style>body{{font-family:sans-serif;padding:24px;background:#f8fafc;}} .card{{background:#fff;padding:20px;border-radius:8px;max-width:400px;border:1px solid #e2e8f0;}}</style></head><body>
<div class="card">
  <h2>Enter OTP</h2>
  <p>OTP sent to {mobile[:3]}••••{mobile[-3:]}. (Test Mode OTP: <b>{_LAST_OTP}</b>)</p>
  <form action="/sandbox/login/verify" method="post">
    <input type="hidden" name="mobile" value="{mobile}">
    <label>6-Digit OTP: <input type="text" name="otp" required maxlength="6" style="width:100%;padding:8px;margin:8px 0;"></label>
    <button type="submit" id="btn-verify-otp" style="background:#2e7d32;color:#fff;border:none;padding:10px 16px;border-radius:6px;cursor:pointer;">Verify & Proceed</button>
  </form>
</div></body></html>""")

@sandbox_app.post("/login/verify", response_class=HTMLResponse)
def verify_otp(mobile: str = Form(...), otp: str = Form(...)):
    if otp != _LAST_OTP:
        return HTMLResponse(content="""<div style="color:red;padding:20px;">Invalid OTP. <a href="/sandbox/login">Try again</a></div>""", status_code=400)
    return HTMLResponse(content=f"""<!doctype html>
<html><head><style>body{{font-family:sans-serif;padding:24px;background:#f8fafc;}} .card{{background:#fff;padding:20px;border-radius:8px;max-width:550px;border:1px solid #e2e8f0;}} label{{display:block;margin:10px 0 4px;font-weight:600;}} input, select, textarea{{width:100%;padding:8px;box-sizing:border-box;}}</style></head><body>
<div class="card">
  <h2>PMFBY Localized Crop Loss Claim</h2>
  <p>Logged in: <b>{mobile[:3]}••••{mobile[-3:]}</b></p>
  <form action="/sandbox/insurance/review" method="post">
    <label>State</label><input type="text" name="state" value="Maharashtra" readonly>
    <label>District</label><input type="text" name="district" value="Nashik" required>
    <label>Affected Crop</label><input type="text" name="crop" value="Onion" required>
    <label>Survey / Gat Number</label><input type="text" name="survey_no" placeholder="e.g. 142/2A" required>
    <label>Cause of Loss</label>
    <select name="cause"><option value="HAILSTORM">Hailstorm (गारपीट)</option><option value="INUNDATION">Inundation / Flooding</option><option value="PEST_ATTACK">Severe Pest Infestation</option></select>
    <label>Estimated Crop Damage %</label><input type="number" name="loss_pct" min="10" max="100" value="65" required>
    <label>Security CAPTCHA: <b style="background:#ddd;padding:2px 8px;letter-spacing:2px;">{_CONFIG['captcha_code']}</b></label>
    <input type="text" name="captcha" required placeholder="Type CAPTCHA here">
    <br><br>
    <button type="submit" id="btn-proceed-review" style="background:#1565c0;color:#fff;border:none;padding:10px 18px;border-radius:6px;cursor:pointer;">Proceed to Final Review</button>
  </form>
</div></body></html>""")

@sandbox_app.post("/insurance/review", response_class=HTMLResponse)
def review_claim(state: str = Form(...), district: str = Form(...), crop: str = Form(...), survey_no: str = Form(...), cause: str = Form(...), loss_pct: str = Form(...), captcha: str = Form(...)):
    if captcha.strip().upper() != _CONFIG["captcha_code"]:
        return HTMLResponse(content="""<div style="color:red;padding:20px;">Invalid CAPTCHA. Nothing filed. <a href="javascript:history.back()">Go back</a></div>""", status_code=400)
    return HTMLResponse(content=f"""<!doctype html>
<html><head><style>body{{font-family:sans-serif;padding:24px;background:#f8fafc;}} .card{{background:#fff;padding:24px;border-radius:8px;max-width:550px;border:2px solid #2e7d32;}} table{{width:100%;border-collapse:collapse;}} td{{padding:8px;border-bottom:1px solid #eee;}}</style></head><body>
<div class="card">
  <h2>Review Crop Loss Intimation</h2>
  <p style="color:#d32f2f;"><b>CITIZEN APPROVAL REQUIRED</b>: The agent will not submit this form without your explicit approval.</p>
  <table>
    <tr><td><b>State & District:</b></td><td>{state}, {district}</td></tr>
    <tr><td><b>Crop:</b></td><td>{crop}</td></tr>
    <tr><td><b>Survey Number:</b></td><td>{survey_no}</td></tr>
    <tr><td><b>Calamity Cause:</b></td><td>{cause}</td></tr>
    <tr><td><b>Reported Damage:</b></td><td>{loss_pct}%</td></tr>
  </table>
  <br>
  <form action="/sandbox/insurance/submit" method="post">
    <input type="hidden" name="crop" value="{crop}">
    <input type="hidden" name="district" value="{district}">
    <input type="hidden" name="cause" value="{cause}">
    <button type="submit" id="btn-final-submit" style="background:#2e7d32;color:#fff;border:none;padding:12px 22px;border-radius:6px;font-weight:700;cursor:pointer;">Submit Crop Loss Claim</button>
  </form>
</div></body></html>""")

@sandbox_app.post("/insurance/submit", response_class=HTMLResponse)
def submit_claim(crop: str = Form(...), district: str = Form(...), cause: str = Form(...)):
    ref_num = f"PMFBY/MH/2026/{random.randint(100000, 999999)}"
    return HTMLResponse(content=f"""<!doctype html>
<html><head><style>body{{font-family:sans-serif;padding:24px;background:#f8fafc;}} .card{{background:#fff;padding:24px;border-radius:8px;max-width:550px;border:2px solid #2e7d32;text-align:center;}}</style></head><body>
<div class="card">
  <h1 style="color:#2e7d32;">✓ Application Successfully Filed</h1>
  <p>Your localized crop loss intimation for <b>{crop}</b> in <b>{district}</b> has been registered.</p>
  <div style="background:#e8f5e9;padding:12px;border-radius:8px;margin:16px 0;font-size:20px;font-family:monospace;font-weight:bold;">
    Reference No: {ref_num}
  </div>
  <p style="font-size:13px;color:#555;">Joint inspection panchnama will be conducted by Agriculture Officer within 10 days.</p>
</div></body></html>""")
