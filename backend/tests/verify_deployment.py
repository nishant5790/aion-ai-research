"""
verify_deployment.py — Pre-deployment verification test suite.

Validates end-to-end that the backend is functional:
  1. Server health
  2. All source-fetching tools return data (no import/async errors)
  3. Sub-agents can invoke tools and produce output
  4. Full pipeline produces a real report

Usage:
    cd backend
    uv run python tests/verify_deployment.py
    uv run python tests/verify_deployment.py --base-url http://localhost:8090
    uv run python tests/verify_deployment.py --skip-live   # skip live API tests

Exit code 0 = all checks pass, safe to deploy.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
import json
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ---------------------------------------------------------------------------
# ANSI
# ---------------------------------------------------------------------------
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"

results: list[tuple[str, bool, str]] = []


def _record(name: str, passed: bool, detail: str = ""):
    tag = f"{GREEN}✓ PASS{RESET}" if passed else f"{RED}✗ FAIL{RESET}"
    print(f"  {tag}  {name}" + (f"  — {detail}" if detail else ""))
    results.append((name, passed, detail))


def _section(title: str):
    print(f"\n{CYAN}{BOLD}{'─' * 60}{RESET}")
    print(f"{CYAN}{BOLD}  {title}{RESET}")
    print(f"{CYAN}{BOLD}{'─' * 60}{RESET}")


# ===========================================================================
# SECTION 1: Tool Unit Tests (no server needed)
# ===========================================================================

async def test_tools():
    """Verify each source-fetching tool can be invoked and returns valid JSON."""
    _section("TOOLS — Verify each tool returns data")

    from src.lg_workflow_agent.tools import (
        fetch_hackernews,
        fetch_youtube,
        fetch_github,
        fetch_linkedin,
        fetch_reddit,
        fetch_rss,
        fetch_google_news,
        fetch_podcasts,
        fetch_arxiv,
        think_tool,
    )

    tools = [
        ("fetch_hackernews", fetch_hackernews, {"topic": "AI agents", "limit": 3}),
        ("fetch_github", fetch_github, {"topic": "LLM", "limit": 3}),
        ("fetch_reddit", fetch_reddit, {"topic": "machine learning", "limit": 3}),
        ("fetch_rss", fetch_rss, {"topic": "artificial intelligence", "limit": 3}),
        ("fetch_google_news", fetch_google_news, {"topic": "AI", "limit": 3}),
        ("fetch_arxiv", fetch_arxiv, {"topic": "transformer", "limit": 3}),
        ("fetch_youtube", fetch_youtube, {"topic": "AI agents", "limit": 3}),
        ("fetch_podcasts", fetch_podcasts, {"topic": "AI", "limit": 3}),
        ("fetch_linkedin", fetch_linkedin, {"topic": "AI", "limit": 3}),
        ("think_tool", think_tool, {"reflection": "test reflection"}),
    ]

    for name, tool_fn, kwargs in tools:
        try:
            result = await tool_fn.ainvoke(kwargs)
            if not result or len(result) < 5:
                _record(name, False, f"empty/tiny response: {repr(result[:100])}")
                continue
            # Most tools return JSON, think_tool returns plain text
            if name != "think_tool":
                parsed = json.loads(result)
                items = parsed.get("results", parsed.get("items", []))
                _record(name, True, f"{len(items)} items, {len(result)} chars")
            else:
                _record(name, True, f"echoed: {result[:60]}")
        except Exception as e:
            _record(name, False, f"{type(e).__name__}: {e}")


# ===========================================================================
# SECTION 2: Sub-agent construction test
# ===========================================================================

def test_sub_agent_build():
    """Verify sub-agents can be constructed without import errors."""
    _section("SUB-AGENTS — Build and verify construction")

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        from src.lg_workflow_agent.sub_agents import build_sub_agents, build_role_runners

        model_name = os.environ.get("DEEP_AGENT_MODEL", "gemini-2.5-flash")
        if model_name.startswith("google_genai:"):
            model_name = model_name.split(":", 1)[1]
        llm = ChatGoogleGenerativeAI(model=model_name, temperature=0.0)

        agents = build_sub_agents(llm)
        expected_roles = ["data_collection", "statistics", "citation", "web_research", "latest_news_collection"]

        for role in expected_roles:
            if role in agents:
                _record(f"sub_agent[{role}]", True, "constructed")
            else:
                _record(f"sub_agent[{role}]", False, "missing from build_sub_agents()")

        runners = build_role_runners(llm)
        for name, runner in runners.items():
            is_async = asyncio.iscoroutinefunction(runner)
            _record(f"runner[{name}]", is_async, "async" if is_async else "NOT async — will fail at runtime!")

    except Exception as e:
        _record("sub_agent_build", False, f"{type(e).__name__}: {e}")


# ===========================================================================
# SECTION 3: Graph construction test
# ===========================================================================

def test_graph_build():
    """Verify the full LangGraph workflow compiles without errors."""
    _section("GRAPH — Compile workflow")

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        from src.lg_workflow_agent.graph import WorkflowGraphBuilder

        model_name = os.environ.get("DEEP_AGENT_MODEL", "gemini-2.5-flash")
        if model_name.startswith("google_genai:"):
            model_name = model_name.split(":", 1)[1]
        llm = ChatGoogleGenerativeAI(model=model_name, temperature=0.0)

        builder = WorkflowGraphBuilder(llm=llm, db=None)
        graph = builder.build()
        _record("graph_compile", graph is not None, f"nodes: {len(graph.nodes)}")
    except Exception as e:
        _record("graph_compile", False, f"{type(e).__name__}: {e}")


# ===========================================================================
# SECTION 4: Live API tests (requires running server)
# ===========================================================================

def test_live_api(base_url: str, timeout: int = 300):
    """Full end-to-end: submit query, poll until done, verify report."""
    _section(f"LIVE API — End-to-end test ({base_url})")

    headers = {"Authorization": "Bearer test", "Content-Type": "application/json"}

    # Health check
    try:
        r = requests.get(f"{base_url}/health", timeout=5)
        _record("GET /health", r.status_code == 200, r.text[:80])
    except Exception as e:
        _record("GET /health", False, f"Server not reachable: {e}")
        return

    # Submit query
    query = f"test query: latest in LLM frameworks {int(time.time())}"
    try:
        r = requests.post(f"{base_url}/query", json={"query": query}, headers=headers, timeout=15)
        data = r.json()
        ok = r.status_code == 200 and data.get("status") in ("processing", "found")
        _record("POST /query", ok, f"status={data.get('status')}")

        if data.get("status") == "found":
            _record("cache_hit", True, f"report_len={len(data.get('report', ''))}")
            return

        task_id = data.get("task_id", "")
        if not task_id:
            _record("task_id", False, "no task_id returned")
            return
    except Exception as e:
        _record("POST /query", False, str(e))
        return

    # Poll for completion
    print(f"\n  {YELLOW}Polling task {task_id[:12]}... (max {timeout}s){RESET}")
    start = time.time()
    final_data = None

    while time.time() - start < timeout:
        try:
            r = requests.get(f"{base_url}/status", params={"task_id": task_id}, headers=headers, timeout=10)
            data = r.json()
            status = data.get("status", "?")
            steps = len(data.get("steps", []))
            elapsed = int(time.time() - start)

            last_step = data.get("steps", [{}])[-1].get("step", "—") if data.get("steps") else "—"
            print(f"    [{elapsed:3d}s] status={status} steps={steps} last={last_step}")

            if status == "completed":
                final_data = data
                break
            elif status == "failed":
                _record("task_completion", False, f"error: {data.get('error', '?')[:200]}")
                return
        except Exception as e:
            print(f"    [poll error: {e}]")

        time.sleep(10)

    if final_data is None:
        _record("task_completion", False, f"timed out after {timeout}s")
        return

    # Validate the result
    report = final_data.get("report", "") or ""
    steps = final_data.get("steps", [])

    _record("task_completed", True, f"{int(time.time() - start)}s")
    _record("report_generated", len(report) > 500, f"{len(report)} chars")

    # Check sub-agents didn't fail
    sub_agent_steps = [s for s in steps if "agent" in s.get("step", "")]
    for step in sub_agent_steps:
        outputs = step.get("metadata", {}).get("worker_outputs", [])
        for out in outputs:
            output_text = out.get("output", "")
            failed = "failed:" in output_text.lower() or "does not support" in output_text.lower()
            role = out.get("role", "?")
            if failed:
                _record(f"sub_agent_output[{role}]", False, output_text[:120])
            else:
                _record(f"sub_agent_output[{role}]", True, f"{len(output_text)} chars")

    # Check writer produced content
    writer_steps = [s for s in steps if "writer" in s.get("step", "")]
    if writer_steps:
        writer_len = len(writer_steps[0].get("content", ""))
        _record("writer_output", writer_len > 200, f"{writer_len} chars")

    # Verify report has real content (not just headers)
    has_substance = len(report) > 1000 and report.count("\n") > 10
    _record("report_has_substance", has_substance, f"{report.count(chr(10))} lines")


# ===========================================================================
# SECTION 5: Validation edge cases
# ===========================================================================

def test_api_edge_cases(base_url: str):
    """Quick API edge case checks."""
    _section("API EDGE CASES")

    headers = {"Authorization": "Bearer test", "Content-Type": "application/json"}

    # Missing body → 422
    try:
        r = requests.post(f"{base_url}/query", json={}, headers=headers, timeout=5)
        _record("POST /query empty body → 422", r.status_code == 422, f"got {r.status_code}")
    except Exception as e:
        _record("POST /query empty body", False, str(e))

    # Unknown task_id → 404
    try:
        r = requests.get(f"{base_url}/status", params={"task_id": "nonexistent"}, headers=headers, timeout=5)
        _record("GET /status unknown → 404", r.status_code == 404, f"got {r.status_code}")
    except Exception as e:
        _record("GET /status unknown", False, str(e))

    # GET /report
    try:
        r = requests.get(f"{base_url}/report", headers=headers, timeout=5)
        data = r.json()
        _record("GET /report", r.status_code == 200 and "reports" in data, f"{len(data.get('reports', []))} reports")
    except Exception as e:
        _record("GET /report", False, str(e))


# ===========================================================================
# Main runner
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(description="Pre-deployment verification for AI Research backend")
    parser.add_argument("--base-url", default="http://localhost:8090", help="Running server URL")
    parser.add_argument("--skip-live", action="store_true", help="Skip live API tests (only test tools/build)")
    parser.add_argument("--skip-tools", action="store_true", help="Skip individual tool tests")
    parser.add_argument("--timeout", type=int, default=300, help="Max seconds to wait for task completion")
    args = parser.parse_args()

    print(f"\n{BOLD}╔══════════════════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}║    Pre-Deployment Verification Suite                     ║{RESET}")
    print(f"{BOLD}╚══════════════════════════════════════════════════════════╝{RESET}")

    if not args.skip_tools:
        asyncio.run(test_tools())

    test_sub_agent_build()
    test_graph_build()

    if not args.skip_live:
        test_live_api(args.base_url, timeout=args.timeout)
        test_api_edge_cases(args.base_url)
    else:
        print(f"\n  {YELLOW}⚠ Skipping live API tests (--skip-live){RESET}")

    # Summary
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    total = len(results)
    color = GREEN if failed == 0 else RED

    print(f"\n{color}{BOLD}{'═' * 60}{RESET}")
    print(f"{color}{BOLD}  RESULTS: {passed}/{total} passed, {failed} failed{RESET}")
    print(f"{color}{BOLD}{'═' * 60}{RESET}")

    if failed > 0:
        print(f"\n  {RED}Failed checks:{RESET}")
        for name, ok, detail in results:
            if not ok:
                print(f"    • {name}: {detail}")
        print()

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
