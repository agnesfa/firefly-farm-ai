"""
Tests for MCP server read tools (server.py).

Monkeypatches server.get_client() to return a mock FarmOSClient,
then calls the tool functions directly and verifies output.
"""

import json
import sys
import os

import pytest

# Ensure mcp-server is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import server
from tests.conftest import make_plant_asset, make_log, make_plant_type, make_section_asset


# ── query_plants ──────────────────────────────────────────────


def test_query_plants_returns_formatted(monkeypatch, mock_farmos_client):
    """query_plants returns JSON with count and plant results."""
    plants = [
        make_plant_asset(name="25 APR 2025 - Pigeon Pea - P2R2.0-3", inventory_count=4),
        make_plant_asset(name="25 APR 2025 - Comfrey - P2R2.0-3", inventory_count=6),
    ]
    mock_farmos_client.get_plant_assets.return_value = plants
    monkeypatch.setattr(server, "get_client", lambda: mock_farmos_client)

    result = json.loads(server.query_plants(section_id="P2R2.0-3"))

    assert result["count"] == 2
    assert len(result["plants"]) == 2
    assert result["filters"]["section_id"] == "P2R2.0-3"
    # Verify plant names appear in formatted output
    species_names = [p["species"] for p in result["plants"]]
    assert "Pigeon Pea" in species_names
    assert "Comfrey" in species_names


# ── get_plant_detail ──────────────────────────────────────────


def test_get_plant_detail_found(monkeypatch, mock_farmos_client):
    """get_plant_detail returns plant details and associated logs."""
    plant = make_plant_asset(
        name="25 APR 2025 - Pigeon Pea - P2R2.0-3",
        inventory_count=4,
    )
    logs = [
        make_log(name="Observation P2R2.0-3 — Pigeon Pea", log_type="observation"),
        make_log(name="Transplanting P2R2.0-3 — Pigeon Pea", log_type="transplanting"),
    ]
    mock_farmos_client.fetch_by_name.return_value = [plant]
    mock_farmos_client.get_logs.return_value = logs
    monkeypatch.setattr(server, "get_client", lambda: mock_farmos_client)

    result = json.loads(server.get_plant_detail("25 APR 2025 - Pigeon Pea - P2R2.0-3"))

    assert "plant" in result
    assert result["plant"]["species"] == "Pigeon Pea"
    assert result["plant"]["section"] == "P2R2.0-3"
    assert result["log_count"] == 2
    assert len(result["logs"]) == 2


def test_get_plant_detail_not_found(monkeypatch, mock_farmos_client):
    """get_plant_detail returns error when plant not found."""
    mock_farmos_client.fetch_by_name.return_value = []
    mock_farmos_client.get_plant_assets.return_value = []
    monkeypatch.setattr(server, "get_client", lambda: mock_farmos_client)

    result = json.loads(server.get_plant_detail("Nonexistent Plant"))

    assert "error" in result
    assert "not found" in result["error"].lower()


# ── get_inventory ─────────────────────────────────────────────


def test_get_inventory_groups_by_section(monkeypatch, mock_farmos_client):
    """get_inventory groups results by section when querying by species."""
    plants = [
        make_plant_asset(name="25 APR 2025 - Pigeon Pea - P2R2.0-3", inventory_count=4),
        make_plant_asset(name="25 APR 2025 - Pigeon Pea - P2R3.15-21", inventory_count=3),
    ]
    mock_farmos_client.get_plant_assets.return_value = plants
    monkeypatch.setattr(server, "get_client", lambda: mock_farmos_client)

    result = json.loads(server.get_inventory(species="Pigeon Pea"))

    assert result["summary"]["total_species_entries"] == 2
    assert result["summary"]["total_plant_count"] == 7
    # by_section present when species spans multiple sections
    assert "by_section" in result
    assert len(result["by_section"]) == 2
    sections = [s["section"] for s in result["by_section"]]
    assert "P2R2.0-3" in sections
    assert "P2R3.15-21" in sections


# ── query_sections ────────────────────────────────────────────


def test_query_sections_groups_by_row(monkeypatch, mock_farmos_client):
    """query_sections groups section results by row prefix."""
    sections = [
        make_section_asset(name="P2R2.0-3"),
        make_section_asset(name="P2R2.3-7"),
        make_section_asset(name="P2R3.15-21"),
    ]
    # Plants for the count index
    all_plants = [
        make_plant_asset(name="25 APR 2025 - Pigeon Pea - P2R2.0-3"),
        make_plant_asset(name="25 APR 2025 - Comfrey - P2R2.0-3"),
        make_plant_asset(name="25 APR 2025 - Macadamia - P2R3.15-21"),
    ]
    mock_farmos_client.get_section_assets.return_value = sections
    mock_farmos_client.fetch_all_paginated.return_value = all_plants
    monkeypatch.setattr(server, "get_client", lambda: mock_farmos_client)

    result = json.loads(server.query_sections())

    assert result["total_sections"] == 3
    assert "P2R2" in result["rows"]
    assert "P2R3" in result["rows"]
    assert len(result["rows"]["P2R2"]) == 2
    assert len(result["rows"]["P2R3"]) == 1
    # Verify plant counts
    r2_counts = {s["section_id"]: s["plant_count"] for s in result["rows"]["P2R2"]}
    assert r2_counts["P2R2.0-3"] == 2
    assert r2_counts["P2R2.3-7"] == 0


# ── search_plant_types ────────────────────────────────────────


def test_search_plant_types_case_insensitive(monkeypatch, mock_farmos_client):
    """search_plant_types matches case-insensitively."""
    types = [
        make_plant_type(name="Pigeon Pea", description="Pioneer nitrogen fixer"),
        make_plant_type(name="Sweet Potato", description="Living mulch groundcover"),
        make_plant_type(name="Peanut", description="Legume groundcover"),
    ]
    mock_farmos_client.get_plant_type_details.return_value = types
    monkeypatch.setattr(server, "get_client", lambda: mock_farmos_client)

    # Lowercase query should match "Pigeon Pea" and "Sweet Potato" (contains "pea"/"pea")
    result = json.loads(server.search_plant_types("pea"))

    assert result["query"] == "pea"
    # "Pigeon Pea" and "Peanut" contain "pea"
    assert result["count"] == 2
    matched_names = [t["name"] for t in result["plant_types"]]
    assert "Pigeon Pea" in matched_names
    assert "Peanut" in matched_names
    assert "Sweet Potato" not in matched_names


# ── get_all_plant_types ──────────────────────────────────────


def test_get_all_plant_types_returns_all_sorted(monkeypatch, mock_farmos_client):
    """get_all_plant_types returns all types sorted alphabetically."""
    types = [
        make_plant_type(name="Sweet Potato", description="Living mulch"),
        make_plant_type(name="Comfrey", description="Nutrient accumulator"),
        make_plant_type(name="Pigeon Pea", description="Pioneer nitrogen fixer"),
    ]
    mock_farmos_client.get_all_plant_types_cached.return_value = types
    monkeypatch.setattr(server, "get_client", lambda: mock_farmos_client)

    result = json.loads(server.get_all_plant_types())

    assert result["count"] == 3
    names = [t["name"] for t in result["plant_types"]]
    assert names == ["Comfrey", "Pigeon Pea", "Sweet Potato"]


def test_get_all_plant_types_uses_cache(monkeypatch, mock_farmos_client):
    """get_all_plant_types calls cached method, not raw fetch."""
    mock_farmos_client.get_all_plant_types_cached.return_value = []
    monkeypatch.setattr(server, "get_client", lambda: mock_farmos_client)

    server.get_all_plant_types()

    mock_farmos_client.get_all_plant_types_cached.assert_called_once()


# ── farm_context ─────────────────────────────────────────────────


def _build_plant_type_with_metadata(name, strata="low", succession="secondary"):
    """Build a plant type with syntropic metadata in the description."""
    desc = f"A plant.\n\n---\n**Syntropic Agriculture Data:**\n**Strata:** {strata.title()}\n**Succession Stage:** {succession.title()}"
    return make_plant_type(name=name, description=desc)


def _setup_farm_context_mocks(monkeypatch, mock_farmos_client, plants, logs, plant_types, kb_entries=None, memory_sessions=None):
    """Common setup for farm_context tests."""
    from unittest.mock import MagicMock

    mock_farmos_client.get_plant_assets.return_value = plants
    mock_farmos_client.get_logs.return_value = logs
    mock_farmos_client.get_all_plant_types_cached.return_value = plant_types
    monkeypatch.setattr(server, "get_client", lambda: mock_farmos_client)

    # Mock knowledge client
    mock_kb = MagicMock()
    if kb_entries is not None:
        mock_kb.search.return_value = kb_entries
    else:
        mock_kb.search.return_value = []
    monkeypatch.setattr(server, "get_knowledge_client", lambda: mock_kb)

    # Mock memory client
    mock_mem = MagicMock()
    mock_mem.is_connected = True
    mock_mem.search_memory.return_value = {"results": memory_sessions or [], "count": len(memory_sessions or [])}
    monkeypatch.setattr(server, "get_memory_client", lambda: mock_mem)

    # Clear semantics cache so it loads fresh YAML
    from semantics import clear_caches
    clear_caches()


class TestFarmContextSection:
    """Tests for farm_context(section=...) mode."""

    def test_section_returns_all_five_layers(self, monkeypatch, mock_farmos_client):
        """farm_context section mode returns ontology, facts, interpretation, context, gaps."""
        plants = [
            make_plant_asset(name="25 APR 2025 - Ice Cream Bean - P2R3.15-21", inventory_count=4),
            make_plant_asset(name="25 APR 2025 - Pigeon Pea - P2R3.15-21", inventory_count=2),
            make_plant_asset(name="25 APR 2025 - Comfrey - P2R3.15-21", inventory_count=3),
            make_plant_asset(name="25 APR 2025 - Tomato (Marmande) - P2R3.15-21", inventory_count=5),
        ]
        logs = [
            make_log(name="Observation P2R3.15-21", log_type="observation",
                     timestamp=str(int((datetime.now(tz=AEST) - timedelta(days=5)).timestamp()))),
        ]
        plant_types = [
            _build_plant_type_with_metadata("Ice Cream Bean", "emergent", "pioneer"),
            _build_plant_type_with_metadata("Pigeon Pea", "high", "pioneer"),
            _build_plant_type_with_metadata("Comfrey", "low", "secondary"),
            _build_plant_type_with_metadata("Tomato (Marmande)", "medium", "pioneer"),
        ]

        _setup_farm_context_mocks(monkeypatch, mock_farmos_client, plants, logs, plant_types)

        result = json.loads(server.farm_context(section="P2R3.15-21"))

        # All five layers present
        assert "ontology" in result
        assert "facts" in result
        assert "interpretation" in result
        assert "context" in result
        assert "gaps" in result

        # Query metadata
        assert result["query"]["type"] == "section"
        assert result["query"]["id"] == "P2R3.15-21"

        # Ontology
        assert result["ontology"]["entity_type"] == "paddock_section"

        # Facts
        assert result["facts"]["total_plants"] == 4
        assert result["facts"]["total_species"] == 4

        # Interpretation — strata coverage should be good (4/4 strata)
        strata = result["interpretation"]["strata_coverage"]
        assert strata["score"] == 1.0
        assert strata["status"] == "good"

        # Activity recency — 5 days ago, should be active
        recency = result["interpretation"]["activity_recency"]
        assert recency["status"] == "active"

    def test_section_detects_poor_strata(self, monkeypatch, mock_farmos_client):
        """Section with only 1 stratum → poor strata coverage."""
        plants = [
            make_plant_asset(name="25 APR 2025 - Pigeon Pea - P2R3.15-21", inventory_count=4),
        ]
        plant_types = [_build_plant_type_with_metadata("Pigeon Pea", "high", "pioneer")]

        _setup_farm_context_mocks(monkeypatch, mock_farmos_client, plants, [], plant_types)

        result = json.loads(server.farm_context(section="P2R3.15-21"))

        assert result["interpretation"]["strata_coverage"]["status"] == "poor"
        assert any("strata coverage" in g.lower() for g in result["gaps"])

    def test_section_detects_neglected(self, monkeypatch, mock_farmos_client):
        """Section with no logs → neglected."""
        plants = [make_plant_asset(name="25 APR 2025 - Pigeon Pea - P2R3.15-21", inventory_count=2)]
        plant_types = [_build_plant_type_with_metadata("Pigeon Pea", "high", "pioneer")]

        _setup_farm_context_mocks(monkeypatch, mock_farmos_client, plants, [], plant_types)

        result = json.loads(server.farm_context(section="P2R3.15-21"))

        assert result["interpretation"]["activity_recency"]["status"] == "neglected"
        assert any("visited" in g.lower() for g in result["gaps"])

    def test_section_nursery_zone(self, monkeypatch, mock_farmos_client):
        """Nursery zone → entity_type is nursery_zone, no strata expectation."""
        plants = [make_plant_asset(name="01 MAR 2026 - Comfrey - NURS.SH1-2", inventory_count=5)]
        plant_types = [_build_plant_type_with_metadata("Comfrey", "low", "secondary")]

        _setup_farm_context_mocks(monkeypatch, mock_farmos_client, plants, [], plant_types)

        result = json.loads(server.farm_context(section="NURS.SH1-2"))

        assert result["ontology"]["entity_type"] == "nursery_zone"


class TestFarmContextSubject:
    """Tests for farm_context(subject=...) mode."""

    def test_subject_returns_distribution(self, monkeypatch, mock_farmos_client):
        """Species query returns plants grouped by section."""
        plants = [
            make_plant_asset(name="25 APR 2025 - Pigeon Pea - P2R2.0-3", inventory_count=4),
            make_plant_asset(name="25 APR 2025 - Pigeon Pea - P2R3.15-21", inventory_count=2),
        ]
        plant_types = [_build_plant_type_with_metadata("Pigeon Pea", "high", "pioneer")]

        _setup_farm_context_mocks(monkeypatch, mock_farmos_client, plants, [], plant_types)

        result = json.loads(server.farm_context(subject="Pigeon Pea"))

        assert result["query"]["type"] == "species"
        assert result["facts"]["total_plants"] == 2
        assert result["facts"]["distribution"] == 2
        assert result["interpretation"]["strata"] == "High"
        assert result["interpretation"]["succession"] == "Pioneer"

    def test_subject_detects_kb_gap(self, monkeypatch, mock_farmos_client):
        """Species with no KB entries → gap detected."""
        plants = [make_plant_asset(name="25 APR 2025 - Pigeon Pea - P2R2.0-3", inventory_count=4)]
        plant_types = [_build_plant_type_with_metadata("Pigeon Pea", "high", "pioneer")]

        _setup_farm_context_mocks(monkeypatch, mock_farmos_client, plants, [], plant_types, kb_entries=[])

        result = json.loads(server.farm_context(subject="Pigeon Pea"))

        assert any("No Knowledge Base" in g for g in result["gaps"])

    def test_subject_unknown_species(self, monkeypatch, mock_farmos_client):
        """Unknown species → gap about missing taxonomy."""
        _setup_farm_context_mocks(monkeypatch, mock_farmos_client, [], [], [])

        result = json.loads(server.farm_context(subject="Unicorn Tree"))

        assert any("not found" in g for g in result["gaps"])


class TestFarmContextTopic:
    """Tests for farm_context(topic=...) mode."""

    def test_topic_nursery(self, monkeypatch, mock_farmos_client):
        """Nursery topic returns sections and transplant readiness."""
        plants = [
            make_plant_asset(name="01 JAN 2026 - Comfrey - NURS.SH1-2", inventory_count=3),
        ]
        plant_types = [_build_plant_type_with_metadata("Comfrey", "low", "secondary")]

        _setup_farm_context_mocks(monkeypatch, mock_farmos_client, plants, [], plant_types)

        result = json.loads(server.farm_context(topic="nursery"))

        assert result["query"]["type"] == "topic"
        assert result["query"]["name"] == "nursery"
        assert result["ontology"]["section_prefix"] == "NURS."

    def test_topic_no_kb_entries(self, monkeypatch, mock_farmos_client):
        """Topic with no KB entries → gap detected."""
        _setup_farm_context_mocks(monkeypatch, mock_farmos_client, [], [], [], kb_entries=[])

        result = json.loads(server.farm_context(topic="compost"))

        assert any("No Knowledge Base" in g for g in result["gaps"])


class TestFarmContextLoggingGaps:
    """Tests for farm_context team memory cross-reference."""

    def test_detects_missing_farmos_log(self, monkeypatch, mock_farmos_client):
        """Session claims plant created but no farmOS log exists → integrity gap."""
        plants = [make_plant_asset(name="25 APR 2025 - Pigeon Pea - P2R4.6-14", inventory_count=14)]
        plant_types = [_build_plant_type_with_metadata("Pigeon Pea", "high", "pioneer")]

        # James's session claims lavender was planted but no log in farmOS
        memory_sessions = [{
            "summary_id": "89",
            "user": "James",
            "timestamp": "2026-03-25T23:04:00Z",
            "farmos_changes": '[{"type":"create_plant","species":"Lavender","section":"P2R4.6-14","count":5,"details":"Lavender x5 — P2R4.6-14"}]',
        }]

        _setup_farm_context_mocks(monkeypatch, mock_farmos_client, plants, [], plant_types,
                                  memory_sessions=memory_sessions)

        result = json.loads(server.farm_context(section="P2R4.6-14"))

        # Should have a logging gap
        assert len(result["context"]["logging_gaps"]) >= 1
        assert any("James" in g["user"] for g in result["context"]["logging_gaps"])
        assert any("INTEGRITY" in g for g in result["gaps"])

        # Data integrity gate should require confirmation
        assert result["data_integrity"]["requires_confirmation"] is True
        assert len(result["data_integrity"]["discrepancies"]) >= 1
        assert "Lavender" in result["data_integrity"]["discrepancies"][0]["claimed"]

    def test_no_gap_when_log_exists(self, monkeypatch, mock_farmos_client):
        """Session claims activity and farmOS log matches → no integrity gap."""
        plants = [make_plant_asset(name="25 APR 2025 - Pigeon Pea - P2R3.50-62", inventory_count=8)]
        logs = [make_log(name="Seeding — P2R3.50-62", log_type="activity",
                         log_uuid="0ee1ea15-a7e7-482c-8872-6745588a75be")]
        plant_types = [_build_plant_type_with_metadata("Pigeon Pea", "high", "pioneer")]

        memory_sessions = [{
            "summary_id": "82",
            "user": "James",
            "timestamp": "2026-03-21T07:08:00Z",
            "farmos_changes": '[{"type":"activity","id":"0ee1ea15","details":"Seeding — P2R3.50-62"}]',
        }]

        _setup_farm_context_mocks(monkeypatch, mock_farmos_client, plants, logs, plant_types,
                                  memory_sessions=memory_sessions)

        result = json.loads(server.farm_context(section="P2R3.50-62"))

        assert len(result["context"]["logging_gaps"]) == 0
        assert not any("INTEGRITY" in g for g in result["gaps"])

        # Data integrity gate should NOT require confirmation
        assert result["data_integrity"]["requires_confirmation"] is False


class TestFarmContextValidation:
    """Tests for farm_context input validation."""

    def test_no_params_returns_error(self):
        """Calling with no params → error."""
        result = json.loads(server.farm_context())
        assert "error" in result


# Need datetime imports for timestamps in tests
from datetime import datetime, timedelta, timezone
AEST = timezone(timedelta(hours=10))


class TestSystemHealthTeamDimensionUnwrap:
    """Regression tests for the team dimension counter bug (April 9, 2026).

    The Apps Script clients (MemoryClient.read_activity,
    KnowledgeClient.list_entries) return wrapper dicts like
    {success, summaries: [...], count} and {success, entries: [...], total}.
    A prior implementation checked ``isinstance(x, list)`` and silently
    short-circuited to 0, making ``system_health`` report Team stage as
    dormant forever. These tests lock in the unwrap behaviour.
    """

    def _setup(self, monkeypatch, mock_farmos_client, *, memory_resp, kb_resp):
        from unittest.mock import MagicMock

        mock_farmos_client.get_plant_assets.return_value = []
        mock_farmos_client.get_logs.return_value = []
        mock_farmos_client.get_all_plant_types_cached.return_value = []
        mock_farmos_client.get_section_assets.return_value = []
        monkeypatch.setattr(server, "get_client", lambda: mock_farmos_client)

        mock_mem = MagicMock()
        mock_mem.is_connected = True
        mock_mem.read_activity.return_value = memory_resp
        monkeypatch.setattr(server, "get_memory_client", lambda: mock_mem)

        mock_kb = MagicMock()
        mock_kb.list_entries.return_value = kb_resp
        monkeypatch.setattr(server, "get_knowledge_client", lambda: mock_kb)

        # Plant types and observe clients may be called by other dimensions;
        # keep them benign.
        mock_pt = MagicMock()
        mock_pt.reconcile.return_value = {"mismatch_count": 0}
        monkeypatch.setattr(server, "get_plant_types_client", lambda: mock_pt)

        mock_obs = MagicMock()
        mock_obs.list_observations.return_value = []
        monkeypatch.setattr(server, "get_observe_client", lambda: mock_obs)

        from semantics import clear_caches
        clear_caches()

    def test_apps_script_wrapper_dicts_are_unwrapped(self, monkeypatch, mock_farmos_client):
        """Wrapped dict responses must be counted, not treated as zero."""
        memory_resp = {
            "success": True,
            "summaries": [
                {"user": "Agnes", "summary": "..."},
                {"user": "James", "summary": "..."},
                {"user": "James", "summary": "..."},
            ],
            "count": 3,
        }
        kb_resp = {
            "success": True,
            "entries": [{"entry_id": str(i)} for i in range(18)],
            "count": 18,
            "total": 18,
        }
        self._setup(monkeypatch, mock_farmos_client, memory_resp=memory_resp, kb_resp=kb_resp)

        result = json.loads(server.system_health())

        team = result["dimensions"]["team"]
        assert team["metrics"]["active_users_weekly"]["value"] == 2, (
            "distinct_users should count unique 'user' fields from summaries list"
        )
        assert team["metrics"]["team_memory_velocity"]["value"] == 3, (
            "memory_velocity should be the length of the summaries list"
        )
        assert team["metrics"]["kb_entry_count"]["value"] == 18, (
            "kb_entry_count should unwrap the 'total' or 'entries' field"
        )

    def test_bare_list_responses_still_work(self, monkeypatch, mock_farmos_client):
        """Fallback: if a client ever returns a bare list, it must still count."""
        memory_resp = [
            {"user": "Agnes"},
            {"user": "James"},
        ]
        kb_resp = [{"entry_id": "1"}, {"entry_id": "2"}, {"entry_id": "3"}]
        self._setup(monkeypatch, mock_farmos_client, memory_resp=memory_resp, kb_resp=kb_resp)

        result = json.loads(server.system_health())

        team = result["dimensions"]["team"]
        assert team["metrics"]["active_users_weekly"]["value"] == 2
        assert team["metrics"]["team_memory_velocity"]["value"] == 2
        assert team["metrics"]["kb_entry_count"]["value"] == 3

    def test_empty_wrappers_report_zero(self, monkeypatch, mock_farmos_client):
        """Empty lists inside wrappers should still resolve cleanly to zero."""
        self._setup(
            monkeypatch,
            mock_farmos_client,
            memory_resp={"success": True, "summaries": [], "count": 0},
            kb_resp={"success": True, "entries": [], "count": 0, "total": 0},
        )

        result = json.loads(server.system_health())
        team = result["dimensions"]["team"]
        assert team["metrics"]["active_users_weekly"]["value"] == 0
        assert team["metrics"]["team_memory_velocity"]["value"] == 0
        assert team["metrics"]["kb_entry_count"]["value"] == 0
