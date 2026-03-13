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
        make_plant_asset(name="25 APR 2025 - Pigeon Pea - P2R3.14-21", inventory_count=3),
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
    assert "P2R3.14-21" in sections


# ── query_sections ────────────────────────────────────────────


def test_query_sections_groups_by_row(monkeypatch, mock_farmos_client):
    """query_sections groups section results by row prefix."""
    sections = [
        make_section_asset(name="P2R2.0-3"),
        make_section_asset(name="P2R2.3-7"),
        make_section_asset(name="P2R3.14-21"),
    ]
    # Plants for the count index
    all_plants = [
        make_plant_asset(name="25 APR 2025 - Pigeon Pea - P2R2.0-3"),
        make_plant_asset(name="25 APR 2025 - Comfrey - P2R2.0-3"),
        make_plant_asset(name="25 APR 2025 - Macadamia - P2R3.14-21"),
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
