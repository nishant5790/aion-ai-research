"""
test_agent.py — pytest unit tests for ResearchAgent (agent/core.py).

Scenarios covered:
  1. is_ready is False before build().
  2. invoke() before build() raises RuntimeError.
  3. build() sets is_ready to True.
  4. Calling build() twice is a no-op (graph not re-created).
  5. invoke() returns the agent output string.
  6. Model name stripping — "google_genai:gemini-2.5-flash" → "gemini-2.5-flash".
"""

import pytest
from unittest.mock import patch, MagicMock

from src.agent.core import ResearchAgent


# ---------------------------------------------------------------------------
# Helper — build a ResearchAgent without hitting Google APIs
# ---------------------------------------------------------------------------

def _build_with_mocks(env_model: str = "gemini-2.5-flash") -> ResearchAgent:
    """Instantiate and build a ResearchAgent with all LLM calls mocked."""
    agent = ResearchAgent()
    with patch.dict("os.environ", {"DEEP_AGENT_MODEL": env_model, "GOOGLE_API_KEY": "test"}):
        with patch("src.agent.core.ChatGoogleGenerativeAI") as MockLLM:
            with patch("src.agent.core.GraphBuilder") as MockGraphBuilder:
                # Create a proper mock for GraphBuilder
                mock_builder_instance = MagicMock()
                mock_graph = MagicMock()
                mock_builder_instance.build.return_value = mock_graph
                mock_builder_instance.invoke.return_value = {"final_report": ""}
                MockGraphBuilder.return_value = mock_builder_instance
                
                agent.build()
    return agent


# ---------------------------------------------------------------------------
# 1. is_ready before build
# ---------------------------------------------------------------------------

def test_is_ready_false_before_build():
    agent = ResearchAgent()
    assert agent.is_ready is False


# ---------------------------------------------------------------------------
# 2. invoke before build raises
# ---------------------------------------------------------------------------

def test_invoke_before_build_raises():
    agent = ResearchAgent()
    with pytest.raises(RuntimeError, match="build()"):
        agent.invoke("some query")


# ---------------------------------------------------------------------------
# 3. build sets is_ready
# ---------------------------------------------------------------------------

def test_build_sets_is_ready():
    agent = _build_with_mocks()
    assert agent.is_ready is True


# ---------------------------------------------------------------------------
# 4. Double build is a no-op
# ---------------------------------------------------------------------------

def test_build_twice_is_noop():
    agent = _build_with_mocks()
    original_graph = agent._graph
    # Call build() again — the graph object should be the same reference
    with patch("src.agent.core.ChatGoogleGenerativeAI"):
        with patch("src.agent.core.GraphBuilder"):
            agent.build()
    assert agent._graph is original_graph


# ---------------------------------------------------------------------------
# 5. invoke returns the agent output
# ---------------------------------------------------------------------------

def test_invoke_returns_output():
    agent = _build_with_mocks()
    agent._graph_builder.invoke = MagicMock(return_value={"final_report": "# Great Report"})

    result = agent.invoke("What are AI trends?")
    assert result == "# Great Report"
    agent._graph_builder.invoke.assert_called_once()


# ---------------------------------------------------------------------------
# 6. Model name prefixes are stripped
# ---------------------------------------------------------------------------

def test_model_prefix_stripped():
    """google_genai:gemini-2.5-flash should be reduced to gemini-2.5-flash."""
    captured = {}

    def fake_llm(model, temperature):
        captured["model"] = model
        return MagicMock()

    agent = ResearchAgent()
    with patch.dict(
        "os.environ",
        {"DEEP_AGENT_MODEL": "google_genai:gemini-2.5-flash", "GOOGLE_API_KEY": "test"},
    ):
        with patch("src.agent.core.ChatGoogleGenerativeAI", side_effect=fake_llm):
            with patch("src.agent.core.GraphBuilder"):
                agent.build()

    assert captured["model"] == "gemini-2.5-flash"
