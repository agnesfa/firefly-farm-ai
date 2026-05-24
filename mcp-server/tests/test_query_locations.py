"""query_locations tool + client.get_locations tests.

Mirrors mcp-server-ts/plugins/farm-plugin/src/__tests__/query-locations.test.ts.

The 2026-05-24 gap: query_sections silently returns 0 for row-level (P1R2)
and paddock-level (P1) assets because its regex only matches section-shaped
names. query_locations exposes the full land+structure surface so we can
confirm assets exist before triggering a create that would duplicate them.
"""

import json
import sys
import os
from unittest.mock import MagicMock

import pytest
import responses

# Ensure mcp-server is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import server
from farmos_client import FarmOSClient


BASE_URL = "https://test.farmos.net"
TOKEN_URL = f"{BASE_URL}/oauth/token"


@pytest.fixture
def env_vars(monkeypatch):
    monkeypatch.setenv("FARMOS_URL", BASE_URL)
    monkeypatch.setenv("FARMOS_USERNAME", "testuser")
    monkeypatch.setenv("FARMOS_PASSWORD", "testpass")


def _add_token_mock():
    responses.add(
        responses.POST,
        TOKEN_URL,
        json={"access_token": "test-token", "token_type": "bearer"},
        status=200,
    )


def _connect(env_vars) -> FarmOSClient:
    _add_token_mock()
    client = FarmOSClient()
    client.connect()
    return client


def _land(name, uuid, archived=False, parent_uuids=None):
    parent_data = [{"type": "asset--land", "id": p} for p in (parent_uuids or [])]
    return {
        "id": uuid,
        "type": "asset--land",
        "attributes": {"name": name, "archived": archived, "land_type": "paddock"},
        "relationships": {"parent": {"data": parent_data}},
    }


def _structure(name, uuid, archived=False):
    return {
        "id": uuid,
        "type": "asset--structure",
        "attributes": {"name": name, "archived": archived, "structure_type": "shelf"},
        "relationships": {"parent": {"data": []}},
    }


# ── client.get_locations (HTTP-mocked) ─────────────────────────────────────


class TestGetLocations:

    @responses.activate
    def test_classifies_every_level(self, env_vars):
        client = _connect(env_vars)

        # asset/land — paginated: one full page, then empty
        responses.add(
            responses.GET,
            f"{BASE_URL}/api/asset/land",
            json={
                "data": [
                    _land("P1", "uuid-paddock-1"),
                    _land("P2", "uuid-paddock-2"),
                    _land("P1R2", "uuid-row-p1r2", parent_uuids=["uuid-paddock-1"]),
                    _land("P2R3", "uuid-row-p2r3", parent_uuids=["uuid-paddock-2"]),
                    _land("P1R2.0-14", "uuid-section-1", parent_uuids=["uuid-row-p1r2"]),
                    _land("NURS.GR", "uuid-nurs"),
                    _land("COMP.BAY1", "uuid-comp"),
                    _land("Dam", "uuid-other"),
                ],
                "links": {},
            },
        )
        responses.add(
            responses.GET,
            f"{BASE_URL}/api/asset/land",
            json={"data": [], "links": {}},
        )
        # asset/structure
        responses.add(
            responses.GET,
            f"{BASE_URL}/api/asset/structure",
            json={"data": [_structure("NURS.SH1-1", "uuid-struct-1")], "links": {}},
        )
        responses.add(
            responses.GET,
            f"{BASE_URL}/api/asset/structure",
            json={"data": [], "links": {}},
        )

        locations = client.get_locations()

        assert len(locations) == 9
        by_level = {}
        for loc in locations:
            by_level[loc["level"]] = by_level.get(loc["level"], 0) + 1
        assert by_level == {
            "paddock": 2, "row": 2, "section": 1, "nursery": 1,
            "compost": 1, "structure": 1, "other": 1,
        }

    @responses.activate
    def test_hides_archived_by_default(self, env_vars):
        client = _connect(env_vars)
        responses.add(
            responses.GET,
            f"{BASE_URL}/api/asset/land",
            json={
                "data": [
                    _land("P1R2", "uuid-active"),
                    _land("P1R9-old", "uuid-archived", archived=True),
                ],
                "links": {},
            },
        )
        responses.add(responses.GET, f"{BASE_URL}/api/asset/land", json={"data": [], "links": {}})
        responses.add(responses.GET, f"{BASE_URL}/api/asset/structure", json={"data": [], "links": {}})

        locations = client.get_locations()
        assert [l["uuid"] for l in locations] == ["uuid-active"]

    @responses.activate
    def test_includes_archived_when_requested(self, env_vars):
        client = _connect(env_vars)
        responses.add(
            responses.GET,
            f"{BASE_URL}/api/asset/land",
            json={
                "data": [
                    _land("P1R2", "uuid-active"),
                    _land("P1R9-old", "uuid-archived", archived=True),
                ],
                "links": {},
            },
        )
        responses.add(responses.GET, f"{BASE_URL}/api/asset/land", json={"data": [], "links": {}})
        responses.add(responses.GET, f"{BASE_URL}/api/asset/structure", json={"data": [], "links": {}})

        locations = client.get_locations(include_archived=True)
        assert sorted(l["uuid"] for l in locations) == ["uuid-active", "uuid-archived"]


# ── query_locations tool (mocked client) ───────────────────────────────────


FULL_LOCATIONS = [
    {"name": "COMP.BAY1", "uuid": "uuid-comp", "level": "compost", "asset_type": "land", "archived": False, "parent_uuids": []},
    {"name": "Dam", "uuid": "uuid-other", "level": "other", "asset_type": "land", "archived": False, "parent_uuids": []},
    {"name": "NURS.GR", "uuid": "uuid-nurs-1", "level": "nursery", "asset_type": "land", "archived": False, "parent_uuids": []},
    {"name": "NURS.SH1-1", "uuid": "uuid-struct-1", "level": "structure", "asset_type": "structure", "archived": False, "parent_uuids": []},
    {"name": "P1", "uuid": "uuid-paddock-1", "level": "paddock", "asset_type": "land", "archived": False, "parent_uuids": []},
    {"name": "P1R2", "uuid": "uuid-row-p1r2", "level": "row", "asset_type": "land", "archived": False, "parent_uuids": ["uuid-paddock-1"]},
    {"name": "P1R2.0-14", "uuid": "uuid-section-1", "level": "section", "asset_type": "land", "archived": False, "parent_uuids": ["uuid-row-p1r2"]},
    {"name": "P2", "uuid": "uuid-paddock-2", "level": "paddock", "asset_type": "land", "archived": False, "parent_uuids": []},
    {"name": "P2R3", "uuid": "uuid-row-p2r3", "level": "row", "asset_type": "land", "archived": False, "parent_uuids": ["uuid-paddock-2"]},
]


@pytest.fixture
def mock_with_locations(monkeypatch):
    mock = MagicMock(spec=FarmOSClient)
    mock.get_locations.return_value = list(FULL_LOCATIONS)
    monkeypatch.setattr(server, "get_client", lambda: mock)
    return mock


class TestQueryLocationsTool:

    def test_level_all_returns_everything(self, mock_with_locations):
        result = json.loads(server.query_locations())
        assert result["count"] == len(FULL_LOCATIONS)
        assert result["total"] == len(FULL_LOCATIONS)
        assert result["by_level"]["paddock"] == 2
        assert result["by_level"]["row"] == 2
        assert result["by_level"]["section"] == 1

    def test_level_row_returns_only_rows(self, mock_with_locations):
        result = json.loads(server.query_locations(level="row"))
        assert result["count"] == 2
        assert sorted(l["name"] for l in result["locations"]) == ["P1R2", "P2R3"]

    def test_level_paddock_returns_only_paddocks(self, mock_with_locations):
        result = json.loads(server.query_locations(level="paddock"))
        assert result["count"] == 2
        assert sorted(l["name"] for l in result["locations"]) == ["P1", "P2"]

    def test_level_section_returns_only_sections(self, mock_with_locations):
        result = json.loads(server.query_locations(level="section"))
        assert result["count"] == 1
        assert result["locations"][0]["name"] == "P1R2.0-14"

    def test_level_structure_returns_only_structures(self, mock_with_locations):
        result = json.loads(server.query_locations(level="structure"))
        assert result["count"] == 1
        assert result["locations"][0]["name"] == "NURS.SH1-1"

    def test_level_nursery_returns_only_nursery(self, mock_with_locations):
        result = json.loads(server.query_locations(level="nursery"))
        assert result["count"] == 1
        assert result["locations"][0]["name"] == "NURS.GR"

    def test_name_resolves_the_row_asset(self, mock_with_locations):
        """The 2026-05-24 gap: confirm row asset is findable by name."""
        result = json.loads(server.query_locations(name="P1R2"))
        assert result["count"] == 1
        assert result["locations"][0]["uuid"] == "uuid-row-p1r2"
        assert result["locations"][0]["level"] == "row"

    def test_name_prefix_returns_all_matches(self, mock_with_locations):
        result = json.loads(server.query_locations(name_prefix="P1R"))
        # P1R2 (row) + P1R2.0-14 (section)
        assert result["count"] == 2
        names = sorted(l["name"] for l in result["locations"])
        assert names == ["P1R2", "P1R2.0-14"]

    def test_name_prefix_plus_level_narrows(self, mock_with_locations):
        result = json.loads(server.query_locations(name_prefix="P1R", level="row"))
        assert result["count"] == 1
        assert result["locations"][0]["name"] == "P1R2"

    def test_include_archived_forwarded_to_client(self, mock_with_locations):
        server.query_locations(include_archived=True)
        mock_with_locations.get_locations.assert_called_with(include_archived=True)
