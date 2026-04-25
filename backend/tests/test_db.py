"""
test_db.py — pytest unit tests for VectorDBContext (db/database.py).

Uses in-memory Qdrant and mocked Google embeddings — no cloud accounts needed.

Scenarios covered:
  1. init_db creates the collection (idempotent on second call).
  2. save_report stores a point that can be retrieved via get_reports.
  3. search_query returns None when nothing matches above the threshold.
  4. search_query returns the report when a match is above threshold.
  5. cleanup deletes and recreates the collection (empty after cleanup).
  6. get_reports returns an empty list on a fresh DB.
"""

import pytest
from unittest.mock import patch, MagicMock

from src.db.database import VectorDBContext, COLLECTION_NAME, SIMILARITY_THRESHOLD


# ---------------------------------------------------------------------------
# Helper — build DB with 3072-dim fixed embedding
# ---------------------------------------------------------------------------

FIXED_VECTOR = [0.1] * 3072


def _make_db() -> VectorDBContext:
    """VectorDBContext backed by in-memory Qdrant with mocked embeddings."""
    with patch.dict("os.environ", {"QDRANT_URL": "", "GOOGLE_API_KEY": "test"}):
        db = VectorDBContext()
    db.embeddings = MagicMock()
    db.embeddings.embed_query.return_value = FIXED_VECTOR
    db.init_db()
    return db


# ---------------------------------------------------------------------------
# 1. init_db is idempotent
# ---------------------------------------------------------------------------

def test_init_db_idempotent():
    db = _make_db()
    db.init_db()  # second call should not raise
    info = db.client.get_collection(COLLECTION_NAME)
    assert info is not None


# ---------------------------------------------------------------------------
# 2. save_report → get_reports round-trip
# ---------------------------------------------------------------------------

def test_save_and_retrieve_report():
    db = _make_db()
    db.save_report("What is AI?", "# AI Report\n\nAI is everywhere.")

    reports = db.get_reports()
    assert len(reports) == 1
    assert reports[0]["query"] == "What is AI?"
    assert "AI is everywhere." in reports[0]["report"]


# ---------------------------------------------------------------------------
# 3. search_query — no match (below threshold)
# ---------------------------------------------------------------------------

def test_search_query_no_match():
    """Empty DB should always return None."""
    db = _make_db()
    result = db.search_query("Quantum entanglement")
    assert result is None


# ---------------------------------------------------------------------------
# 4. search_query — match above threshold
# ---------------------------------------------------------------------------

def test_search_query_finds_cached_report():
    """After saving, the same-vector query should return the report."""
    db = _make_db()
    db.save_report("AI ethics", "# Ethics Report")

    # In-memory Qdrant with identical vectors → score will be 1.0
    result = db.search_query("AI ethics")
    assert result == "# Ethics Report"


# ---------------------------------------------------------------------------
# 5. cleanup empties the collection
# ---------------------------------------------------------------------------

def test_cleanup_empties_collection():
    db = _make_db()
    db.save_report("Test topic", "# Test")
    assert len(db.get_reports()) == 1

    db.cleanup()
    assert len(db.get_reports()) == 0


# ---------------------------------------------------------------------------
# 6. get_reports on fresh DB
# ---------------------------------------------------------------------------

def test_get_reports_empty_on_fresh_db():
    db = _make_db()
    assert db.get_reports() == []
