"""
tests/test_streaming.py
=======================
Streaming agent integration tests.

Covers two scenarios:
  1. Direct agent.astream() — validates the async generator yields per-step dicts.
  2. HTTP end-to-end   — POST /query then poll GET /status watching steps grow.

Run with:
    uv run python tests/test_streaming.py
"""

import asyncio
import sys
import time
import pytest

import httpx
from dotenv import load_dotenv

load_dotenv()

# ── PATH SETUP ────────────────────────────────────────────────────────────────
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

QUERY = "research on machine learning"
BASE_URL = "http://localhost:8000"


# ─────────────────────────────────────────────────────────────────────────────
# Test 1 — Direct agent.astream()
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.skip(reason="Integration script run separately")
async def test_direct_astream() -> None:
    """Call ResearchAgent.astream() and print each step as it arrives."""
    from src.agent.core import ResearchAgent

    print("\n" + "=" * 60)
    print("TEST 1: Direct agent.astream()")
    print("=" * 60)

    agent = ResearchAgent()
    agent.build()
    print(f"Agent ready. Streaming query: '{QUERY}'\n")

    step_num = 0
    async for update in agent.astream(QUERY):
        step_num += 1
        content_preview = update["content"][:120].replace("\n", " ")
        print(f"  Step {step_num:02d} [{update['step']:>6}]: {content_preview or '(no text content)'}")

    assert step_num > 0, "Expected at least one step from astream()"
    print(f"\n✅ Test 1 passed — {step_num} steps streamed\n")


# ─────────────────────────────────────────────────────────────────────────────
# Test 2 — HTTP end-to-end: POST /query → poll /status
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.skip(reason="Integration script run separately")
def test_http_streaming(
    poll_interval: int = 5,
    max_polls: int = 30,
) -> None:
    """
    Submit QUERY to the live server (must be running on BASE_URL).
    Poll /status every poll_interval seconds, printing new steps as they arrive,
    until status is 'completed' or 'failed'.
    """
    print("\n" + "=" * 60)
    print("TEST 2: HTTP streaming — POST /query → poll /status")
    print("=" * 60)

    # ── Submit query ──────────────────────────────────────────────────────────
    resp = httpx.post(f"{BASE_URL}/query", json={"query": QUERY}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    print("POST /query →", data)

    if data["status"] == "found":
        print("\n📦 Served from cache!")
        print("Report preview:", (data.get("report") or "")[:300])
        return

    task_id = data["task_id"]
    print(f"\n⏳ Task ID: {task_id}")
    print("Polling /status for incremental step updates...\n")

    seen_steps = 0

    for poll_num in range(1, max_polls + 1):
        time.sleep(poll_interval)

        status_resp = httpx.get(
            f"{BASE_URL}/status",
            params={"task_id": task_id},
            timeout=10,
        )
        status_resp.raise_for_status()
        status = status_resp.json()

        steps = status.get("steps") or []
        new_steps = steps[seen_steps:]

        for s in new_steps:
            content_preview = s["content"][:100].replace("\n", " ")
            print(f"  [{s['step']:>6}] {content_preview or '(no text)'}")
        seen_steps = len(steps)

        print(
            f"  Poll {poll_num:02d}: status={status['status']}"
            f", total_steps={seen_steps}"
        )

        if status["status"] == "completed":
            print("\n✅ Test 2 passed — task completed!")
            print("Report preview:", (status.get("report") or "")[:500])
            assert seen_steps > 0, "Expected at least one step in status"
            return
        elif status["status"] == "failed":
            raise AssertionError(f"Task failed: {status.get('error')}")

    raise AssertionError(
        f"Task did not complete within {max_polls * poll_interval}s"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Run the direct astream test
    asyncio.run(test_direct_astream())

    # Run the HTTP test (server must already be running)
    test_http_streaming()

    print("\n🎉 All streaming tests passed!")
