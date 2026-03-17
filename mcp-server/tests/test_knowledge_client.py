"""
Tests for the KnowledgeClient (knowledge_client.py).

Uses the `responses` library to mock HTTP requests to the Google Apps Script endpoint.
"""

import json

import pytest
import responses

from knowledge_client import KnowledgeClient


FAKE_ENDPOINT = "https://script.google.com/macros/s/FAKE_KNOWLEDGE_ID/exec"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_ENDPOINT", FAKE_ENDPOINT)
    c = KnowledgeClient()
    c.connect()
    return c


# ── Connection ──────────────────────────────────────────────────


def test_connect_success(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_ENDPOINT", FAKE_ENDPOINT)
    c = KnowledgeClient()
    c.connect()
    assert c.is_connected is True
    assert c.endpoint == FAKE_ENDPOINT


def test_connect_missing_env(monkeypatch):
    monkeypatch.delenv("KNOWLEDGE_ENDPOINT", raising=False)
    c = KnowledgeClient()
    with pytest.raises(ValueError, match="Missing KNOWLEDGE_ENDPOINT"):
        c.connect()


def test_not_connected_initially():
    c = KnowledgeClient()
    assert c.is_connected is False


# ── list_entries ────────────────────────────────────────────────


@responses.activate
def test_list_entries_default(client):
    responses.add(
        responses.GET, FAKE_ENDPOINT,
        json={"success": True, "entries": [{"title": "Test"}], "count": 1, "total": 1},
    )

    result = client.list_entries()
    assert result["count"] == 1

    req = responses.calls[0].request
    assert "action=list" in req.url
    assert "limit=50" in req.url
    assert "offset=0" in req.url


@responses.activate
def test_list_entries_with_category(client):
    responses.add(
        responses.GET, FAKE_ENDPOINT,
        json={"success": True, "entries": [], "count": 0, "total": 0},
    )

    client.list_entries(category="composting", limit=10, offset=5)

    req = responses.calls[0].request
    assert "category=composting" in req.url
    assert "limit=10" in req.url
    assert "offset=5" in req.url


# ── search ──────────────────────────────────────────────────────


@responses.activate
def test_search_basic(client):
    responses.add(
        responses.GET, FAKE_ENDPOINT,
        json={"success": True, "results": [{"title": "Pigeon Pea Guide"}], "count": 1},
    )

    result = client.search(query="pigeon pea")
    assert result["count"] == 1

    req = responses.calls[0].request
    assert "action=search" in req.url
    assert "query=pigeon" in req.url


@responses.activate
def test_search_with_category(client):
    responses.add(
        responses.GET, FAKE_ENDPOINT,
        json={"success": True, "results": [], "count": 0},
    )

    client.search(query="frost", category="pests")

    req = responses.calls[0].request
    assert "category=pests" in req.url


# ── get_categories ──────────────────────────────────────────────


@responses.activate
def test_get_categories(client):
    responses.add(
        responses.GET, FAKE_ENDPOINT,
        json={"success": True, "categories": [{"name": "syntropic", "count": 5}]},
    )

    result = client.get_categories()
    assert result["categories"][0]["name"] == "syntropic"

    req = responses.calls[0].request
    assert "action=categories" in req.url


# ── add ─────────────────────────────────────────────────────────


@responses.activate
def test_add_entry(client):
    responses.add(
        responses.POST, FAKE_ENDPOINT,
        json={"success": True, "message": "Added", "entry_id": "abc-123", "row": 5},
    )

    result = client.add(fields={
        "title": "Compost Basics",
        "content": "How to make compost at FFC.",
        "category": "composting",
        "author": "Olivier",
        "tags": "compost,soil,organic",
    })

    assert result["success"] is True
    assert result["entry_id"] == "abc-123"

    req = responses.calls[0].request
    assert req.headers["Content-Type"] == "text/plain"
    body = json.loads(req.body)
    assert body["action"] == "add"
    assert body["title"] == "Compost Basics"
    assert body["category"] == "composting"


# ── update ──────────────────────────────────────────────────────


@responses.activate
def test_update_entry(client):
    responses.add(
        responses.POST, FAKE_ENDPOINT,
        json={"success": True, "message": "Updated", "entry_id": "abc-123", "updated_fields": ["content"]},
    )

    result = client.update("abc-123", {"content": "Updated compost guide."})

    assert result["success"] is True

    body = json.loads(responses.calls[0].request.body)
    assert body["action"] == "update"
    assert body["entry_id"] == "abc-123"
    assert body["content"] == "Updated compost guide."


# ── archive ─────────────────────────────────────────────────────


@responses.activate
def test_archive_entry(client):
    responses.add(
        responses.POST, FAKE_ENDPOINT,
        json={"success": True, "message": "Archived entry: abc-123"},
    )

    result = client.archive("abc-123", reason="Outdated information")

    assert result["success"] is True

    body = json.loads(responses.calls[0].request.body)
    assert body["action"] == "archive"
    assert body["entry_id"] == "abc-123"
    assert body["reason"] == "Outdated information"


# ── error propagation ───────────────────────────────────────────


@responses.activate
def test_http_error_raises(client):
    responses.add(responses.GET, FAKE_ENDPOINT, status=500)

    with pytest.raises(Exception):
        client.list_entries()
