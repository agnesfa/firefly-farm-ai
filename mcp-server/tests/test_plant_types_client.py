"""Tests for the Plant Types Google Sheet client."""
import os
import json
import pytest
import responses

from plant_types_client import PlantTypesClient


MOCK_ENDPOINT = "https://script.google.com/macros/s/test-plant-types/exec"


@pytest.fixture
def client():
    """Create a connected PlantTypesClient with mocked endpoint."""
    os.environ["PLANT_TYPES_ENDPOINT"] = MOCK_ENDPOINT
    c = PlantTypesClient()
    c.connect()
    yield c
    os.environ.pop("PLANT_TYPES_ENDPOINT", None)


def test_connect_success():
    os.environ["PLANT_TYPES_ENDPOINT"] = MOCK_ENDPOINT
    c = PlantTypesClient()
    assert c.connect() is True
    assert c.is_connected is True
    os.environ.pop("PLANT_TYPES_ENDPOINT")


def test_connect_missing_env():
    os.environ.pop("PLANT_TYPES_ENDPOINT", None)
    c = PlantTypesClient()
    with pytest.raises(ValueError, match="Missing PLANT_TYPES_ENDPOINT"):
        c.connect()


@responses.activate
def test_list_all(client):
    responses.add(
        responses.GET, MOCK_ENDPOINT,
        json={"success": True, "plant_types": [
            {"farmos_name": "Pigeon Pea", "strata": "high"},
            {"farmos_name": "Comfrey", "strata": "low"},
        ], "count": 2},
    )
    result = client.list_all()
    assert result["success"] is True
    assert result["count"] == 2
    assert responses.calls[0].request.params["action"] == "list"


@responses.activate
def test_search(client):
    responses.add(
        responses.GET, MOCK_ENDPOINT,
        json={"success": True, "results": [
            {"farmos_name": "Guava", "strata": "emergent"},
        ], "count": 1},
    )
    result = client.search("guava")
    assert result["count"] == 1
    assert responses.calls[0].request.params["query"] == "guava"


@responses.activate
def test_add(client):
    responses.add(
        responses.POST, MOCK_ENDPOINT,
        json={"success": True, "message": "Added plant type: Test Plant", "row": 5},
    )
    result = client.add({"farmos_name": "Test Plant", "strata": "low"})
    assert result["success"] is True
    body = json.loads(responses.calls[0].request.body)
    assert body["action"] == "add"
    assert body["farmos_name"] == "Test Plant"


@responses.activate
def test_update(client):
    responses.add(
        responses.POST, MOCK_ENDPOINT,
        json={"success": True, "message": "Updated plant type: Guava",
              "row": 3, "updated_fields": ["strata"]},
    )
    result = client.update("Guava", {"strata": "emergent"})
    assert result["success"] is True
    body = json.loads(responses.calls[0].request.body)
    assert body["action"] == "update"
    assert body["farmos_name"] == "Guava"
    assert body["strata"] == "emergent"


@responses.activate
def test_get_reconcile_data(client):
    responses.add(
        responses.GET, MOCK_ENDPOINT,
        json={"success": True, "plant_types": [
            {"farmos_name": "Pigeon Pea", "strata": "high", "row_number": 2},
        ], "count": 1},
    )
    result = client.get_reconcile_data()
    assert result["success"] is True
    assert responses.calls[0].request.params["action"] == "reconcile"


@responses.activate
def test_add_error_propagation(client):
    responses.add(
        responses.POST, MOCK_ENDPOINT,
        json={"success": False, "error": "Already exists"},
    )
    result = client.add({"farmos_name": "Duplicate"})
    assert result["success"] is False
