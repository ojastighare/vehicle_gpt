"""Unit tests for query parsing, intent detection, and response generation."""

import pytest
from datetime import datetime, timezone
from backend.query_parser import QueryParser
from backend.response_builder import ResponseBuilder
from backend.retrieval import VehicleDataRetriever


@pytest.fixture
def parser():
    anchor = datetime(2026, 10, 22, 14, 0, 0, tzinfo=timezone.utc)
    return QueryParser(anchor_time=anchor)


def test_query_parser_adas_yesterday(parser: QueryParser):
    q = "Show all ADAS disengagement events from yesterday."
    res = parser.parse(q)
    assert res.intent == "ADAS_DISENGAGEMENTS"
    assert res.time_window["label"] == "yesterday"
    assert "2026-10-21" in res.time_window["start"]


def test_query_parser_warning_correlation(parser: QueryParser):
    q = "What happened before the battery overheating warning?"
    res = parser.parse(q)
    assert res.intent == "WARNING_CORRELATION"
    assert res.entities["warning_target"] == "overheating"


def test_query_parser_driving_range(parser: QueryParser):
    q = "Why has my driving range reduced over the last two weeks?"
    res = parser.parse(q)
    assert res.intent == "DRIVING_RANGE_ANALYSIS"
    assert res.time_window["label"] == "last two weeks"


def test_query_parser_consumption_surge(parser: QueryParser):
    q = "When did energy consumption increase the most?"
    res = parser.parse(q)
    assert res.intent == "ENERGY_CONSUMPTION_SURGE"


def test_query_parser_unsupported(parser: QueryParser):
    q = "What is the capital of France?"
    res = parser.parse(q)
    assert res.intent == "UNSUPPORTED"
    assert not res.is_supported
    assert "VehicleGPT supports natural language questions" in res.clarification_note


@pytest.mark.asyncio
async def test_response_builder_execution():
    """Verify that ResponseBuilder executes end-to-end on the seeded database."""
    builder = ResponseBuilder()
    resp = await builder.execute_query("Show all ADAS disengagement events from yesterday.")
    assert resp.intent == "ADAS_DISENGAGEMENTS"
    assert resp.confidence in ("HIGH", "MEDIUM")
    assert resp.model_used.startswith("deterministic-engine")
    assert resp.latency.total_ms > 0
    assert len(resp.evidence) > 0
