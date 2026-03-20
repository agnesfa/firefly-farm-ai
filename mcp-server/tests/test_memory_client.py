"""
Tests for the MemoryClient (memory_client.py).

Uses the `responses` library to mock HTTP requests to the Google Apps Script endpoint.
"""

import json

import pytest
import responses

from memory_client import MemoryClient


FAKE_ENDPOINT = "https://script.google.com/macros/s/FAKE_MEMORY_ID/exec"


@pytest.fixture
def client(monkeypatch):
    """Return a connected MemoryClient with a fake endpoint."""
    monkeypatch.setenv("MEMORY_ENDPOINT", FAKE_ENDPOINT)
    c = MemoryClient()
    c.connect()
    return c


# ── Connection tests ──────────────────────────────────────────


def test_connect_success(monkeypatch):
    """Setting MEMORY_ENDPOINT env var connects successfully."""
    monkeypatch.setenv("MEMORY_ENDPOINT", FAKE_ENDPOINT)
    c = MemoryClient()
    c.connect()
    assert c.is_connected is True
    assert c.endpoint == FAKE_ENDPOINT


def test_connect_missing_env(monkeypatch):
    """Missing MEMORY_ENDPOINT raises ValueError."""
    monkeypatch.delenv("MEMORY_ENDPOINT", raising=False)
    c = MemoryClient()
    with pytest.raises(ValueError, match="Missing MEMORY_ENDPOINT"):
        c.connect()


# ── write_summary ─────────────────────────────────────────────


@responses.activate
def test_write_summary_payload(client):
    """POST payload contains all summary fields and uses text/plain Content-Type."""
    responses.add(
        responses.POST,
        FAKE_ENDPOINT,
        json={"success": True, "message": "Summary saved"},
        status=200,
    )

    result = client.write_summary(
        user="Agnes",
        topics="MCP server, testing",
        decisions="Use responses library for HTTP mocks",
        farmos_changes='[{"type": "plant", "id": "abc", "name": "Test Plant"}]',
        questions="Should we add integration tests?",
        summary="Built test suite for MCP server clients.",
        skip=False,
    )

    assert result["success"] is True

    req = responses.calls[0].request
    assert req.headers["Content-Type"] == "text/plain"

    body = json.loads(req.body)
    assert body["action"] == "write_summary"
    assert body["user"] == "Agnes"
    assert body["topics"] == "MCP server, testing"
    assert body["decisions"] == "Use responses library for HTTP mocks"
    assert body["farmos_changes"] == '[{"type": "plant", "id": "abc", "name": "Test Plant"}]'
    assert body["questions"] == "Should we add integration tests?"
    assert body["summary"] == "Built test suite for MCP server clients."
    assert body["skip"] is False


# ── read_activity ─────────────────────────────────────────────


@responses.activate
def test_read_activity_params(client):
    """GET params include action=list, days, and limit."""
    responses.add(
        responses.GET,
        FAKE_ENDPOINT,
        json={"success": True, "summaries": [], "count": 0},
        status=200,
    )

    result = client.read_activity(days=14, limit=10)

    assert result["success"] is True

    req = responses.calls[0].request
    assert "action=list" in req.url
    assert "days=14" in req.url
    assert "limit=10" in req.url


@responses.activate
def test_read_activity_with_user_filter(client):
    """GET includes user param when filtering by user."""
    summaries = [{"user": "Claire", "summary": "Field walk P2R3"}]
    responses.add(
        responses.GET,
        FAKE_ENDPOINT,
        json={"success": True, "summaries": summaries, "count": 1},
        status=200,
    )

    result = client.read_activity(days=7, user="Claire")

    assert result["count"] == 1

    req = responses.calls[0].request
    assert "user=Claire" in req.url
    assert "action=list" in req.url
    assert "days=7" in req.url


# ── search_memory ─────────────────────────────────────────────


@responses.activate
def test_search_memory_params(client):
    """GET params include action=search, query, and days."""
    responses.add(
        responses.GET,
        FAKE_ENDPOINT,
        json={"success": True, "results": [{"summary": "Pigeon pea discussion"}], "count": 1},
        status=200,
    )

    result = client.search_memory(query="pigeon pea", days=60)

    assert result["count"] == 1

    req = responses.calls[0].request
    assert "action=search" in req.url
    assert "query=pigeon" in req.url  # URL-encoded space may vary
    assert "days=60" in req.url


# ── acknowledge_memory ────────────────────────────────────────


@responses.activate
def test_acknowledge_memory_payload(client):
    """POST payload contains action=acknowledge, summary_id, and user."""
    responses.add(
        responses.POST,
        FAKE_ENDPOINT,
        json={"success": True, "message": "Acknowledged"},
        status=200,
    )

    result = client.acknowledge_memory(summary_id="row-42", user="Claire")

    assert result["success"] is True

    req = responses.calls[0].request
    assert req.headers["Content-Type"] == "text/plain"

    body = json.loads(req.body)
    assert body["action"] == "acknowledge"
    assert body["summary_id"] == "row-42"
    assert body["user"] == "Claire"


@responses.activate
def test_acknowledge_memory_error_propagates(client):
    """HTTP errors from acknowledge are raised."""
    responses.add(
        responses.POST,
        FAKE_ENDPOINT,
        json={"error": "Not found"},
        status=404,
    )

    with pytest.raises(Exception):
        client.acknowledge_memory(summary_id="bad-id", user="Agnes")


# ── read_activity with only_fresh_for ─────────────────────────


@responses.activate
def test_read_activity_with_only_fresh_for(client):
    """GET includes only_fresh_for param when filtering fresh entries."""
    responses.add(
        responses.GET,
        FAKE_ENDPOINT,
        json={"success": True, "summaries": [{"user": "James", "summary": "New update"}], "count": 1},
        status=200,
    )

    result = client.read_activity(days=7, only_fresh_for="Claire")

    assert result["count"] == 1

    req = responses.calls[0].request
    assert "only_fresh_for=Claire" in req.url
    assert "action=list" in req.url


@responses.activate
def test_read_activity_without_only_fresh_for(client):
    """GET does not include only_fresh_for when not specified."""
    responses.add(
        responses.GET,
        FAKE_ENDPOINT,
        json={"success": True, "summaries": [], "count": 0},
        status=200,
    )

    client.read_activity(days=7)

    req = responses.calls[0].request
    assert "only_fresh_for" not in req.url
