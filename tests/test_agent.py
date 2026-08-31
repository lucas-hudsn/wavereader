"""Unit tests for wavereader.agent — smolagents surf forecasting agent."""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from wavereader.agent import (
    AgentTrace,
    FindSpotsTool,
    GetForecastTool,
    GetSpotKnowledgeTool,
    RankSpotsThisWeekTool,
    ScoreWeekTool,
    SurfAgent,
    TraceEvent,
    PROVIDER_HF,
    PROVIDER_NIM,
    DEFAULT_MODEL,
    run_agent,
    run_agent_stream,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_env(monkeypatch):
    """Clear provider env vars for each test."""
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)


@pytest.fixture
def mock_model():
    """Mock InferenceClientModel to avoid real API calls."""
    with patch("wavereader.agent.InferenceClientModel") as mock:
        # Configure the mock to return a MagicMock when instantiated
        mock_instance = MagicMock()
        mock.return_value = mock_instance
        yield mock


@pytest.fixture
def mock_build_model():
    """Mock _build_model to return a mock model instance."""
    with patch("wavereader.agent._build_model") as mock:
        mock_instance = MagicMock()
        mock.return_value = mock_instance
        yield mock


# ---------------------------------------------------------------------------
# TraceEvent / AgentTrace
# ---------------------------------------------------------------------------

def test_trace_event_creation():
    evt = TraceEvent(type="tool_call", timestamp=123.0, data={"name": "test"})
    assert evt.type == "tool_call"
    assert evt.timestamp == 123.0
    assert evt.data == {"name": "test"}


def test_agent_trace_add_event():
    trace = AgentTrace()
    trace.add_event("tool_call", {"name": "get_forecast", "args": {}})
    assert len(trace.events) == 1
    assert trace.events[0].type == "tool_call"
    assert trace.events[0].data["name"] == "get_forecast"


def test_agent_trace_to_json():
    trace = AgentTrace(question="test?", model="Qwen", provider="hf")
    trace.add_event("llm_chunk", {"chunk": "hello"})
    json_str = trace.to_json()
    data = json.loads(json_str)
    assert data["question"] == "test?"
    assert data["model"] == "Qwen"
    assert data["provider"] == "hf"
    assert data["events"][0]["type"] == "llm_chunk"


# ---------------------------------------------------------------------------
# Tools (unit test tool forward methods)
# ---------------------------------------------------------------------------

class TestGetForecastTool:
    def test_forward_success(self):
        tool = GetForecastTool()
        with patch("wavereader.agent.get_forecast") as mock_get:
            mock_get.return_value = {"hourly": [{"time": "2024-01-01T00:00", "wave_height": 1.5}]}
            result = tool.forward("Snapper Rocks", "QLD")
            assert result["hourly"][0]["wave_height"] == 1.5
            mock_get.assert_called_once_with("Snapper Rocks", "QLD")

    def test_forward_spot_not_found(self):
        tool = GetForecastTool()
        with patch("wavereader.agent.get_forecast") as mock_get:
            mock_get.return_value = {"error": "Spot 'Bad' (XX) not found"}
            result = tool.forward("Bad", "XX")
            assert "error" in result


class TestScoreWeekTool:
    def test_forward_success(self):
        tool = ScoreWeekTool()
        with patch("wavereader.agent.score_week") as mock_score:
            mock_score.return_value = [{"time": "2024-01-01T00:00", "score": 8.5}]
            result = tool.forward("Snapper Rocks", "QLD")
            assert result[0]["score"] == 8.5
            mock_score.assert_called_once_with("Snapper Rocks", "QLD")

    def test_forward_spot_not_found(self):
        tool = ScoreWeekTool()
        with patch("wavereader.agent.score_week") as mock_score:
            mock_score.return_value = []
            result = tool.forward("Bad", "XX")
            assert result == []


class TestFindSpotsTool:
    def test_forward_with_query(self):
        tool = FindSpotsTool()
        with patch("wavereader.agent.find_spots") as mock_find:
            mock_find.return_value = [{"name": "Snapper Rocks", "region": "QLD"}]
            result = tool.forward(query="Snapper")
            assert len(result) == 1
            assert result[0]["name"] == "Snapper Rocks"
            mock_find.assert_called_once_with(query="Snapper", skill=None, limit=10)

    def test_forward_with_skill_and_limit(self):
        tool = FindSpotsTool()
        with patch("wavereader.agent.find_spots") as mock_find:
            mock_find.return_value = []
            tool.forward(query="", skill="beginner", limit=5)
            mock_find.assert_called_once_with(query="", skill="beginner", limit=5)


class TestGetSpotKnowledgeTool:
    def test_forward_success(self):
        tool = GetSpotKnowledgeTool()
        with patch("wavereader.agent.get_spot_knowledge") as mock_get:
            mock_get.return_value = {"name": "Bells Beach", "region": "VIC", "ideal_swell": {}}
            result = tool.forward("Bells Beach", "VIC")
            assert result["name"] == "Bells Beach"
            mock_get.assert_called_once_with("Bells Beach", "VIC")

    def test_forward_spot_not_found(self):
        tool = GetSpotKnowledgeTool()
        with patch("wavereader.agent.get_spot_knowledge") as mock_get:
            mock_get.return_value = {"error": "Spot 'Bad' (XX) not found"}
            result = tool.forward("Bad", "XX")
            assert "error" in result


class TestRankSpotsThisWeekTool:
    def test_forward_success(self):
        tool = RankSpotsThisWeekTool()
        with patch("wavereader.agent.rank_spots_this_week") as mock_rank:
            mock_rank.return_value = [
                {"name": "A", "region": "QLD", "best_score": 9.0},
                {"name": "B", "region": "QLD", "best_score": 7.0},
            ]
            result = tool.forward("QLD")
            assert len(result) == 2
            assert result[0]["best_score"] == 9.0
            mock_rank.assert_called_once_with("QLD", None)

    def test_forward_with_skill(self):
        tool = RankSpotsThisWeekTool()
        with patch("wavereader.agent.rank_spots_this_week") as mock_rank:
            mock_rank.return_value = []
            tool.forward("NSW", "advanced")
            mock_rank.assert_called_once_with("NSW", "advanced")


# ---------------------------------------------------------------------------
# SurfAgent initialization
# ---------------------------------------------------------------------------

class TestSurfAgentInit:
    def test_init_with_explicit_provider_hf(self, mock_build_model):
        agent = SurfAgent(provider=PROVIDER_HF)
        assert agent.provider == PROVIDER_HF
        mock_build_model.assert_called_once_with(PROVIDER_HF, DEFAULT_MODEL)

    def test_init_with_explicit_provider_nim(self, mock_build_model):
        agent = SurfAgent(provider=PROVIDER_NIM)
        assert agent.provider == PROVIDER_NIM
        mock_build_model.assert_called_once_with(PROVIDER_NIM, DEFAULT_MODEL)

    def test_init_auto_detect_hf(self, mock_build_model, monkeypatch):
        monkeypatch.setenv("HF_TOKEN", "test-token")
        agent = SurfAgent(provider=None)
        assert agent.provider == PROVIDER_HF
        mock_build_model.assert_called_once_with(PROVIDER_HF, DEFAULT_MODEL)

    def test_init_auto_detect_nim(self, mock_build_model, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
        agent = SurfAgent(provider=None)
        assert agent.provider == PROVIDER_NIM
        mock_build_model.assert_called_once_with(PROVIDER_NIM, DEFAULT_MODEL)

    def test_init_prefers_nim_over_hf(self, mock_build_model, monkeypatch):
        monkeypatch.setenv("HF_TOKEN", "test-token")
        monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
        agent = SurfAgent(provider=None)
        assert agent.provider == PROVIDER_NIM
        mock_build_model.assert_called_once_with(PROVIDER_NIM, DEFAULT_MODEL)

    def test_init_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            SurfAgent(provider="unknown")

    def test_init_no_api_key_raises_hf(self, monkeypatch):
        monkeypatch.delenv("HF_TOKEN", raising=False)
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
        with pytest.raises(ValueError, match="HF_TOKEN"):
            SurfAgent(provider=PROVIDER_HF)

    def test_init_no_api_key_raises_nim(self, monkeypatch):
        monkeypatch.delenv("HF_TOKEN", raising=False)
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
        with pytest.raises(ValueError, match="NVIDIA_API_KEY"):
            SurfAgent(provider=PROVIDER_NIM)

    def test_init_custom_model(self, mock_build_model):
        agent = SurfAgent(provider=PROVIDER_HF, model="custom/model")
        assert agent.model == "custom/model"
        mock_build_model.assert_called_once_with(PROVIDER_HF, "custom/model")


# ---------------------------------------------------------------------------
# SurfAgent run / trace capture
# ---------------------------------------------------------------------------

class TestSurfAgentRun:
    def test_run_creates_trace(self, mock_build_model):
        mock_agent = MagicMock()
        mock_agent.run.return_value = "Test answer"

        with patch("wavereader.agent.CodeAgent", return_value=mock_agent):
            agent = SurfAgent(provider=PROVIDER_HF)
            result = agent.run("What's the surf like?")

        assert result == "Test answer"
        assert agent.trace is not None
        assert agent.trace.question == "What's the surf like?"
        assert agent.trace.provider == PROVIDER_HF

    def test_run_stream_yields_chunks(self, mock_build_model):
        mock_agent = MagicMock()
        mock_agent.run.return_value = iter(["chunk1", "chunk2", "chunk3"])

        with patch("wavereader.agent.CodeAgent", return_value=mock_agent):
            agent = SurfAgent(provider=PROVIDER_HF)
            chunks = list(agent.run_stream("Test question"))

        assert chunks == ["chunk1", "chunk2", "chunk3"]
        assert agent.trace is not None

    def test_run_stream_captures_tool_calls_in_trace(self, mock_build_model):
        """Verify trace captures tool calls during streaming."""
        from smolagents.memory import ActionStep, ToolCall
        from smolagents.monitoring import Timing

        # Create a proper ActionStep-like object with tool_calls
        tool_call = ToolCall(name="get_forecast", arguments={"spot_name": "Snapper", "region": "QLD"}, id="call-1")
        memory_step_with_tool = ActionStep(
            step_number=1,
            timing=Timing(start_time=0, end_time=0),
            tool_calls=[tool_call],
            observations="forecast data",
            is_final_answer=False,
        )
        memory_step_without_tool = ActionStep(
            step_number=2,
            timing=Timing(start_time=0, end_time=0),
            tool_calls=[],
            observations="",
            is_final_answer=True,
        )

        call_count = {"count": 0}
        step_results = [memory_step_with_tool, memory_step_without_tool]

        def mock_step(memory_step, *args, **kwargs):
            result = step_results[call_count["count"]]
            call_count["count"] += 1
            return result

        # Use a real object instead of MagicMock so step can be dynamically replaced
        class MockAgent:
            def __init__(self):
                self.step = mock_step

            def run(self, question, stream=False):
                if stream:
                    # Call step through self.step (which will be wrapped by traced_step)
                    self.step(memory_step_with_tool)
                    yield "chunk 1"
                    self.step(memory_step_without_tool)
                    yield "chunk 2"
                return "final answer"

        mock_agent = MockAgent()

        with patch("wavereader.agent.CodeAgent", return_value=mock_agent):
            agent = SurfAgent(provider=PROVIDER_HF)
            list(agent.run_stream("Test"))

        trace = agent.trace
        tool_call_events = [e for e in trace.events if e.type == "tool_call"]
        tool_result_events = [e for e in trace.events if e.type == "tool_result"]

        assert len(tool_call_events) == 1
        assert tool_call_events[0].data["name"] == "get_forecast"
        # observations is a string, so traced_step iterates character by character
        # "forecast data" = 12 chars + 1 space = 13 events
        assert len(tool_result_events) == 13
        # First and last character events
        assert tool_result_events[0].data["observation"] == "f"
        assert tool_result_events[-1].data["observation"] == "a"

    def test_run_stream_captures_llm_chunks(self, mock_build_model):
        mock_agent = MagicMock()
        mock_agent.step = MagicMock(return_value=MagicMock(tool_calls=[], observations=[]))
        mock_agent.run.return_value = iter(["hello", " world"])

        with patch("wavereader.agent.CodeAgent", return_value=mock_agent):
            agent = SurfAgent(provider=PROVIDER_HF)
            list(agent.run_stream("Test"))

        llm_events = [e for e in agent.trace.events if e.type == "llm_chunk"]
        assert len(llm_events) == 2
        assert llm_events[0].data["chunk"] == "hello"
        assert llm_events[1].data["chunk"] == " world"


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------

def test_run_agent_function(mock_build_model):
    mock_agent = MagicMock()
    mock_agent.run.return_value = "Direct answer"

    with patch("wavereader.agent.CodeAgent", return_value=mock_agent):
        result = run_agent("Test question", provider=PROVIDER_HF)

    assert result == "Direct answer"


def test_run_agent_stream_function(mock_build_model):
    mock_agent = MagicMock()
    mock_agent.run.return_value = iter(["stream", "ing"])

    with patch("wavereader.agent.CodeAgent", return_value=mock_agent):
        result = list(run_agent_stream("Test question", provider=PROVIDER_HF))

    assert result == ["stream", "ing"]


# ---------------------------------------------------------------------------
# Provider constants
# ---------------------------------------------------------------------------

def test_provider_constants():
    assert PROVIDER_HF == "hf"
    assert PROVIDER_NIM == "nim"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])