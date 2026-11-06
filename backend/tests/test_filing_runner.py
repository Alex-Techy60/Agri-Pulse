"""End-to-end test of the Playwright autonomous filing runner against the sandbox replica."""
import threading
import time
import pytest
import uvicorn
from app.main import app
from app.executor.runner import FilingRunner, submit_gate
from app.executor.receipts import verify_receipt


@pytest.fixture(scope="module")
def sandbox_server():
    """Runs FastAPI in a local thread so Playwright can navigate to /sandbox."""
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8999, log_level="error"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    time.sleep(1.2)
    yield "http://127.0.0.1:8999/sandbox"
    server.should_exit = True


async def _drive(runner, task_id, approve: bool):
    """Plays the farmer: answers the OTP gate and the approval gate exactly as the filing room does."""
    steps = []
    async for s in runner.execute_crop_loss_filing(
        task_id=task_id, mobile="9822012345", crop="Onion", district="Nashik", survey_no="142/2A", cause="HAILSTORM",
    ):
        steps.append(s)
        if s.get("status") == "awaiting_human":
            assert submit_gate(task_id, "otp", "123456")
        if s.get("status") == "awaiting_approval":
            assert submit_gate(task_id, "approve", approve)
    return steps


def test_filing_runner_e2e(sandbox_server):
    import asyncio

    async def _run():
        runner = FilingRunner(sandbox_base_url=sandbox_server)
        steps = await _drive(runner, "test_e2e_987", approve=True)

        assert len(steps) >= 7
        last = steps[-1]
        assert last["type"] == "final"
        assert last["status"] == "completed"
        assert "PMFBY/MH/2026/" in last["reference_no"]

        receipt = last["receipt"]
        assert receipt["receipt_id"] == "REC-TEST_E2E"
        assert receipt["crop"] == "Onion"
        assert receipt["district"] == "Nashik"
        assert verify_receipt(receipt) is True

    asyncio.run(_run())


def test_filing_is_not_submitted_without_farmer_approval(sandbox_server):
    import asyncio

    async def _run():
        runner = FilingRunner(sandbox_base_url=sandbox_server)
        steps = await _drive(runner, "test_declined_654", approve=False)
        assert all(s.get("status") != "submitting" for s in steps)
        assert steps[-1]["status"] == "declined"
        assert "receipt" not in steps[-1]

    asyncio.run(_run())


def test_gate_answer_with_nothing_waiting_is_refused():
    assert submit_gate("no-such-task", "otp", "123456") is False
