from __future__ import annotations
import asyncio
import hashlib
from datetime import datetime, timezone
from typing import AsyncGenerator
from playwright.async_api import async_playwright
from app.executor.receipts import sign_receipt

# Human gates: the runner pauses at each one until the farmer answers via POST /api/agent/file/{task_id}/gate.
# Futures live on the event loop that runs the filing, so the route handler resolves them in the same loop.
OTP_TIMEOUT_S = 300.0
GATE_TIMEOUT_S = 300.0
_GATES: dict[str, dict[str, asyncio.Future]] = {}


def submit_gate(task_id: str, gate: str, value) -> bool:
    """Answer a pending gate ("otp" with the code, "approve" with True/False). False if nothing is waiting."""
    fut = _GATES.get(task_id, {}).get(gate)
    if fut is None or fut.done():
        return False
    fut.set_result(value)
    return True


def _open_gate(task_id: str, gate: str) -> asyncio.Future:
    """Register the waiting future BEFORE the runner yields the 'awaiting' event, so an answer sent as soon as
    the event arrives is never lost."""
    fut = asyncio.get_running_loop().create_future()
    _GATES.setdefault(task_id, {})[gate] = fut
    return fut


async def _wait_gate(task_id: str, gate: str, fut: asyncio.Future, timeout: float):
    try:
        return await asyncio.wait_for(fut, timeout)
    finally:
        _GATES.get(task_id, {}).pop(gate, None)


class FilingRunner:
    def __init__(self, sandbox_base_url: str = "http://127.0.0.1:8000/sandbox"):
        self.base_url = sandbox_base_url

    async def execute_crop_loss_filing(
        self,
        task_id: str,
        mobile: str,
        crop: str,
        district: str,
        survey_no: str,
        cause: str = "HAILSTORM"
    ) -> AsyncGenerator[dict, None]:
        """Runs the deterministic crop loss filing route on the sandbox replica with human handoff, approval, and signed receipt."""
        start_time = datetime.now(timezone.utc).isoformat()
        yield {"type": "event", "step": "init", "message": "Starting autonomous browser agent...", "status": "running"}

        async with async_playwright() as p:
            # Launch Chromium in headless mode
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(viewport={"width": 1280, "height": 720})
            page = await context.new_page()

            try:
                # Step 1: Navigate to portal login
                yield {"type": "event", "step": "nav", "message": f"Navigating to Krishi Portal: {self.base_url}/login", "status": "running"}
                await page.goto(f"{self.base_url}/login", wait_until="networkidle")

                # Step 2: Fill mobile and request OTP
                yield {"type": "event", "step": "mobile_submit", "message": f"Entering farmer mobile: {mobile[:3]}••••{mobile[-3:]}", "status": "running"}
                await page.fill("input[name='mobile']", mobile)
                await page.click("button[type='submit']")
                await page.wait_for_load_state("networkidle")

                # Step 3: Human Handoff (OTP)
                otp_gate = _open_gate(task_id, "otp")
                yield {
                    "type": "event",
                    "step": "human_needed",
                    "kind": "otp",
                    "message": "Portal sent an OTP to the farmer's mobile. Waiting for the farmer to enter it.",
                    "status": "awaiting_human"
                }
                try:
                    otp = str(await _wait_gate(task_id, "otp", otp_gate, OTP_TIMEOUT_S))
                except asyncio.TimeoutError:
                    yield {"type": "final", "status": "failed", "error": "otp_timeout",
                           "message": "No OTP entered in time. Filing stopped; nothing was submitted."}
                    return
                await page.fill("input[name='otp']", otp)
                await page.click("#btn-verify-otp")
                await page.wait_for_load_state("networkidle")
                if await page.locator("input[name='district']").count() == 0:
                    yield {"type": "final", "status": "failed", "error": "otp_rejected",
                           "message": "The portal rejected the OTP. Filing stopped; nothing was submitted."}
                    return

                # Step 4: Fill localized crop loss claim form
                yield {"type": "event", "step": "form_fill", "message": f"Filling damage details: {crop} in {district}, Survey {survey_no}", "status": "running"}
                await page.fill("input[name='district']", district)
                await page.fill("input[name='crop']", crop)
                await page.fill("input[name='survey_no']", survey_no)
                await page.select_option("select[name='cause']", cause)
                await page.fill("input[name='captcha']", "7KQ2M")

                # Step 5: Proceed to Review page
                await page.click("#btn-proceed-review")
                await page.wait_for_load_state("networkidle")

                # Step 6: Approval Gate (Human in the loop)
                approve_gate = _open_gate(task_id, "approve")
                yield {
                    "type": "event",
                    "step": "approval_needed",
                    "message": f"Review page reached. Ready to lodge official claim for {crop} ({cause}) on Survey {survey_no}. Waiting for the farmer's approval.",
                    "status": "awaiting_approval"
                }
                try:
                    approved = bool(await _wait_gate(task_id, "approve", approve_gate, GATE_TIMEOUT_S))
                except asyncio.TimeoutError:
                    approved = False
                if not approved:
                    yield {"type": "final", "status": "declined", "error": "not_approved",
                           "message": "The farmer did not approve. Nothing was submitted."}
                    return

                # Step 7: Final Submit click
                yield {"type": "event", "step": "submitting", "message": "Farmer approved. Executing final submission...", "status": "submitting"}
                await page.click("#btn-final-submit")
                await page.wait_for_load_state("networkidle")

                # Step 8: Verify outcome & extract the reference number the portal actually printed.
                # Never substitute a placeholder: if none is found, the filing did not verifiably complete.
                content = await page.content()
                import re
                match = re.search(r"PMFBY/MH/2026/\d+", content)
                if not match:
                    yield {"type": "final", "status": "failed", "error": "no_reference",
                           "message": "The portal did not show a reference number. Treat this filing as NOT registered; check the portal."}
                    return
                ref_num = match.group(0)

                # Step 9: Take snapshot evidence
                evidence_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

                # Step 10: Sign receipt using Ed25519
                unsigned_receipt = {
                    "receipt_id": f"REC-{task_id[:8].upper()}",
                    "task_id": task_id,
                    "portal": "PMFBY National Crop Insurance Sandbox",
                    "service": "Localized Crop Loss Claim Intimation",
                    "reference_no": ref_num,
                    "crop": crop,
                    "district": district,
                    "survey_no": survey_no,
                    "submitted_at": datetime.now(timezone.utc).isoformat(),
                    "evidence_sha256": evidence_hash
                }
                signed = sign_receipt(unsigned_receipt)

                yield {
                    "type": "final",
                    "status": "completed",
                    "reference_no": ref_num,
                    "receipt": signed,
                    "message": f"Successfully registered! Official Reference No: {ref_num}"
                }

            except Exception as e:
                yield {
                    "type": "final",
                    "status": "failed",
                    "error": str(e),
                    "message": f"Filing paused: {e}"
                }
            finally:
                await browser.close()
