"""query_logs section_id filter — attachment vs name-substring.

The 2026-05-24 diagnostic: query_logs(section_id="P1R2") returned 0 even
though P1R2 has logs in farmOS. Root cause: the filter was matching on the
log NAME substring rather than the log's `location` relationship. This test
suite locks in the new behaviour for both the client (Layer 2) and the
tool (Layer 3a):

  - When section_id resolves to a known asset → filter[location.id]=UUID
  - When section_id does NOT resolve            → name-substring fallback
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


# ── Client: get_logs_with_method ───────────────────────────────────────────


class TestGetLogsWithMethod:

    @responses.activate
    def test_attachment_filter_when_section_resolves(self, env_vars):
        client = _connect(env_vars)
        # get_section_uuid → fetch_by_name on asset/land → returns the row
        responses.add(
            responses.GET,
            f"{BASE_URL}/api/asset/land",
            json={"data": [{"id": "uuid-row-p1r2", "attributes": {"name": "P1R2"}}], "links": {}},
        )
        # 5 log types, each empty
        for _ in range(5):
            responses.add(
                responses.GET,
                f"{BASE_URL}/api/log/observation",
                json={"data": [], "links": {}},
            )
            responses.add(
                responses.GET,
                f"{BASE_URL}/api/log/activity",
                json={"data": [], "links": {}},
            )
            responses.add(
                responses.GET,
                f"{BASE_URL}/api/log/transplanting",
                json={"data": [], "links": {}},
            )
            responses.add(
                responses.GET,
                f"{BASE_URL}/api/log/harvest",
                json={"data": [], "links": {}},
            )
            responses.add(
                responses.GET,
                f"{BASE_URL}/api/log/seeding",
                json={"data": [], "links": {}},
            )

        logs, method = client.get_logs_with_method(section_id="P1R2", max_results=20)
        assert method == "location-id"
        # Verify at least one call used the attachment filter
        urls = [c.request.url for c in responses.calls]
        attachment_calls = [u for u in urls if "filter%5Blocation.id%5D=uuid-row-p1r2" in u
                            or "filter[location.id]=uuid-row-p1r2" in u]
        assert len(attachment_calls) >= 1, f"No attachment filter in URLs: {urls}"

    @responses.activate
    def test_falls_back_to_name_substring_when_section_unknown(self, env_vars):
        client = _connect(env_vars)
        # get_section_uuid: land empty, structure empty → unresolved
        responses.add(
            responses.GET,
            f"{BASE_URL}/api/asset/land",
            json={"data": [], "links": {}},
        )
        responses.add(
            responses.GET,
            f"{BASE_URL}/api/asset/structure",
            json={"data": [], "links": {}},
        )
        for _ in range(5):
            for lt in ["observation", "activity", "transplanting", "harvest", "seeding"]:
                responses.add(
                    responses.GET,
                    f"{BASE_URL}/api/log/{lt}",
                    json={"data": [], "links": {}},
                )

        logs, method = client.get_logs_with_method(section_id="BOGUS", max_results=20)
        assert method == "name-substring (fallback)"
        urls = [c.request.url for c in responses.calls]
        # Should NOT have hit filter[location.id]
        assert not any("filter%5Blocation.id%5D" in u or "filter[location.id]" in u for u in urls)
        # SHOULD have hit the CONTAINS filter
        contains_calls = [u for u in urls if "operator%5D=CONTAINS" in u or "operator]=CONTAINS" in u]
        assert len(contains_calls) >= 1

    @responses.activate
    def test_species_only_uses_name_substring(self, env_vars):
        client = _connect(env_vars)
        for _ in range(5):
            for lt in ["observation", "activity", "transplanting", "harvest", "seeding"]:
                responses.add(
                    responses.GET,
                    f"{BASE_URL}/api/log/{lt}",
                    json={"data": [], "links": {}},
                )

        logs, method = client.get_logs_with_method(species="Pigeon Pea", max_results=20)
        assert method == "name-substring"

    @responses.activate
    def test_no_filters_returns_filter_method_none(self, env_vars):
        client = _connect(env_vars)
        for lt in ["observation", "activity", "transplanting", "harvest", "seeding"]:
            responses.add(
                responses.GET,
                f"{BASE_URL}/api/log/{lt}",
                json={"data": [], "links": {}},
            )

        logs, method = client.get_logs_with_method(max_results=20)
        assert method == "none"


# ── Tool: query_logs surfaces filter_method ────────────────────────────────


class TestQueryLogsToolSurfacesFilterMethod:

    def test_reports_location_id_when_resolved(self, monkeypatch):
        mock = MagicMock(spec=FarmOSClient)
        mock.get_logs_with_method.return_value = ([], "location-id")
        monkeypatch.setattr(server, "get_client", lambda: mock)

        result = json.loads(server.query_logs(section_id="P1R2"))
        assert result["filter_method"] == "location-id"

    def test_reports_fallback_when_section_unknown(self, monkeypatch):
        mock = MagicMock(spec=FarmOSClient)
        mock.get_logs_with_method.return_value = ([], "name-substring (fallback)")
        monkeypatch.setattr(server, "get_client", lambda: mock)

        result = json.loads(server.query_logs(section_id="BOGUS"))
        assert result["filter_method"] == "name-substring (fallback)"

    def test_reports_none_when_no_filters(self, monkeypatch):
        mock = MagicMock(spec=FarmOSClient)
        mock.get_logs_with_method.return_value = ([], "none")
        monkeypatch.setattr(server, "get_client", lambda: mock)

        result = json.loads(server.query_logs())
        assert result["filter_method"] == "none"

    def test_existing_get_logs_callers_unchanged(self, monkeypatch):
        """Other callers using client.get_logs() (not the with-method variant)
        keep getting a plain list — back-compat is preserved."""
        mock = MagicMock(spec=FarmOSClient)
        # get_logs is a thin wrapper around get_logs_with_method
        mock.get_logs.return_value = []
        # Validate: server.get_plant_detail still works (it uses get_logs, not _with_method)
        mock.fetch_by_name.return_value = []
        mock.get_plant_assets.return_value = []
        monkeypatch.setattr(server, "get_client", lambda: mock)

        result = json.loads(server.get_plant_detail("Nonexistent"))
        assert "error" in result
