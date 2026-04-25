"""
smoke_test_api.py — Live HTTP smoke test against a running server.

Run AFTER starting the server with `uv run python run.py`.

Usage:
    uv run python tests/smoke_test_api.py
    uv run python tests/smoke_test_api.py --base-url http://localhost:8000

Each test prints a coloured PASS / FAIL result and exits with code 1 if any fail.
"""

import argparse
import sys
import time
import json
import textwrap
import requests

# ---------------------------------------------------------------------------
# ANSI colours
# ---------------------------------------------------------------------------
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"


def _ok(label: str, msg: str = ""):
    print(f"  {GREEN}✓ PASS{RESET}  {label}" + (f"  — {msg}" if msg else ""))


def _fail(label: str, msg: str = ""):
    print(f"  {RED}✗ FAIL{RESET}  {label}" + (f"  — {msg}" if msg else ""))


def _section(title: str):
    print(f"\n{CYAN}{BOLD}{'─' * 55}{RESET}")
    print(f"{CYAN}{BOLD}  {title}{RESET}")
    print(f"{CYAN}{BOLD}{'─' * 55}{RESET}")


# ---------------------------------------------------------------------------
# Individual smoke checks
# ---------------------------------------------------------------------------

def check_health(base: str) -> bool:
    _section("1 · Health check")
    try:
        r = requests.get(f"{base}/health", timeout=5)
        if r.status_code == 200 and r.json().get("status") == "ok":
            _ok("/health", r.json())
            return True
        _fail("/health", f"status={r.status_code} body={r.text[:120]}")
    except Exception as e:
        _fail("/health", str(e))
    return False


def check_query_flow(base: str) -> tuple[bool, str]:
    """POST /query → returns a task_id for a new topic."""
    _section("2 · POST /query  (new topic)")
    topic = f"Smoke test topic {int(time.time())}"
    try:
        r = requests.post(f"{base}/query", json={"query": topic}, timeout=10)
        data = r.json()
        if r.status_code == 200 and data.get("status") in ("processing", "found"):
            _ok("/query", f"status={data['status']}")
            task_id = data.get("task_id", "")
            return True, task_id
        _fail("/query", f"status={r.status_code} body={r.text[:120]}")
    except Exception as e:
        _fail("/query", str(e))
    return False, ""


def check_status(base: str, task_id: str) -> bool:
    """GET /status?task_id=<id> — waits up to 30s for completion."""
    _section("3 · GET /status  (poll until done)")
    if not task_id:
        print(f"  {YELLOW}SKIP{RESET}  No task_id to poll (was a cache hit).")
        return True

    for attempt in range(10):
        try:
            r = requests.get(f"{base}/status", params={"task_id": task_id}, timeout=5)
            data = r.json()
            status = data.get("status", "?")
            print(f"  [{attempt + 1:02d}] status={status}")
            if status in ("completed", "failed"):
                if status == "completed":
                    _ok(f"/status", "task completed")
                    return True
                else:
                    _fail("/status", f"task failed: {data.get('error')}")
                    return False
        except Exception as e:
            _fail("/status", str(e))
            return False
        time.sleep(3)

    _fail("/status", "timed out waiting for task")
    return False


def check_status_404(base: str) -> bool:
    _section("4 · GET /status  (unknown id → 404)")
    try:
        r = requests.get(f"{base}/status", params={"task_id": "not-real-id"}, timeout=5)
        if r.status_code == 404:
            _ok("/status 404")
            return True
        _fail("/status 404", f"got {r.status_code}")
    except Exception as e:
        _fail("/status 404", str(e))
    return False


def check_report(base: str) -> bool:
    _section("5 · GET /report")
    try:
        r = requests.get(f"{base}/report", timeout=5)
        data = r.json()
        if r.status_code == 200 and "reports" in data:
            _ok("/report", f"{len(data['reports'])} report(s) stored")
            return True
        _fail("/report", f"status={r.status_code}")
    except Exception as e:
        _fail("/report", str(e))
    return False


def check_cleanup(base: str) -> bool:
    _section("6 · POST /cleanup")
    try:
        r = requests.post(f"{base}/cleanup", timeout=10)
        data = r.json()
        if r.status_code == 200 and data.get("status") == "cleaned":
            _ok("/cleanup", data)
            return True
        _fail("/cleanup", f"status={r.status_code}")
    except Exception as e:
        _fail("/cleanup", str(e))
    return False


def check_validation_error(base: str) -> bool:
    _section("7 · POST /query  (missing body → 422)")
    try:
        r = requests.post(f"{base}/query", json={}, timeout=5)
        if r.status_code == 422:
            _ok("/query 422 validation error")
            return True
        _fail("/query 422", f"got {r.status_code}")
    except Exception as e:
        _fail("/query 422", str(e))
    return False


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run(base: str) -> int:
    print(f"\n{BOLD}Smoke testing server at: {base}{RESET}")
    results = []

    results.append(check_health(base))
    ok, task_id = check_query_flow(base)
    results.append(ok)
    results.append(check_status(base, task_id))
    results.append(check_status_404(base))
    results.append(check_report(base))
    results.append(check_cleanup(base))
    results.append(check_validation_error(base))

    passed = sum(results)
    total  = len(results)
    colour = GREEN if passed == total else RED

    print(f"\n{colour}{BOLD}{'─' * 55}")
    print(f"  Result: {passed}/{total} checks passed")
    print(f"{'─' * 55}{RESET}\n")

    return 0 if passed == total else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Smoke-test the running AI Report Gen API")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Server base URL")
    args = parser.parse_args()

    sys.exit(run(args.base_url))
