"""End-to-end test of the Playwright autonomous filing runner against the sandbox replica."""
import threading
import time
import pytest
import uvicorn
from app.main import app
from app.executor.runner import FilingRunner
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


def test_filing_runner_e2e(sandbox_server):
    import asyncio

    async def _run():
        runner = FilingRunner(sandbox_base_url=sandbox_server)
        steps = []
        async for s in runner.execute_crop_loss_filing(
            task_id="test_e2e_987",
            mobile="9822012345",
            crop="Onion",
            district="Nashik",
            survey_no="142/2A",
            cause="HAILSTORM",
        ):
            steps.append(s)

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
