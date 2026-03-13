"""
Tests for the ObservationClient (observe_client.py).

Uses the `responses` library to mock HTTP requests to the Google Apps Script endpoint.
"""

import json
import os

import pytest
import responses

from observe_client import ObservationClient


FAKE_ENDPOINT = "https://script.google.com/macros/s/FAKE_DEPLOY_ID/exec"


@pytest.fixture
def client(monkeypatch):
    """Return a connected ObservationClient with a fake endpoint."""
    monkeypatch.setenv("OBSERVE_ENDPOINT", FAKE_ENDPOINT)
    c = ObservationClient()
    c.connect()
    return c


# ── Connection tests ──────────────────────────────────────────


def test_connect_success(monkeypatch):
    """Setting OBSERVE_ENDPOINT env var connects successfully."""
    monkeypatch.setenv("OBSERVE_ENDPOINT", FAKE_ENDPOINT)
    c = ObservationClient()
    c.connect()
    assert c.is_connected is True
    assert c.endpoint == FAKE_ENDPOINT


def test_connect_missing_env(monkeypatch):
    """Missing OBSERVE_ENDPOINT raises ValueError."""
    monkeypatch.delenv("OBSERVE_ENDPOINT", raising=False)
    monkeypatch.setattr("observe_client.load_dotenv", lambda: None)
    c = ObservationClient()
    with pytest.raises(ValueError, match="Missing OBSERVE_ENDPOINT"):
        c.connect()


# ── list_observations ─────────────────────────────────────────


@responses.activate
def test_list_observations_no_filters(client):
    """GET with action=list only when no filters provided."""
    responses.add(
        responses.GET,
        FAKE_ENDPOINT,
        json={"success": True, "observations": [], "count": 0},
        status=200,
    )

    result = client.list_observations()

    assert result["success"] is True
    assert result["count"] == 0

    # Verify request params
    req = responses.calls[0].request
    assert "action=list" in req.url
    # No extra filter params
    assert "status=" not in req.url
    assert "section=" not in req.url


@responses.activate
def test_list_observations_with_filters(client):
    """GET includes status and section params when provided."""
    obs = [{"species": "Pigeon Pea", "section_id": "P2R3.14-21", "status": "pending"}]
    responses.add(
        responses.GET,
        FAKE_ENDPOINT,
        json={"success": True, "observations": obs, "count": 1},
        status=200,
    )

    result = client.list_observations(status="pending", section="P2R3.14-21")

    assert result["count"] == 1
    req = responses.calls[0].request
    assert "status=pending" in req.url
    assert "section=P2R3.14-21" in req.url


# ── update_status ─────────────────────────────────────────────


@responses.activate
def test_update_status_payload(client):
    """POST payload has action=update_status and correct Content-Type."""
    responses.add(
        responses.POST,
        FAKE_ENDPOINT,
        json={"success": True, "updated": 2, "errors": []},
        status=200,
    )

    updates = [
        {"submission_id": "abc123", "status": "approved", "reviewer": "Claire", "notes": "Looks good"},
        {"submission_id": "def456", "status": "rejected", "reviewer": "Claire", "notes": "Wrong section"},
    ]
    result = client.update_status(updates)

    assert result["success"] is True
    assert result["updated"] == 2

    req = responses.calls[0].request
    assert req.headers["Content-Type"] == "text/plain"

    body = json.loads(req.body)
    assert body["action"] == "update_status"
    assert len(body["updates"]) == 2
    assert body["updates"][0]["submission_id"] == "abc123"
    assert body["updates"][1]["status"] == "rejected"


# ── delete_imported ───────────────────────────────────────────


@responses.activate
def test_delete_imported_payload(client):
    """POST payload has action=delete_imported and submission_id."""
    responses.add(
        responses.POST,
        FAKE_ENDPOINT,
        json={"success": True, "deleted": 3},
        status=200,
    )

    result = client.delete_imported("sub_789")

    assert result["deleted"] == 3

    req = responses.calls[0].request
    body = json.loads(req.body)
    assert body["action"] == "delete_imported"
    assert body["submission_id"] == "sub_789"


# ── get_media ─────────────────────────────────────────────────


@responses.activate
def test_get_media_params(client):
    """GET params include action=get_media and submission_id."""
    responses.add(
        responses.GET,
        FAKE_ENDPOINT,
        json={"success": True, "files": [{"filename": "photo.jpg", "mime_type": "image/jpeg", "data_base64": "..."}]},
        status=200,
    )

    result = client.get_media("sub_001")

    assert result["success"] is True
    assert len(result["files"]) == 1

    req = responses.calls[0].request
    assert "action=get_media" in req.url
    assert "submission_id=sub_001" in req.url


# ── Error handling ────────────────────────────────────────────


@responses.activate
def test_list_observations_error(client):
    """HTTP 500 raises requests.exceptions.HTTPError."""
    responses.add(
        responses.GET,
        FAKE_ENDPOINT,
        json={"error": "Internal server error"},
        status=500,
    )

    with pytest.raises(Exception) as exc_info:
        client.list_observations()

    # requests raises HTTPError on raise_for_status()
    assert "500" in str(exc_info.value)
