"""Tests for FarmOSClient — farmOS HTTP client with OAuth2 auth.

Uses the `responses` library to mock HTTP at transport level.
Every test that triggers HTTP calls uses @responses.activate.
"""

import pytest
import responses
from requests.exceptions import HTTPError

from farmos_client import FarmOSClient, PLANT_UNIT_UUID


BASE_URL = "https://test.farmos.net"
TOKEN_URL = f"{BASE_URL}/oauth/token"


@pytest.fixture
def env_vars(monkeypatch):
    """Set required farmOS environment variables for tests."""
    monkeypatch.setenv("FARMOS_URL", BASE_URL)
    monkeypatch.setenv("FARMOS_USERNAME", "testuser")
    monkeypatch.setenv("FARMOS_PASSWORD", "testpass")


def _add_token_mock(status=200, body=None):
    """Helper to register the OAuth2 token endpoint mock."""
    if body is None:
        body = {"access_token": "test-token", "token_type": "bearer"}
    responses.add(
        responses.POST,
        TOKEN_URL,
        json=body,
        status=status,
    )


def _connect(env_vars) -> FarmOSClient:
    """Helper: create client, mock token, connect, return client."""
    _add_token_mock()
    client = FarmOSClient()
    client.connect()
    return client


# ── OAuth2 tests ─────────────────────────────────────────────


class TestOAuth2:

    @responses.activate
    def test_connect_success(self, env_vars):
        _add_token_mock()
        client = FarmOSClient()
        result = client.connect()

        assert result is True
        assert client._connected is True
        assert client.session is not None
        assert client.session.headers["Authorization"] == "Bearer test-token"

    def test_connect_missing_env_vars(self, monkeypatch):
        # Clear all farmOS env vars AND prevent load_dotenv from restoring them
        monkeypatch.delenv("FARMOS_URL", raising=False)
        monkeypatch.delenv("FARMOS_USERNAME", raising=False)
        monkeypatch.delenv("FARMOS_PASSWORD", raising=False)
        monkeypatch.setattr("farmos_client.load_dotenv", lambda: None)

        client = FarmOSClient()
        with pytest.raises(ValueError, match="Missing environment variables"):
            client.connect()

    @responses.activate
    def test_connect_auth_failure(self, env_vars):
        _add_token_mock(status=401, body={"error": "invalid_grant"})
        client = FarmOSClient()

        with pytest.raises(ConnectionError, match="OAuth2 authentication failed"):
            client.connect()


# ── Error handling tests ─────────────────────────────────────


class TestErrorHandling:

    @responses.activate
    def test_get_401_disconnects(self, env_vars):
        client = _connect(env_vars)
        responses.add(responses.GET, f"{BASE_URL}/api/asset/plant", status=401)

        assert client._connected is True
        with pytest.raises(ConnectionError, match="authentication expired"):
            client._get("/api/asset/plant")
        assert client._connected is False

    @responses.activate
    def test_get_500_raises(self, env_vars):
        client = _connect(env_vars)
        responses.add(responses.GET, f"{BASE_URL}/api/asset/plant", status=500)

        with pytest.raises(RuntimeError, match="HTTP 500"):
            client._get("/api/asset/plant")

    @responses.activate
    def test_post_422_raises(self, env_vars):
        client = _connect(env_vars)
        responses.add(
            responses.POST,
            f"{BASE_URL}/api/asset/plant",
            json={"errors": [{"detail": "Unprocessable"}]},
            status=422,
        )

        with pytest.raises(HTTPError):
            client._post("/api/asset/plant", {"data": {}})


# ── Pagination tests ─────────────────────────────────────────


class TestPagination:

    @responses.activate
    def test_fetch_all_paginated_single_page(self, env_vars):
        client = _connect(env_vars)
        responses.add(
            responses.GET,
            f"{BASE_URL}/api/taxonomy_term/plant_type",
            json={
                "data": [
                    {"id": "uuid-1", "type": "taxonomy_term--plant_type",
                     "attributes": {"name": "Pigeon Pea"}},
                    {"id": "uuid-2", "type": "taxonomy_term--plant_type",
                     "attributes": {"name": "Comfrey"}},
                ],
                "links": {},
            },
        )

        result = client.fetch_all_paginated("taxonomy_term/plant_type")
        assert len(result) == 2
        assert result[0]["id"] == "uuid-1"
        assert result[1]["id"] == "uuid-2"

    @responses.activate
    def test_fetch_all_paginated_multi_page(self, env_vars):
        client = _connect(env_vars)
        page2_url = f"{BASE_URL}/api/taxonomy_term/plant_type?page[offset]=50"

        # Page 1 with next link
        responses.add(
            responses.GET,
            f"{BASE_URL}/api/taxonomy_term/plant_type",
            json={
                "data": [
                    {"id": "uuid-1", "type": "t", "attributes": {"name": "A"}},
                    {"id": "uuid-2", "type": "t", "attributes": {"name": "B"}},
                ],
                "links": {"next": {"href": page2_url}},
            },
        )
        # Page 2 with a duplicate uuid-2 to test dedup
        responses.add(
            responses.GET,
            page2_url,
            json={
                "data": [
                    {"id": "uuid-2", "type": "t", "attributes": {"name": "B"}},
                    {"id": "uuid-3", "type": "t", "attributes": {"name": "C"}},
                ],
                "links": {},
            },
        )

        result = client.fetch_all_paginated("taxonomy_term/plant_type")
        assert len(result) == 3
        ids = [r["id"] for r in result]
        assert ids == ["uuid-1", "uuid-2", "uuid-3"]

    @responses.activate
    def test_fetch_plants_contains_url_construction(self, env_vars):
        client = _connect(env_vars)
        responses.add(
            responses.GET,
            f"{BASE_URL}/api/asset/plant",
            json={"data": [], "links": {}},
        )

        client._fetch_plants_contains("P2R3.14-21")

        # Verify the request URL contains CONTAINS filter params
        request_url = responses.calls[-1].request.url
        assert "filter%5Bname%5D%5Boperator%5D=CONTAINS" in request_url
        assert "P2R3.14-21" in request_url
        assert "filter%5Bstatus%5D=active" in request_url


# ── Quantity merging tests ───────────────────────────────────


class TestQuantityMerging:

    def test_merge_included_quantities(self):
        data = {
            "included": [
                {
                    "type": "quantity--standard",
                    "id": "qty-1",
                    "attributes": {"value": {"decimal": "4"}, "measure": "count"},
                },
                {
                    "type": "quantity--standard",
                    "id": "qty-2",
                    "attributes": {"value": {"decimal": "10"}, "measure": "count"},
                },
            ]
        }
        items = [
            {
                "id": "log-1",
                "relationships": {
                    "quantity": {
                        "data": [{"id": "qty-1", "type": "quantity--standard"}]
                    }
                },
            },
            {
                "id": "log-2",
                "relationships": {
                    "quantity": {
                        "data": [{"id": "qty-2", "type": "quantity--standard"}]
                    }
                },
            },
        ]

        FarmOSClient._merge_included_quantities(data, items)

        assert len(items[0]["_quantities"]) == 1
        assert items[0]["_quantities"][0]["id"] == "qty-1"
        assert items[1]["_quantities"][0]["attributes"]["value"]["decimal"] == "10"

    def test_merge_no_included(self):
        data = {"included": []}
        items = [
            {
                "id": "log-1",
                "relationships": {
                    "quantity": {"data": [{"id": "qty-x", "type": "quantity--standard"}]}
                },
            },
        ]

        result = FarmOSClient._merge_included_quantities(data, items)

        # Should return items unchanged, no crash, no _quantities key added
        assert result is items
        assert "_quantities" not in items[0]


# ── Entity creation tests ───────────────────────────────────


class TestEntityCreation:

    @responses.activate
    def test_create_quantity_payload(self, env_vars):
        client = _connect(env_vars)
        responses.add(
            responses.POST,
            f"{BASE_URL}/api/quantity/standard",
            json={"data": {"id": "new-qty-id", "type": "quantity--standard"}},
            status=201,
        )

        result = client.create_quantity("plant-uuid-123", count=5, adjustment="reset")

        assert result == "new-qty-id"

        # Verify the POST payload
        payload = responses.calls[-1].request.body
        import json
        body = json.loads(payload)
        qty_data = body["data"]
        assert qty_data["type"] == "quantity--standard"
        assert qty_data["attributes"]["value"] == {"decimal": "5"}
        assert qty_data["attributes"]["measure"] == "count"
        assert qty_data["attributes"]["inventory_adjustment"] == "reset"
        assert qty_data["relationships"]["units"]["data"]["id"] == PLANT_UNIT_UUID
        assert qty_data["relationships"]["inventory_asset"]["data"]["id"] == "plant-uuid-123"
        assert qty_data["relationships"]["inventory_asset"]["data"]["type"] == "asset--plant"

    @responses.activate
    def test_create_observation_log(self, env_vars):
        client = _connect(env_vars)
        responses.add(
            responses.POST,
            f"{BASE_URL}/api/log/observation",
            json={"data": {"id": "obs-log-id", "type": "log--observation"}},
            status=201,
        )

        result = client.create_observation_log(
            plant_id="plant-1",
            section_uuid="section-1",
            quantity_id="qty-1",
            timestamp=1710000000,
            name="Inventory P2R3.14-21 - Pigeon Pea",
            notes="3 healthy",
        )

        assert result == "obs-log-id"

        import json
        body = json.loads(responses.calls[-1].request.body)
        log_data = body["data"]
        assert log_data["type"] == "log--observation"
        assert log_data["attributes"]["is_movement"] is True
        assert log_data["attributes"]["status"] == "done"
        assert log_data["attributes"]["notes"] == {"value": "3 healthy", "format": "default"}
        assert log_data["relationships"]["asset"]["data"] == [
            {"type": "asset--plant", "id": "plant-1"}
        ]
        assert log_data["relationships"]["location"]["data"] == [
            {"type": "asset--land", "id": "section-1"}
        ]
        assert log_data["relationships"]["quantity"]["data"] == [
            {"type": "quantity--standard", "id": "qty-1"}
        ]

    @responses.activate
    def test_create_plant_asset(self, env_vars):
        client = _connect(env_vars)
        responses.add(
            responses.POST,
            f"{BASE_URL}/api/asset/plant",
            json={"data": {"id": "new-plant-id", "type": "asset--plant"}},
            status=201,
        )

        result = client.create_plant_asset(
            name="25 APR 2025 - Pigeon Pea - P2R2.0-3",
            plant_type_uuid="pt-uuid-456",
            notes="Planted from nursery stock",
        )

        assert result == "new-plant-id"

        import json
        body = json.loads(responses.calls[-1].request.body)
        data = body["data"]
        assert data["type"] == "asset--plant"
        assert data["attributes"]["name"] == "25 APR 2025 - Pigeon Pea - P2R2.0-3"
        assert data["attributes"]["status"] == "active"
        assert data["relationships"]["plant_type"]["data"] == [
            {"type": "taxonomy_term--plant_type", "id": "pt-uuid-456"}
        ]

    @responses.activate
    def test_create_plant_type(self, env_vars):
        client = _connect(env_vars)
        responses.add(
            responses.POST,
            f"{BASE_URL}/api/taxonomy_term/plant_type",
            json={"data": {"id": "new-type-id", "type": "taxonomy_term--plant_type"}},
            status=201,
        )

        result = client.create_plant_type(
            name="Pigeon Pea",
            description="Fast-growing nitrogen-fixing pioneer.",
            maturity_days=120,
            transplant_days=30,
        )

        assert result == "new-type-id"

        import json
        body = json.loads(responses.calls[-1].request.body)
        data = body["data"]
        assert data["type"] == "taxonomy_term--plant_type"
        assert data["attributes"]["name"] == "Pigeon Pea"
        assert data["attributes"]["description"] == {
            "value": "Fast-growing nitrogen-fixing pioneer.",
            "format": "default",
        }
        assert data["attributes"]["maturity_days"] == 120
        assert data["attributes"]["transplant_days"] == 30

        # Verify POST went to the correct endpoint
        assert responses.calls[-1].request.url == f"{BASE_URL}/api/taxonomy_term/plant_type"
