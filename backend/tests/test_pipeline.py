"""
test_pipeline.py — pytest unit tests for ResearchPipeline (orchestrator.py).

Scenarios covered:
  1. Cache hit — process_query returns cached report immediately.
  2. Cache miss — process_query creates a task and returns task_id.
  3. run_task success — report persisted, task status becomes "completed".
  4. run_task failure — agent raises, task status becomes "failed" with error.
  5. get_task_status returns None for unknown task_id.
  6. get_all_reports delegates to DB correctly.
  7. cleanup wipes tasks dict and calls DB cleanup.
  8. Double-initialize is idempotent (agent.build() is a no-op the 2nd time).
"""

import pytest
from unittest.mock import patch, MagicMock

from src.pipeline.orchestrator import ResearchPipeline


# ---------------------------------------------------------------------------
# 1. Cache hit
# ---------------------------------------------------------------------------

def test_process_query_cache_hit(pipeline, in_memory_db):
    """When the DB already has a matching report, return it immediately."""
    # Pre-seed the DB with a fake embedding hit by patching search_query
    in_memory_db.search_query = MagicMock(return_value="Cached report text")

    result = pipeline.process_query("AI trends")

    assert result["status"] == "found"
    assert result["report"] == "Cached report text"
    assert "task_id" not in result


# ---------------------------------------------------------------------------
# 2. Cache miss
# ---------------------------------------------------------------------------

def test_process_query_cache_miss(pipeline, in_memory_db):
    """On a cache miss a new pending task is created."""
    in_memory_db.search_query = MagicMock(return_value=None)

    result = pipeline.process_query("Quantum computing")

    assert result["status"] == "processing"
    assert "task_id" in result
    # Task should now exist in the internal tracker
    task_id = result["task_id"]
    task = pipeline.get_task_status(task_id)
    assert task is not None
    assert task["status"] == "pending"


# ---------------------------------------------------------------------------
# 3. run_task — success path
# ---------------------------------------------------------------------------

def test_run_task_success(pipeline, in_memory_db, mock_agent):
    """Successful task execution saves the report and marks task completed."""
    in_memory_db.search_query = MagicMock(return_value=None)
    in_memory_db.save_report = MagicMock()

    result = pipeline.process_query("Machine learning")
    task_id = result["task_id"]

    pipeline.run_task(task_id, "Machine learning")

    task = pipeline.get_task_status(task_id)
    assert task["status"] == "completed"
    assert task["report"] is not None
    in_memory_db.save_report.assert_called_once()


# ---------------------------------------------------------------------------
# 4. run_task — failure path
# ---------------------------------------------------------------------------

def test_run_task_failure(pipeline, in_memory_db, mock_agent):
    """When the agent raises, task is marked failed and error is recorded."""
    in_memory_db.search_query = MagicMock(return_value=None)
    # Use _graph_builder.invoke for the refactored architecture
    mock_agent._graph_builder.invoke.side_effect = RuntimeError("LLM quota exceeded")

    result = pipeline.process_query("Blockchain")
    task_id = result["task_id"]

    pipeline.run_task(task_id, "Blockchain")

    task = pipeline.get_task_status(task_id)
    assert task["status"] == "failed"
    assert "LLM quota exceeded" in task["error"]


# ---------------------------------------------------------------------------
# 5. Unknown task_id
# ---------------------------------------------------------------------------

def test_get_task_status_unknown(pipeline):
    """Returns None for a task_id that has never been created."""
    assert pipeline.get_task_status("does-not-exist") is None


# ---------------------------------------------------------------------------
# 6. get_all_reports
# ---------------------------------------------------------------------------

def test_get_all_reports_delegates_to_db(pipeline, in_memory_db):
    """get_all_reports should return whatever the DB returns."""
    fake_reports = [{"id": "abc", "query": "q", "report": "r"}]
    in_memory_db.get_reports = MagicMock(return_value=fake_reports)

    reports = pipeline.get_all_reports()

    assert reports == fake_reports
    in_memory_db.get_reports.assert_called_once()


# ---------------------------------------------------------------------------
# 7. cleanup
# ---------------------------------------------------------------------------

def test_cleanup_clears_tasks_and_db(pipeline, in_memory_db):
    """Cleanup should empty the task dict and call db.cleanup()."""
    in_memory_db.search_query = MagicMock(return_value=None)
    in_memory_db.cleanup = MagicMock()

    # Create a task first
    result = pipeline.process_query("Robotics")
    assert result["task_id"] in pipeline._tasks

    pipeline.cleanup()

    assert len(pipeline._tasks) == 0
    in_memory_db.cleanup.assert_called_once()


# ---------------------------------------------------------------------------
# 8. initialize is idempotent
# ---------------------------------------------------------------------------

def test_initialize_is_idempotent(pipeline, mock_agent):
    """Calling initialize() twice should not double-build the agent."""
    mock_agent.build = MagicMock(wraps=mock_agent.build)
    pipeline.initialize()
    pipeline.initialize()
    # build() is a no-op the 2nd time — still only executes real work once
    assert mock_agent.is_ready
