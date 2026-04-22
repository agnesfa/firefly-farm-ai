#!/usr/bin/env python3
"""
farmOS MCP Server for Firefly Corner Farm.

Provides Claude Desktop with tools and resources to query and manage
the farm's farmOS instance (margregen.farmos.net).

Phase 1a: Local STDIO server for Agnes with full read/write access.
Phase 1b: HTTP transport + API key auth for Claire/James (future).

Usage:
    # Run via STDIO (Claude Desktop)
    python mcp-server/server.py

    # Run with MCP Inspector for testing
    fastmcp dev mcp-server/server.py
"""

import json
import subprocess
import sys
import os
from datetime import datetime
from typing import Optional

# Add parent directory to path so we can find our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastmcp import FastMCP
from interaction_stamp import build_mcp_stamp, append_stamp, build_stamp

from farmos_client import FarmOSClient
from observe_client import ObservationClient
from memory_client import MemoryClient
from plant_types_client import PlantTypesClient
from knowledge_client import KnowledgeClient
from helpers import (
    parse_date,
    format_planted_label,
    build_asset_name,
    format_timestamp,
    format_plant_asset,
    format_log,
    format_plant_type,
    format_section_from_assets,
    build_plant_type_description,
    parse_plant_type_metadata,
    AEST,
)


# ── Server setup ────────────────────────────────────────────────

mcp = FastMCP(
    "farmos",
    instructions="""You are connected to the Firefly Corner Farm management system.
This MCP server provides access to farmOS (margregen.farmos.net) — the farm's
source of truth for plant assets, field observations, and inventory tracking.

The farm practices syntropic agroforestry across 5 rows in Paddock 2,
with 33 sections containing 404 plant assets and 219 plant species.

Use the available tools to query plants, sections, logs, and plant types.
Use write tools to create observations, activities, and new plant records.
Use observation tools to review and import field observations from the Sheet.
Use memory tools to read team activity and write session summaries.
Use plant type tools to add or update species in the farmOS taxonomy.

Key concepts:
- Sections are identified like P2R3.15-21 (Paddock 2, Row 3, metres 14-21)
- Plant assets are named: "{date} - {species} - {section}"
- Strata: emergent (20m+), high (8-20m), medium (2-8m), low (0-2m)
- Succession: pioneer (0-5yr), secondary (3-15yr), climax (15+yr)
""",
)

# Global clients — connect lazily on first use
_client: Optional[FarmOSClient] = None
_observe_client: Optional[ObservationClient] = None
_memory_client: Optional[MemoryClient] = None
_plant_types_client: Optional[PlantTypesClient] = None
_knowledge_client: Optional[KnowledgeClient] = None


def get_client() -> FarmOSClient:
    """Get or create the farmOS client connection."""
    global _client
    if _client is None or not _client.is_connected:
        _client = FarmOSClient()
        _client.connect()
    return _client


def get_observe_client() -> ObservationClient:
    """Get or create the observation Sheet client connection."""
    global _observe_client
    if _observe_client is None or not _observe_client.is_connected:
        _observe_client = ObservationClient()
        _observe_client.connect()
    return _observe_client


def get_memory_client() -> MemoryClient:
    """Get or create the team memory client connection."""
    global _memory_client
    if _memory_client is None or not _memory_client.is_connected:
        _memory_client = MemoryClient()
        _memory_client.connect()
    return _memory_client


def get_plant_types_client() -> Optional[PlantTypesClient]:
    """Get or create the plant types Sheet client connection.

    Returns None if PLANT_TYPES_ENDPOINT is not configured (graceful degradation).
    """
    global _plant_types_client
    if _plant_types_client is None:
        try:
            _plant_types_client = PlantTypesClient()
            _plant_types_client.connect()
        except ValueError:
            # PLANT_TYPES_ENDPOINT not set — Sheet sync disabled
            return None
    if not _plant_types_client.is_connected:
        return None
    return _plant_types_client


def get_knowledge_client() -> Optional[KnowledgeClient]:
    """Get or create the knowledge base client connection.

    Returns None if KNOWLEDGE_ENDPOINT is not configured (graceful degradation).
    """
    global _knowledge_client
    if _knowledge_client is None:
        try:
            _knowledge_client = KnowledgeClient()
            _knowledge_client.connect()
        except ValueError:
            # KNOWLEDGE_ENDPOINT not set — knowledge tools disabled
            return None
    if not _knowledge_client.is_connected:
        return None
    return _knowledge_client


# ═══════════════════════════════════════════════════════════════
# RESOURCES — Read-only data endpoints
# ═══════════════════════════════════════════════════════════════

@mcp.resource("farm://overview")
def farm_overview() -> str:
    """Farm overview: paddock/row/section counts, asset totals, plant type count."""
    client = get_client()

    # Count sections (P2R*.start-end pattern)
    sections = client.get_section_assets()

    # Count plants
    plants = client.fetch_filtered("asset/plant", filters={"status": "active"}, max_results=50)

    # Count plant types
    plant_types = client.fetch_filtered("taxonomy_term/plant_type", max_results=50)

    # Group sections by row
    rows = {}
    for s in sections:
        name = s.get("attributes", {}).get("name", "")
        # Extract row prefix (P2R1, P2R2, etc.)
        parts = name.split(".")
        if parts:
            row = parts[0]
            if row not in rows:
                rows[row] = []
            rows[row].append(name)

    # Separate P1 and P2 sections
    p1_sections = {r: s for r, s in rows.items() if r.startswith("P1")}
    p2_sections = {r: s for r, s in rows.items() if r.startswith("P2")}

    return json.dumps({
        "farm": "Firefly Corner Farm",
        "location": "Krambach, NSW, Australia",
        "farmos_url": "https://margregen.farmos.net",
        "paddocks": 2,
        "total_rows": len(rows),
        "total_sections": len(sections),
        "paddock_1": {
            "sections": sum(len(s) for s in p1_sections.values()),
            "rows": {row: sorted(secs) for row, secs in sorted(p1_sections.items())},
        },
        "paddock_2": {
            "sections": sum(len(s) for s in p2_sections.values()),
            "rows": {row: sorted(secs) for row, secs in sorted(p2_sections.items())},
            "note": "P2 has plant assets and observation data imported",
        },
        "plant_assets": "404+",
        "plant_types": "219",
        "observation_logs": "442+",
        "note": "Use query tools for exact current counts.",
    }, indent=2)


@mcp.resource("farm://sections/{section_id}")
def section_detail(section_id: str) -> str:
    """Detailed view of a section including all plant assets."""
    client = get_client()

    # Get section land asset
    section_assets = client.fetch_by_name("asset/land", section_id)
    if not section_assets:
        return json.dumps({"error": f"Section '{section_id}' not found"})

    section = section_assets[0]

    # Get plants in this section
    plants = client.get_plant_assets(section_id=section_id)
    formatted_plants = [format_plant_asset(p) for p in plants]

    return json.dumps({
        "section": section_id,
        "uuid": section.get("id"),
        "plant_count": len(formatted_plants),
        "plants": formatted_plants,
    }, indent=2)


@mcp.resource("farm://plant-types")
def plant_types_list() -> str:
    """All plant type taxonomy terms with syntropic metadata."""
    client = get_client()
    terms = client.get_plant_type_details()
    formatted = [format_plant_type(t) for t in terms]
    # Sort by name
    formatted.sort(key=lambda t: t.get("name", ""))
    return json.dumps({
        "count": len(formatted),
        "plant_types": formatted,
    }, indent=2)


@mcp.resource("farm://plant-types/{name}")
def plant_type_detail(name: str) -> str:
    """Single plant type detail with syntropic metadata."""
    client = get_client()
    terms = client.get_plant_type_details(name=name)
    if not terms:
        return json.dumps({"error": f"Plant type '{name}' not found"})
    return json.dumps(format_plant_type(terms[0]), indent=2)


@mcp.resource("farm://recent-logs")
def recent_logs() -> str:
    """Last 20 logs across all types, newest first."""
    client = get_client()
    logs = client.get_recent_logs(count=20)
    formatted = [format_log(l) for l in logs]
    return json.dumps({
        "count": len(formatted),
        "logs": formatted,
    }, indent=2)


# ═══════════════════════════════════════════════════════════════
# TOOLS — Read tools (available to all users)
# ═══════════════════════════════════════════════════════════════

@mcp.tool
def query_plants(
    section_id: Optional[str] = None,
    species: Optional[str] = None,
    status: str = "active",
) -> str:
    """Search plant assets by section, species, or status.

    Args:
        section_id: Filter by section (e.g., "P2R3.15-21"). Optional.
        species: Filter by species name (e.g., "Pigeon Pea"). Partial match. Optional.
        status: Asset status filter. Default "active".

    Returns:
        List of matching plant assets with name, species, section, and status.
    """
    client = get_client()
    plants = client.get_plant_assets(
        section_id=section_id,
        species=species,
        status=status,
    )
    formatted = [format_plant_asset(p) for p in plants]
    return json.dumps({
        "count": len(formatted),
        "filters": {
            "section_id": section_id,
            "species": species,
            "status": status,
        },
        "plants": formatted,
    }, indent=2)


@mcp.tool
def query_sections(row: Optional[str] = None) -> str:
    """List sections with optional row filter.

    Args:
        row: Filter by row prefix (e.g., "P2R1", "P2R3"). Optional.

    Returns:
        List of section IDs grouped by row with plant counts.
    """
    client = get_client()

    # Use the enhanced get_all_locations for broader queries
    if row and row.upper().startswith("NURS"):
        # Nursery query — use new location method
        locations = client.get_all_locations(type_filter="nursery")
        sections_list = locations.get("nursery", [])
    elif row and row.upper().startswith("COMP"):
        # Compost query
        locations = client.get_all_locations(type_filter="compost")
        sections_list = locations.get("compost", [])
    elif row is None:
        # No filter — return paddock sections (backward compatible)
        sections = client.get_section_assets()
        sections_list = [
            {"name": s.get("attributes", {}).get("name", ""), "uuid": s.get("id")}
            for s in sections
        ]
    else:
        # Paddock row filter (original behavior)
        sections = client.get_section_assets(row_filter=row)
        sections_list = [
            {"name": s.get("attributes", {}).get("name", ""), "uuid": s.get("id")}
            for s in sections
        ]

    # Fetch ALL plant assets once (not per-section!)
    all_plants = client.fetch_all_paginated("asset/plant", filters={"status": "active"})

    # Build section→plant count index from plant asset names
    plant_counts = {}
    for p in all_plants:
        pname = p.get("attributes", {}).get("name", "")
        # Plant names end with " - {section_id}"
        parts = pname.rsplit(" - ", 1)
        if len(parts) == 2:
            sec = parts[1]
            plant_counts[sec] = plant_counts.get(sec, 0) + 1

    # Build results using pre-counted index
    results = []
    for s in sections_list:
        name = s.get("name", "")
        results.append({
            "section_id": name,
            "uuid": s.get("uuid"),
            "plant_count": plant_counts.get(name, 0),
        })

    # Sort by section ID
    results.sort(key=lambda x: x["section_id"])

    # Group by prefix (row for paddocks, type for nursery/compost)
    rows = {}
    for r in results:
        row_prefix = r["section_id"].split(".")[0]
        if row_prefix not in rows:
            rows[row_prefix] = []
        rows[row_prefix].append(r)

    return json.dumps({
        "total_sections": len(results),
        "filter": {"row": row},
        "rows": rows,
    }, indent=2)


@mcp.tool
def get_plant_detail(plant_name: str) -> str:
    """Get full detail of a plant asset including all associated logs.

    Args:
        plant_name: The exact plant asset name (e.g., "25 APR 2025 - Pigeon Pea - P2R2.0-3").
                    Can also be a partial name for search.

    Returns:
        Plant asset details and all associated logs.
    """
    client = get_client()

    # Try exact name match first
    assets = client.fetch_by_name("asset/plant", plant_name)
    if not assets:
        # Try partial search
        all_plants = client.get_plant_assets(species=plant_name)
        if not all_plants:
            return json.dumps({"error": f"Plant '{plant_name}' not found"})
        assets = all_plants[:5]  # Limit to 5 if multiple matches

    if len(assets) == 1:
        plant = assets[0]
        formatted = format_plant_asset(plant)

        # Get logs for this plant (search by plant name in log names)
        species = formatted["species"]
        section = formatted["section"]
        logs = client.get_logs(species=species, section_id=section, max_results=20)
        formatted_logs = [format_log(l) for l in logs]

        return json.dumps({
            "plant": formatted,
            "log_count": len(formatted_logs),
            "logs": formatted_logs,
        }, indent=2)
    else:
        # Multiple matches — return summary
        formatted = [format_plant_asset(a) for a in assets]
        return json.dumps({
            "note": f"Multiple matches found for '{plant_name}'. Showing first {len(formatted)}.",
            "matches": formatted,
        }, indent=2)


@mcp.tool
def query_logs(
    log_type: Optional[str] = None,
    section_id: Optional[str] = None,
    species: Optional[str] = None,
    status: Optional[str] = None,
    max_results: int = 20,
) -> str:
    """Search logs by type, section, or species.

    Args:
        log_type: Filter by log type: observation, activity, transplanting, harvest, seeding. Optional.
        section_id: Filter by section ID in log name. Optional.
        species: Filter by species name in log name. Optional.
        status: Filter by log status: "done" or "pending". Use "pending" to find TODO tasks. Optional.
        max_results: Maximum number of results (default 20, max 50).

    Returns:
        List of matching logs with name, type, timestamp, and notes.
    """
    client = get_client()
    max_results = min(max_results, 50)
    logs = client.get_logs(
        log_type=log_type,
        section_id=section_id,
        species=species,
        status=status,
        max_results=max_results,
    )
    formatted = [format_log(l) for l in logs]
    return json.dumps({
        "count": len(formatted),
        "filters": {
            "log_type": log_type,
            "section_id": section_id,
            "species": species,
            "status": status,
        },
        "logs": formatted,
    }, indent=2)


def _get_seedbank_endpoint() -> Optional[str]:
    """Get the SeedBank Apps Script endpoint URL."""
    endpoint = os.environ.get("SEEDBANK_ENDPOINT")
    if endpoint:
        return endpoint
    # Fallback: hardcoded known endpoint (same as SEED.BANK.html)
    return "https://script.google.com/macros/s/AKfycbwm2YllQ0vi-vSz_aruKXGxVL3klbSE7F_85dS4qIlxoy3TP4DA0VkAPcI3izNgj7hMIg/exec"


def _format_seed_asset(seed: dict) -> dict:
    """Format a farmOS seed asset into a standard inventory dict."""
    attrs = seed.get("attributes", {})
    name = attrs.get("name", "")
    # Extract species from seed name: "{Species} Seeds" or "{Species} Seeds — {Source}"
    species_name = name.replace(" Seeds", "").split(" — ")[0].strip()
    # Get inventory from computed attribute
    inv = attrs.get("inventory", [])
    count = None
    if inv:
        for q in inv:
            val = q.get("value")
            if val is not None:
                try:
                    count = float(val)
                except (ValueError, TypeError):
                    pass
    return {
        "name": name,
        "species": species_name,
        "section": "Seed Bank",
        "inventory_count": count,
        "status": attrs.get("status", "active"),
        "asset_type": "seed",
        "notes": (attrs.get("notes", {}) or {}).get("value", ""),
    }


@mcp.tool
def get_inventory(section_id: Optional[str] = None, species: Optional[str] = None, section_prefix: Optional[str] = None) -> str:
    """Get current inventory (plant counts) for a section or specific species.

    Args:
        section_id: Section to check inventory for (e.g., "P2R3.15-21"). Optional.
        species: Species to check across all sections (e.g., "Pigeon Pea"). Optional.
        section_prefix: Prefix to query all matching sections in one call (e.g., "NURS",
            "P2R3", "COMP"). Fetches inventory for every section matching the prefix.
            Mutually exclusive with section_id.
        At least one of section_id, species, or section_prefix should be provided.

    Returns:
        Plant inventory with current counts.
    """
    client = get_client()

    if not section_id and not species and not section_prefix:
        return json.dumps({"error": "Please provide section_id, species, section_prefix (or a combination)"})

    # --- section_prefix mode: resolve prefix to section list, aggregate ---
    if section_prefix:
        prefix_upper = section_prefix.upper()
        if prefix_upper.startswith("NURS"):
            locations = client.get_all_locations(type_filter="nursery")
            sections_list = [s["name"] for s in locations.get("nursery", [])]
        elif prefix_upper.startswith("COMP"):
            locations = client.get_all_locations(type_filter="compost")
            sections_list = [s["name"] for s in locations.get("compost", [])]
        else:
            # Paddock row prefix (e.g., "P2R3")
            sections = client.get_section_assets(row_filter=section_prefix)
            sections_list = [
                s.get("attributes", {}).get("name", "") for s in sections
            ]

        if not sections_list:
            return json.dumps({"error": f"No sections found matching prefix '{section_prefix}'"})

        # Fetch plants AND seeds for each section and aggregate
        all_formatted = []
        for sec_id in sorted(sections_list):
            plants = client.get_plant_assets(section_id=sec_id, species=species)
            all_formatted.extend([format_plant_asset(p) for p in plants])
            # Also fetch seed assets (different API: asset/seed)
            seeds = client.get_seed_assets(section_id=sec_id, species=species)
            all_formatted.extend([_format_seed_asset(s) for s in seeds])

        formatted = all_formatted
        query_info = {"section_prefix": section_prefix}
        if species:
            query_info["species"] = species
    else:
        # --- original single-section / species mode ---
        plants = client.get_plant_assets(section_id=section_id, species=species)
        formatted = [format_plant_asset(p) for p in plants]
        # Also fetch seed assets
        seeds = client.get_seed_assets(section_id=section_id, species=species)
        formatted.extend([_format_seed_asset(s) for s in seeds])
        query_info = {"section_id": section_id, "species": species}

    # Build inventory summary with actual counts
    inventory_items = []
    total_plant_count = 0
    unknown_count = 0
    for p in formatted:
        count = p.get("inventory_count")
        item = {
            "name": p["name"],
            "species": p["species"],
            "section": p["section"],
            "inventory_count": count if count is not None else "unknown",
            "status": p["status"],
        }
        if p.get("notes"):
            item["notes"] = p["notes"]
        inventory_items.append(item)

        if count is not None:
            total_plant_count += count
        else:
            unknown_count += 1

    # Group by section for section-level summaries
    section_totals = {}
    for item in inventory_items:
        sec = item["section"]
        if sec not in section_totals:
            section_totals[sec] = {"section": sec, "species_count": 0, "plant_count": 0}
        section_totals[sec]["species_count"] += 1
        if isinstance(item["inventory_count"], int):
            section_totals[sec]["plant_count"] += item["inventory_count"]

    result = {
        "query": query_info,
        "summary": {
            "total_species_entries": len(inventory_items),
            "total_plant_count": total_plant_count,
        },
        "plants": inventory_items,
    }

    if unknown_count > 0:
        result["summary"]["entries_without_count"] = unknown_count

    # Add section breakdown for multi-section results
    if len(section_totals) > 1:
        result["by_section"] = sorted(
            section_totals.values(), key=lambda s: s["section"]
        )

    return json.dumps(result, indent=2)


@mcp.tool
def get_seed_transactions(
    days: int = 30,
    species: Optional[str] = None,
    user: Optional[str] = None,
    transaction_type: Optional[str] = None,
) -> str:
    """Query seed bank transactions (withdrawals, additions, stock changes).

    Reads from the Seed Bank Google Sheet Transactions tab via Apps Script.

    Args:
        days: How many days back to search (default 30).
        species: Filter by species name (partial match, e.g., "pigeon", "winter").
        user: Filter by who made the transaction (e.g., "james").
        transaction_type: Filter by type: "take" or "add".

    Returns:
        List of transactions with date, user, seed, type, amount, notes.
    """
    import requests as req

    endpoint = _get_seedbank_endpoint()
    if not endpoint:
        return json.dumps({"error": "SEEDBANK_ENDPOINT not configured"})

    params = {"action": "transactions", "days": str(days)}
    if species:
        params["species"] = species
    if user:
        params["user"] = user
    if transaction_type:
        params["type"] = transaction_type

    try:
        resp = req.get(endpoint, params=params, timeout=30, allow_redirects=True)
        # Apps Script returns JSON after redirect
        data = resp.json()
        if not data.get("success"):
            return json.dumps({"error": data.get("error", "Unknown error from SeedBank endpoint")})
        return json.dumps(data, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to query seed transactions: {e}"})


@mcp.tool
def create_seed(
    species: str,
    quantity_grams: Optional[float] = None,
    stock_level: Optional[str] = None,
    source: Optional[str] = None,
    source_type: str = "commercial",
    notes: str = "",
    date: Optional[str] = None,
) -> str:
    """Create or restock a seed asset in the seed bank.

    Creates a farmOS seed asset, sets initial inventory, and records location
    in NURS.FRDG (seed bank fridge). If the seed asset already exists, adds
    stock via an inventory increment log.

    Three acquisition pathways:
    - commercial: purchased from a nursery or supplier
    - harvest: saved from farm harvest
    - exchange: received from another farm (non-commercial)

    Args:
        species: Plant species farmos_name (must match plant_type taxonomy).
        quantity_grams: Initial weight in grams (for bulk seeds).
        stock_level: For sachet seeds: "full", "half", or "empty".
        source: Where seeds came from (e.g., "Down Under Ag", "Farm harvest P2R3").
        source_type: One of "commercial", "harvest", "exchange". Default "commercial".
        notes: Free text (composition, invoice refs, harvest context).
        date: Acquisition date in ISO format. Defaults to today.

    Returns:
        Created/restocked seed asset details.
    """
    from farmos_client import GRAMS_UNIT_UUID, STOCK_LEVEL_UNIT_UUID

    NURS_FRDG_UUID = "429fcdd3-8be6-436a-b439-49186f56b3c7"

    if not quantity_grams and not stock_level:
        return json.dumps({"error": "Provide either quantity_grams or stock_level."})

    client = get_client()

    # Validate species exists
    pt_results = client.fetch_by_name("taxonomy_term/plant_type", species)
    if not pt_results:
        return json.dumps({"error": f"Plant type '{species}' not found in farmOS taxonomy."})
    pt_uuid = pt_results[0]["id"]

    seed_name = f"{species} Seeds"
    date_str = date or datetime.now().strftime("%Y-%m-%d")
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    timestamp = int(dt.timestamp())

    # Build notes with source metadata
    note_parts = []
    if source:
        note_parts.append(f"Source: {source} ({source_type})")
    if notes:
        note_parts.append(notes)
    full_notes = ". ".join(note_parts)

    # Build interaction stamp
    stamp = build_mcp_stamp(
        action="created", target="seed",
        related_entities=[species],
    )
    full_notes = append_stamp(full_notes, stamp)

    # Check if seed asset already exists
    existing = client.fetch_by_name("asset/seed", seed_name)
    if existing:
        seed_id = existing[0]["id"]
        status = "restocked"
    else:
        seed_id = client.create_seed_asset(seed_name, pt_uuid, full_notes)
        if not seed_id:
            return json.dumps({"error": "Failed to create seed asset in farmOS."})
        status = "created"

    # Create inventory quantity
    qty_id = None
    if quantity_grams:
        adjustment = "increment" if existing else "reset"
        qty_id = client.create_seed_quantity(seed_id, quantity_grams, "grams", adjustment)
    elif stock_level:
        level_map = {"full": 1, "half": 0.5, "empty": 0}
        value = level_map.get(stock_level.lower(), 1)
        qty_id = client.create_seed_quantity(seed_id, value, "stock_level", "reset")

    # Create observation log (movement to NURS.FRDG)
    qty_label = f"{quantity_grams}g" if quantity_grams else (stock_level or "")
    log_name = f"Seedbank {'restock' if existing else 'addition'} — {seed_name}"
    if qty_label:
        log_name += f" — {qty_label}"
    log_id = client.create_seed_observation_log(seed_id, qty_id, timestamp, log_name, full_notes)

    result = {
        "status": status,
        "seed": {"id": seed_id, "name": seed_name, "species": species},
        "inventory": (
            {"quantity_grams": quantity_grams, "adjustment": "increment" if existing else "reset"}
            if quantity_grams
            else {"stock_level": stock_level}
        ),
        "source": source,
        "source_type": source_type,
        "observation_log": {"id": log_id, "name": log_name},
    }
    return json.dumps(result, indent=2)


@mcp.tool
def sync_seed_transactions(days: int = 7, dry_run: bool = False) -> str:
    """Sync seed bank transactions from Google Sheet to farmOS seed assets.

    Fetches recent transactions from the SeedBank.gs Transactions tab,
    finds the corresponding farmOS seed asset for each, and creates an
    observation log with quantity to update the farmOS inventory.

    This closes the loop: QR page → Sheet → farmOS.

    Args:
        days: How many days of transactions to sync (default 7).
        dry_run: If true, show what would be synced without making changes.

    Returns:
        Summary of synced/skipped/failed transactions.
    """
    import requests as req
    from farmos_client import GRAMS_UNIT_UUID, STOCK_LEVEL_UNIT_UUID

    endpoint = _get_seedbank_endpoint()
    if not endpoint:
        return json.dumps({"error": "SEEDBANK_ENDPOINT not configured"})

    # Step 1: Fetch transactions from Sheet
    try:
        resp = req.get(endpoint, params={"action": "transactions", "days": str(days)},
                       timeout=30, allow_redirects=True)
        data = resp.json()
        if not data.get("success"):
            return json.dumps({"error": data.get("error", "Failed to fetch transactions")})
        transactions = data.get("transactions", [])
    except Exception as e:
        return json.dumps({"error": f"Failed to fetch transactions: {e}"})

    if not transactions:
        return json.dumps({"message": f"No transactions in the last {days} days", "synced": 0})

    client = get_client()
    results = {"synced": [], "skipped": [], "failed": []}

    for txn in transactions:
        seed_species = txn.get("seed", "")
        txn_type = txn.get("type", "")
        amount = txn.get("amount", "")
        txn_user = txn.get("user", "")
        txn_date = txn.get("date", "")
        txn_notes = txn.get("notes", "")

        if not seed_species:
            results["skipped"].append({"reason": "No seed name", "txn": txn})
            continue

        # Step 2: Find the farmOS seed asset
        # Seed assets are named "{Species} Seeds" or with source suffix
        seed_name = f"{seed_species} Seeds"
        try:
            seed_assets = client.fetch_by_name("asset/seed", seed_name)
            if not seed_assets:
                # Try partial match
                seed_assets = client.get_seed_assets(species=seed_species)
            if not seed_assets:
                results["failed"].append({
                    "seed": seed_species,
                    "reason": f"Seed asset not found in farmOS for '{seed_species}'",
                    "txn_date": txn_date,
                })
                continue

            seed_asset = seed_assets[0]
            seed_id = seed_asset.get("id", "")

            # Step 3: Determine new inventory value
            # We need to get current farmOS inventory, then apply the transaction
            current_inv = seed_asset.get("attributes", {}).get("inventory", [])
            current_value = 0
            for q in current_inv:
                v = q.get("value")
                if v is not None:
                    try:
                        current_value = float(v)
                    except (ValueError, TypeError):
                        pass

            try:
                txn_amount = float(amount) if amount else 0
            except (ValueError, TypeError):
                txn_amount = 0

            if txn_type == "take":
                new_value = max(0, current_value - abs(txn_amount))
            elif txn_type == "add":
                new_value = current_value + abs(txn_amount)
            else:
                # status_change — use new_stock from txn
                new_stock = txn.get("new_stock", "")
                try:
                    new_value = float(new_stock) if new_stock else current_value
                except (ValueError, TypeError):
                    new_value = current_value

            # Determine unit type based on amount size
            # Stock levels are 0, 0.5, 1 — anything > 1 is grams
            unit_type = "stock_level" if new_value <= 1 and txn_type == "status_change" else "grams"

            if dry_run:
                results["synced"].append({
                    "seed": seed_species,
                    "txn_type": txn_type,
                    "amount": txn_amount,
                    "current_farmos": current_value,
                    "new_value": new_value,
                    "unit_type": unit_type,
                    "txn_date": txn_date,
                    "dry_run": True,
                })
                continue

            # Step 4: Create quantity + observation log in farmOS
            from datetime import datetime
            from helpers import AEST
            try:
                ts_dt = datetime.strptime(txn_date, "%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                ts_dt = datetime.now(tz=AEST)
            timestamp = int(ts_dt.replace(tzinfo=AEST).timestamp()) if ts_dt.tzinfo is None else int(ts_dt.timestamp())

            qty_id = client.create_seed_quantity(seed_id, new_value, unit_type, "reset")
            log_name = f"Seed {txn_type} — {seed_species} — {txn_date}"

            # Check idempotency — don't create duplicate logs
            existing = client.log_exists(log_name, "observation")
            if existing:
                results["skipped"].append({
                    "seed": seed_species,
                    "reason": "Log already exists (idempotent skip)",
                    "log_name": log_name,
                })
                continue

            notes = f"{txn_type.title()} {txn_amount}{'g' if unit_type == 'grams' else ''} by {txn_user}. {txn_notes}".strip()
            log_id = client.create_seed_observation_log(seed_id, qty_id, timestamp, log_name, notes)

            results["synced"].append({
                "seed": seed_species,
                "txn_type": txn_type,
                "amount": txn_amount,
                "new_farmos_value": new_value,
                "log_id": log_id,
                "log_name": log_name,
                "txn_date": txn_date,
            })

        except Exception as e:
            results["failed"].append({
                "seed": seed_species,
                "reason": str(e),
                "txn_date": txn_date,
            })

    summary = {
        "days": days,
        "dry_run": dry_run,
        "total_transactions": len(transactions),
        "synced": len(results["synced"]),
        "skipped": len(results["skipped"]),
        "failed": len(results["failed"]),
        "details": results,
    }
    return json.dumps(summary, indent=2, default=str)


@mcp.tool
def search_plant_types(query: str) -> str:
    """Search plant types by name (partial match).

    Args:
        query: Search term (e.g., "Pigeon", "Tomato", "Macadamia").

    Returns:
        Matching plant types with syntropic metadata.
    """
    client = get_client()
    all_types = client.get_plant_type_details()

    # Filter by partial name match (case-insensitive)
    query_lower = query.lower()
    matches = [
        format_plant_type(t) for t in all_types
        if query_lower in t.get("attributes", {}).get("name", "").lower()
    ]

    return json.dumps({
        "query": query,
        "count": len(matches),
        "plant_types": matches,
    }, indent=2)


@mcp.tool
def get_all_plant_types() -> str:
    """Get ALL plant types with full syntropic metadata in a single call.

    Returns the complete taxonomy (220+ species) with strata, succession stage,
    lifecycle, lifespan, botanical name, crop family, plant functions, and source.

    USE THIS instead of calling search_plant_types multiple times when you need
    data for many species (e.g., building inventory sheets, comparing strata across
    a row). One call replaces 40+ individual lookups.

    Results are cached for 5 minutes — fast on repeated calls within a session.

    Returns:
        All plant types with full metadata, sorted alphabetically.
    """
    client = get_client()
    all_types = client.get_all_plant_types_cached()

    formatted = sorted(
        [format_plant_type(t) for t in all_types],
        key=lambda x: x.get("name", "").lower(),
    )

    return json.dumps({
        "count": len(formatted),
        "plant_types": formatted,
    }, indent=2)


# ═══════════════════════════════════════════════════════════════
# TOOLS — Write tools (Agnes only in Phase 1a)
# ═══════════════════════════════════════════════════════════════

@mcp.tool
def create_observation(
    plant_name: str,
    count: int,
    notes: str = "",
    date: Optional[str] = None,
    status: str = "done",
    submission_id: Optional[str] = None,
) -> str:
    """Create an observation log with inventory count for a plant asset.

    This updates the plant's inventory count in farmOS and records the observation.

    Args:
        plant_name: Exact plant asset name (e.g., "25 APR 2025 - Pigeon Pea - P2R2.0-3").
        count: New inventory count (number of living plants).
        notes: Observation notes (e.g., "2 lost to frost, 3 healthy"). Optional.
        date: Observation date in ISO format (e.g., "2026-03-09"). Defaults to today.
        status: Log status — "done" (completed observation) or "pending"
            (action needed / TODO). Default "done". Set to "pending" when
            the classifier (ADR 0008 I11) detects a TODO intent.
        submission_id: Optional submission UUID. When provided, enables
            ADR 0007 Fix 5 submission-aware dedup: if a log with the same
            name already exists, check the existing log's notes for the
            same `submission=<id>` marker. Same id = retry, skip. Different
            id = legitimate distinct observation, proceed (farmOS allows
            same-name logs keyed by UUID). Bug discovered 2026-04-22:
            2334a179 Okra 13->15 silently dropped because 23603752 inventory
            had already written a log with the same name at count 13.

    Returns:
        Created log details or error message.
    """
    client = get_client()

    # Find the plant asset
    assets = client.fetch_by_name("asset/plant", plant_name)
    if not assets:
        return json.dumps({"error": f"Plant asset '{plant_name}' not found in farmOS"})

    plant = assets[0]
    plant_id = plant["id"]
    formatted = format_plant_asset(plant)

    # Get section UUID
    section_id = formatted["section"]
    section_uuid = client.get_section_uuid(section_id)
    if not section_uuid:
        return json.dumps({"error": f"Section '{section_id}' not found in farmOS"})

    # Parse date
    timestamp = parse_date(date) if date else parse_date(None)

    # Build log name — include date so future inventory updates aren't blocked.
    species = formatted["species"]
    obs_date = datetime.fromtimestamp(timestamp, tz=AEST).strftime("%Y-%m-%d")
    log_name = f"Observation {section_id} — {species} — {obs_date}"

    # ADR 0007 Fix 5 (minimal): if a log with this name exists, check
    # whether the existing log's notes carry the same submission_id.
    # Same submission → retry, skip idempotently. Different submission →
    # distinct observation, proceed (farmOS allows same-name logs).
    existing = client.log_exists(log_name, "observation")
    same_name_prior_log = None
    if existing and submission_id:
        try:
            existing_log_resp = client.session.get(
                f"{client.hostname}/api/log/observation/{existing}", timeout=15,
            )
            existing_log_resp.raise_for_status()
            existing_notes = (
                (existing_log_resp.json().get("data") or {}).get("attributes", {}).get("notes", {}) or {}
            ).get("value", "")
            if f"submission={submission_id}" not in existing_notes:
                # Different submission with colliding name — tier-2 signal.
                same_name_prior_log = existing
                existing = None  # fall through to create
        except Exception:
            # If we can't verify, err on side of creating (risk of
            # duplicate beats risk of silent drop).
            same_name_prior_log = existing
            existing = None
    if existing:
        return json.dumps({
            "status": "skipped",
            "message": f"Observation log '{log_name}' already exists",
            "existing_log_id": existing,
        })

    # Build interaction stamp — passes source_submission so future
    # Fix-5 duplicate checks can match by submission_id in notes.
    stamp = build_mcp_stamp(
        action="created", target="observation",
        related_entities=[species, section_id],
        source_submission=submission_id,
    )
    stamped_notes = append_stamp(notes, stamp)

    # Create quantity (inventory count)
    qty_id = client.create_quantity(plant_id, count, adjustment="reset")

    # Create observation log
    log_id = client.create_observation_log(
        plant_id=plant_id,
        section_uuid=section_uuid,
        quantity_id=qty_id,
        timestamp=timestamp,
        name=log_name,
        notes=stamped_notes,
        status=status,
    )

    result = {
        "status": "created",
        "log_id": log_id,
        "log_name": log_name,
        "plant": plant_name,
        "count": count,
        "notes": notes,
        "log_status": status,
        "timestamp": format_timestamp(timestamp),
    }
    if same_name_prior_log:
        # Tier-2 signal per ADR 0007 Fix 5 (minimal form, without the
        # full content_hash + operator confirm flow).
        result["same_name_prior_log"] = same_name_prior_log
    return json.dumps(result, indent=2)


@mcp.tool
def create_activity(
    section_id: str,
    activity_type: str,
    notes: str,
    date: Optional[str] = None,
    status: str = "done",
) -> str:
    """Log a field activity (watering, weeding, mulching, etc.) for a section.

    Args:
        section_id: Section where the activity happened (e.g., "P2R3.15-21").
        activity_type: Type of activity (e.g., "watering", "weeding", "mulching", "pruning").
        notes: Description of the activity.
        date: Activity date in ISO format. Defaults to today.
        status: Log status — "done" (completed activity) or "pending" (action needed/TODO).

    Returns:
        Created log details or error message.
    """
    client = get_client()

    section_uuid = client.get_section_uuid(section_id)
    if not section_uuid:
        return json.dumps({"error": f"Section '{section_id}' not found in farmOS"})

    location_type = client.get_section_type(section_id)
    timestamp = parse_date(date) if date else parse_date(None)
    log_name = f"{activity_type.title()} — {section_id}"

    # Build interaction stamp
    stamp = build_mcp_stamp(
        action="created", target="activity",
        related_entities=[section_id],
    )
    stamped_notes = append_stamp(notes, stamp)

    log_id = client.create_activity_log(
        section_uuid=section_uuid,
        timestamp=timestamp,
        name=log_name,
        notes=stamped_notes,
        location_type=location_type,
        status=status,
    )

    return json.dumps({
        "status": "created",
        "log_id": log_id,
        "log_name": log_name,
        "section": section_id,
        "activity_type": activity_type,
        "notes": notes,
        "log_status": status,
        "timestamp": format_timestamp(timestamp),
    }, indent=2)


@mcp.tool
def complete_task(
    log_name: str,
    notes: Optional[str] = None,
) -> str:
    """Mark a pending activity log as done (complete a TODO task).

    Use query_logs(log_type="activity", status="pending") to find pending tasks first.

    Args:
        log_name: The exact log name to mark as done (from query_logs results).
        notes: Optional completion notes (e.g., "Done — separated 12 seedlings into pots").

    Returns:
        Confirmation or error message.
    """
    client = get_client()

    # Find the log by name
    log_id = client.log_exists(log_name, log_type="activity")
    if not log_id:
        return json.dumps({"error": f"Activity log '{log_name}' not found in farmOS"})

    # Build interaction stamp and patch notes alongside status
    stamp = build_mcp_stamp(action="updated", target="activity")
    completion_text = notes or ""
    stamped_notes = append_stamp(completion_text, stamp)

    # PATCH both status and notes in one call
    payload = {
        "data": {
            "type": "log--activity",
            "id": log_id,
            "attributes": {
                "status": "done",
                "notes": {"value": stamped_notes, "format": "default"},
            },
        }
    }
    resp = client.session.patch(
        f"{client.hostname}/api/log/activity/{log_id}",
        json=payload,
    )
    if resp.status_code not in (200, 201):
        return json.dumps({"error": f"Failed to update status for '{log_name}'"})

    result = {
        "status": "completed",
        "log_id": log_id,
        "log_name": log_name,
        "new_status": "done",
    }
    if notes:
        result["completion_notes"] = notes

    return json.dumps(result, indent=2)


@mcp.tool
def update_inventory(
    plant_name: str,
    new_count: int,
    notes: str = "",
) -> str:
    """Reset the inventory count for a plant asset.

    Creates a new observation log with the updated count.

    Args:
        plant_name: Exact plant asset name (e.g., "25 APR 2025 - Pigeon Pea - P2R2.0-3").
        new_count: New inventory count.
        notes: Reason for the update. Optional.

    Returns:
        Updated inventory details.
    """
    # Build interaction stamp (create_observation will add its own stamp too,
    # but this one marks the update_inventory intent)
    stamp = build_mcp_stamp(
        action="updated", target="observation",
        related_entities=[plant_name],
    )
    date_today = datetime.now(tz=AEST).strftime("%Y-%m-%d")
    update_notes = f"Inventory update: {notes}" if notes else "Inventory update"
    stamped_notes = append_stamp(update_notes, stamp)
    return create_observation(
        plant_name=plant_name,
        count=new_count,
        notes=stamped_notes,
        date=date_today,
    )


@mcp.tool
def create_plant(
    species: str,
    section_id: str,
    count: int,
    planted_date: Optional[str] = None,
    notes: str = "",
) -> str:
    """Create a new plant asset in a section.

    Creates the plant asset, sets its location via an observation log,
    and records the initial inventory count.

    Args:
        species: Plant species farmos_name (e.g., "Pigeon Pea", "Tomato (Marmande)").
                Must match an existing plant_type taxonomy term.
        section_id: Section to place the plant (e.g., "P2R3.15-21").
        count: Initial number of plants.
        planted_date: Planting date in ISO format (e.g., "2026-03-09"). Defaults to today.
        notes: Additional notes about the planting. Optional.

    Returns:
        Created plant and log details.
    """
    client = get_client()

    # Validate plant type exists
    plant_type_uuid = client.get_plant_type_uuid(species)
    if not plant_type_uuid:
        return json.dumps({
            "error": f"Plant type '{species}' not found in farmOS taxonomy. "
                     "Check spelling or add it first via import_plants.py.",
        })

    # Validate section exists
    section_uuid = client.get_section_uuid(section_id)
    if not section_uuid:
        return json.dumps({"error": f"Section '{section_id}' not found in farmOS"})

    # Build asset name
    date_str = planted_date or datetime.now(tz=AEST).strftime("%Y-%m-%d")
    asset_name = build_asset_name(date_str, species, section_id)

    # Check if plant already exists (idempotency)
    existing = client.plant_asset_exists(asset_name)
    if existing:
        return json.dumps({
            "status": "skipped",
            "message": f"Plant asset '{asset_name}' already exists",
            "existing_id": existing,
        })

    # Build interaction stamp
    stamp = build_mcp_stamp(
        action="created", target="plant",
        related_entities=[species, section_id],
    )
    stamped_notes = append_stamp(notes, stamp)

    # I8 — asset notes must carry only stable planting-context text.
    # Strip import-payload headers + InteractionStamp; those belong on
    # the observation log created below, not on the plant asset.
    asset_notes = _sanitise_asset_notes(notes)
    plant_id = client.create_plant_asset(asset_name, plant_type_uuid, notes=asset_notes)
    if not plant_id:
        return json.dumps({"error": "Failed to create plant asset"})

    # Create quantity (inventory count)
    qty_id = client.create_quantity(plant_id, count, adjustment="reset")

    # Create observation log (sets location via movement)
    timestamp = parse_date(date_str)
    log_name = f"Inventory {section_id} — {species}"
    log_id = client.create_observation_log(
        plant_id=plant_id,
        section_uuid=section_uuid,
        quantity_id=qty_id,
        timestamp=timestamp,
        name=log_name,
        notes=stamped_notes,
    )

    return json.dumps({
        "status": "created",
        "plant": {
            "id": plant_id,
            "name": asset_name,
            "species": species,
            "section": section_id,
            "count": count,
        },
        "observation_log": {
            "id": log_id,
            "name": log_name,
        },
        "notes": notes,
    }, indent=2)


@mcp.tool
def archive_plant(
    plant_name: str,
    reason: str = "",
) -> str:
    """Archive a plant asset in farmOS (mark as no longer active).

    Use this when a plant has died, been removed, or is no longer being tracked.
    Optionally records an activity log explaining why.

    Args:
        plant_name: Exact plant asset name (e.g., "25 APR 2025 - Pigeon Pea - P2R2.0-3")
                   or UUID.
        reason: Why the plant is being archived (e.g., "Died from frost", "Removed during
               renovation"). Optional — if provided, an activity log is created.

    Returns:
        Confirmation with archived asset details, or error message.
    """
    client = get_client()

    try:
        updated = client.archive_plant(plant_name)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    # Format the updated asset for the response
    formatted = format_plant_asset(updated)

    result = {
        "status": "archived",
        "plant": {
            "id": updated.get("id", ""),
            "name": formatted.get("name", plant_name),
            "species": formatted.get("species", ""),
            "section": formatted.get("section", ""),
        },
    }

    # Build interaction stamp
    stamp = build_mcp_stamp(
        action="archived", target="plant",
        related_entities=[plant_name],
    )

    # Optionally create an activity log with the reason
    if reason:
        section_id = formatted.get("section", "")
        section_uuid = client.get_section_uuid(section_id) if section_id else None

        if section_uuid:
            timestamp = parse_date(None)
            species = formatted.get("species", "")
            log_name = f"Archived — {species} — {section_id}"
            stamped_reason = append_stamp(reason, stamp)
            log_id = client.create_activity_log(
                section_uuid=section_uuid,
                timestamp=timestamp,
                name=log_name,
                notes=stamped_reason,
                asset_ids=[updated.get("id", "")],
            )
            result["activity_log"] = {
                "id": log_id,
                "name": log_name,
                "reason": reason,
            }

    return json.dumps(result, indent=2)


# ═══════════════════════════════════════════════════════════════
# TOOLS — Observation management (Sheet ↔ farmOS bridge)
# ═══════════════════════════════════════════════════════════════

@mcp.tool
def list_observations(
    status: Optional[str] = None,
    section: Optional[str] = None,
    observer: Optional[str] = None,
    date: Optional[str] = None,
) -> str:
    """List field observations from the observation sheet.

    Workers submit observations via QR code pages. This tool queries those
    observations from the Google Sheet, grouped by submission.

    Args:
        status: Filter by status (pending, reviewed, approved, imported, rejected). Optional.
        section: Filter by section ID (e.g., "P2R3.15-21"). Optional.
        observer: Filter by observer name. Optional.
        date: Filter by date (YYYY-MM-DD). Optional.

    Returns:
        Observations grouped by submission with summary.
    """
    obs_client = get_observe_client()
    result = obs_client.list_observations(
        status=status, section=section, observer=observer, date=date,
    )

    if not result.get("success"):
        return json.dumps({"error": result.get("error", "Failed to fetch observations")})

    observations = result.get("observations", [])

    # Group by submission_id
    submissions = {}
    for obs in observations:
        sid = obs.get("submission_id", "unknown")
        if sid not in submissions:
            submissions[sid] = {
                "submission_id": sid,
                "section_id": obs.get("section_id", ""),
                "observer": obs.get("observer", ""),
                "timestamp": obs.get("timestamp", ""),
                "mode": obs.get("mode", ""),
                "status": obs.get("status", ""),
                "section_notes": obs.get("section_notes", ""),
                "plants": [],
            }
        if obs.get("species"):
            submissions[sid]["plants"].append({
                "species": obs["species"],
                "strata": obs.get("strata", ""),
                "previous_count": obs.get("previous_count"),
                "new_count": obs.get("new_count"),
                "condition": obs.get("condition", ""),
                "notes": obs.get("plant_notes", ""),
            })

    grouped = list(submissions.values())
    # Sort by timestamp descending
    grouped.sort(key=lambda s: s.get("timestamp", ""), reverse=True)

    return json.dumps({
        "filters": {"status": status, "section": section, "observer": observer, "date": date},
        "total_observations": len(observations),
        "total_submissions": len(grouped),
        "submissions": grouped,
    }, indent=2)


@mcp.tool
def update_observation_status(
    submission_id: str,
    new_status: str,
    reviewer: str,
    notes: str = "",
) -> str:
    """Update the review status of field observations.

    Use this after reviewing observations to mark them as reviewed, approved, or rejected.

    Args:
        submission_id: The submission ID to update (all rows with this ID).
        new_status: New status: reviewed, approved, rejected, or imported.
        reviewer: Name of the reviewer (e.g., "Claire", "Agnes", "James").
        notes: Review notes. Optional.

    Returns:
        Update confirmation with count of rows changed.
    """
    valid_statuses = ["reviewed", "approved", "rejected", "imported"]
    if new_status not in valid_statuses:
        return json.dumps({
            "error": f"Invalid status '{new_status}'. Must be one of: {', '.join(valid_statuses)}"
        })

    obs_client = get_observe_client()
    result = obs_client.update_status([{
        "submission_id": submission_id,
        "status": new_status,
        "reviewer": reviewer,
        "notes": notes,
    }])

    if not result.get("success"):
        return json.dumps({"error": result.get("error", "Failed to update status")})

    return json.dumps({
        "status": "updated",
        "submission_id": submission_id,
        "new_status": new_status,
        "reviewer": reviewer,
        "notes": notes,
        "rows_updated": result.get("updated", 0),
    }, indent=2)


# ── ADR 0008 I8 — asset notes hygiene (re-exported) ───────────
# Implementation lives in `asset_notes.py` so scripts in the main repo
# venv (no fastmcp dep) can import it too. See that module.
from asset_notes import sanitise_asset_notes as _sanitise_asset_notes  # noqa: E402


# ── ADR 0008 I5 — field-photo tier classification ─────────────
#
# Higher tier = better candidate for species reference photo.
# tier 3: submission-id-prefixed (QR photo of one plant)
# tier 2: section-prefixed AND contains _plant_ (plant-specific import)
# tier 1: section-prefixed AND _section_ (multi-plant frame, WEAK ref)
# tier 0: stock / unrecognised

import re as _re_tier

_TIER_SUBMISSION_PLANT = _re_tier.compile(r"^[0-9a-f]{8}_.+_plant_")
_TIER_SUBMISSION = _re_tier.compile(r"^[0-9a-f]{8}_")
_TIER_SECTION_PLANT = _re_tier.compile(r"^(P\d+R\d+|NURS|COMP|SPIR)\S*_plant_")
_TIER_SECTION_SECTION = _re_tier.compile(r"^(P\d+R\d+|NURS|COMP|SPIR)\S*_section_")


def _field_photo_tier(filename: str) -> int:
    """Rank a filename 0-3. See ADR 0008 I5."""
    if not filename:
        return 0
    if _TIER_SUBMISSION_PLANT.match(filename):
        return 3
    if _TIER_SUBMISSION.match(filename):
        return 3
    if _TIER_SECTION_PLANT.match(filename):
        return 2
    if _TIER_SECTION_SECTION.match(filename):
        return 1
    return 0


def _existing_filesizes_on_log(client, log_type: str, log_id: str) -> set:
    """ADR 0008 I4 dedup — return the set of filesizes already attached
    to this log. Graceful fallback (empty set) if the lookup fails.

    Defensive: the farmos_client session is a real requests.Session in
    production but a MagicMock in tests. Iterable / truthy checks on
    MagicMock return types that are not real lists, so we validate the
    response shape before extracting sizes — anything non-dict-shaped
    results in an empty set (no dedup attempted, which is the safe
    fallback: possible double-attach instead of certain data loss).
    """
    sizes: set = set()
    try:
        url = f"{client.hostname}/api/log/{log_type}/{log_id}?include=image"
        resp = client.session.get(url, timeout=15)
        if not hasattr(resp, "ok") or not resp.ok:
            return sizes
        data = resp.json()
        if not isinstance(data, dict):
            return sizes
        included = data.get("included")
        if not isinstance(included, list):
            return sizes
        for inc in included:
            if not isinstance(inc, dict):
                continue
            if inc.get("type") != "file--file":
                continue
            attrs = inc.get("attributes")
            if not isinstance(attrs, dict):
                continue
            sz = attrs.get("filesize", 0)
            if isinstance(sz, int) and sz > 0:
                sizes.add(sz)
    except Exception:
        pass
    return sizes


def _decode_media_file(file: dict) -> Optional[tuple]:
    """Decode a base64 media file from the Apps Script ``get_media`` response.

    Returns (filename, mime_type, bytes) or ``None`` if the payload is
    unusable. The Apps Script payload format is
    ``{filename, mime_type, data_base64}``. A ``data:`` URL prefix is
    tolerated — some older submissions stored the blob that way.
    """
    import base64 as _b64

    data = file.get("data_base64") or file.get("data") or ""
    if not data:
        return None
    # Strip any "data:image/jpeg;base64," prefix defensively.
    if isinstance(data, str) and "," in data and data.lstrip().startswith("data:"):
        data = data.split(",", 1)[1]
    try:
        binary = _b64.b64decode(data)
    except Exception:
        return None
    filename = file.get("filename") or "photo.jpg"
    mime_type = file.get("mime_type") or "image/jpeg"
    return filename, mime_type, binary


def _new_photo_pipeline_report() -> dict:
    """Build a fresh per-import PhotoPipelineReport.

    Mirrors the TypeScript server's PhotoPipelineReport interface
    (see ADR 0001). Every photo failure mode is captured here so the
    operator can see what happened without querying farmOS — no more
    silent zero counts while photos vanish or land blindly.
    """
    return {
        "media_files_fetched": 0,
        "decode_failures": 0,
        "photos_uploaded": 0,
        "upload_errors": [],
        "species_reference_photos_updated": 0,
        "verification": {
            "plantnet_key_present": False,
            "botanical_lookup_size": 0,
            "plantnet_api_calls": 0,
            "photos_verified": 0,
            "photos_rejected": 0,
            "degraded": False,
            "degraded_reason": "",
        },
    }


def _upload_media_to_log(
    client,
    log_type: str,
    log_id: str,
    files: list,
    report: dict,
    context_label: str = "",
) -> list:
    """Attach a list of decoded media files to a farmOS log.

    Returns a list of farmOS file UUIDs that were successfully uploaded.
    Every failure mode is recorded in ``report`` (decode_failures,
    upload_errors with reasons) instead of being swallowed silently.
    Photo failures still never block the import — they're visible in
    the response instead of invisible.

    Mirrors the TypeScript uploadMediaToLog signature. ADR 0001.
    """
    uploaded = []
    if not log_id:
        report["upload_errors"].append(f"{context_label}: missing log id")
        return uploaded
    if not files:
        return uploaded

    # ADR 0008 I4 dedup (ADR 0007 Fix 5): skip files whose content is
    # already attached to this log, keyed on filesize as a cheap
    # content-hash proxy. Prevents the silent-success + retry double-
    # attach pattern (2026-04-18 incident).
    existing_sizes = _existing_filesizes_on_log(client, log_type, log_id)
    sizes_added_this_call = set()

    for f in files:
        decoded = _decode_media_file(f)
        if decoded is None:
            report["decode_failures"] += 1
            fname = f.get("filename", "unknown") if isinstance(f, dict) else "unknown"
            report["upload_errors"].append(
                f"{context_label}: decode_failed ({fname})"
            )
            continue
        filename, mime_type, binary = decoded
        size = len(binary)
        if size in existing_sizes or size in sizes_added_this_call:
            report["upload_errors"].append(
                f"{context_label}: already_attached ({filename}, {size}b)"
            )
            continue
        try:
            file_id = client.upload_file(
                entity_type=f"log/{log_type}",
                entity_id=log_id,
                field_name="image",
                filename=filename,
                binary_data=binary,
                mime_type=mime_type,
            )
            if file_id:
                uploaded.append(file_id)
                report["photos_uploaded"] += 1
                sizes_added_this_call.add(size)
            else:
                # upload_file returned None — file may still have landed
                # in farmOS but we lost the id. Log loudly so the operator
                # can investigate.
                report["upload_errors"].append(
                    f"{context_label}: upload_returned_null ({filename})"
                )
        except Exception as err:
            # Continue the loop on a per-file failure — import must not
            # abort, but the operator MUST see this.
            report["upload_errors"].append(
                f"{context_label}: upload_threw ({filename}): {err}"
            )
    return uploaded


def _update_species_reference_photo(client, species: str, files: list) -> Optional[str]:
    """Promote the best candidate photo to the plant_type reference.

    ADR 0008 I5 + ADR 0007 Fix 4 — tier-aware promotion (April 20 2026).
    Refuses to auto-promote tier-1 section-level multi-plant frames.
    Compares candidate tier against the plant_type's current image tier
    and only promotes if strictly better. Also patches the relationship
    to single-valued after upload so the multi-value drift that caused
    today's cleanup does not recur.

    Returns the uploaded file UUID or ``None`` if nothing happened.
    """
    if not species or not files:
        return None

    # Pick the best-tier decodable file from the incoming batch.
    best_decoded = None
    best_tier = 0
    for f in files:
        decoded = _decode_media_file(f)
        if decoded is None:
            continue
        fn = decoded[0]
        t = _field_photo_tier(fn)
        if t > best_tier:
            best_tier = t
            best_decoded = decoded
    if best_decoded is None:
        return None

    # Tier-1 section-level multi-plant frames never auto-promote.
    if best_tier <= 1:
        return None

    try:
        uuid = client.get_plant_type_uuid(species)
    except Exception:
        return None
    if not uuid:
        return None

    # Inspect current reference. Skip promotion if current is same-or-
    # higher tier (defensive; avoids stomping on a better existing photo).
    current_tier = 0
    try:
        resp = client.session.get(
            f"{client.hostname}/api/taxonomy_term/plant_type/{uuid}"
            f"?include=image", timeout=15,
        )
        if resp.ok:
            data = resp.json()
            for inc in data.get("included", []) or []:
                if inc.get("type") == "file--file":
                    fn = inc.get("attributes", {}).get("filename", "")
                    t = _field_photo_tier(fn)
                    if t > current_tier:
                        current_tier = t
    except Exception:
        pass

    if current_tier > best_tier:
        return None

    filename, mime_type, binary = best_decoded
    try:
        file_id = client.upload_file(
            entity_type="taxonomy_term/plant_type",
            entity_id=uuid,
            field_name="image",
            filename=filename,
            binary_data=binary,
            mime_type=mime_type,
        )
    except Exception:
        return None
    if not file_id:
        return None

    # Collapse image relationship to single-valued (ADR 0008 I5).
    try:
        client.session.patch(
            f"{client.hostname}/api/taxonomy_term/plant_type/{uuid}/relationships/image",
            json={"data": [{"type": "file--file", "id": file_id}]},
            headers={"Content-Type": "application/vnd.api+json"},
            timeout=15,
        )
    except Exception:
        pass  # non-fatal — upload landed, relationship may stay multi-valued

    # Tag description with photo_source=farm_observation (Tier 1)
    try:
        all_types = client.get_all_plant_types_cached()
        term = next((t for t in all_types if t.get("id") == uuid), None)
        if term:
            desc = term.get("attributes", {}).get("description", {})
            desc_text = desc.get("value", "") if isinstance(desc, dict) else str(desc or "")
            meta = parse_plant_type_metadata(desc_text)
            meta["photo_source"] = "farm_observation"
            new_desc = build_plant_type_description(meta)
            client.update_plant_type(uuid, {"description": {"value": new_desc, "format": "default"}})
    except Exception:
        pass  # non-critical — photo uploaded, tag failed
    return file_id


def _build_import_notes(obs: dict, extra: str = "", *, include_section_notes: bool = True) -> str:
    """Build rich notes from observation data for farmOS log.

    Preserves ALL raw data from the field observation so the Google Sheet
    rows can be safely deleted after import.

    `include_section_notes=False` suppresses the `Section notes:` line;
    used by the importer when section_notes are being routed to a
    dedicated section-level log (ADR 0008 I3 / Phase 3c).
    """
    parts = []
    if obs.get("observer"):
        parts.append(f"Reporter: {obs['observer']}")
    if obs.get("timestamp"):
        parts.append(f"Submitted: {obs['timestamp'][:19]}")
    if obs.get("mode"):
        parts.append(f"Mode: {obs['mode']}")
    if obs.get("condition") and obs["condition"] != "alive":
        parts.append(f"Condition: {obs['condition']}")
    if include_section_notes and obs.get("section_notes"):
        parts.append(f"Section notes: {obs['section_notes']}")
    if obs.get("plant_notes"):
        parts.append(f"Plant notes: {obs['plant_notes']}")
    if obs.get("previous_count") is not None and obs.get("new_count") is not None:
        parts.append(f"Count: {obs['previous_count']} → {obs['new_count']}")
    if extra:
        parts.append(extra)
    notes_text = "\n".join(parts)

    # Build interaction stamp for imported observations
    observer = obs.get("observer", "unknown")
    stamp = build_stamp(
        initiator=observer,
        role="farmhand",
        channel="automated",
        executor="farmos_api",
        action="created",
        target="observation",
        source_submission=obs.get("submission_id"),
        related_entities=[
            e for e in [obs.get("species"), obs.get("section_id")] if e
        ] or None,
    )
    return append_stamp(notes_text, stamp)


@mcp.tool
def import_observations(
    submission_id: str,
    reviewer: str = "Claude",
    dry_run: bool = False,
) -> str:
    """Import approved/reviewed observations from the Sheet into farmOS.

    Fetches observations for the submission, validates against farmOS,
    creates appropriate logs/assets, and updates Sheet status to imported.

    Args:
        submission_id: The submission ID to import.
        reviewer: Who is performing the import. Default "Claude".
        dry_run: If true, show what would happen without making changes. Default false.

    Returns:
        Import results: what was created/updated in farmOS, any errors.
    """
    obs_client = get_observe_client()
    client = get_client()

    # Fetch observations for this submission
    result = obs_client.list_observations(submission_id=submission_id)
    if not result.get("success"):
        return json.dumps({"error": result.get("error", "Failed to fetch observations")})

    observations = result.get("observations", [])
    if not observations:
        # ADR 0007 Fix 2: empty result can mean the submission was already
        # imported (delete_imported cleaned up rows after success) or that
        # the ID is unknown. Treat as idempotent "already imported" rather
        # than a hard error so retries are safe.
        return json.dumps({
            "status": "already_imported_or_unknown",
            "submission_id": submission_id,
            "message": (
                f"No observations found for submission '{submission_id}'. "
                "This submission may already have been imported (rows deleted "
                "after successful import) or the ID is unknown. Check farmOS "
                f"for logs with 'submission={submission_id}' in notes."
            ),
            "actions": 0,
        })

    # Validate status — must be reviewed, approved, or already imported
    statuses = set(obs.get("status") for obs in observations)
    # ADR 0007 Fix 2: if all observations are already imported, skip
    # gracefully with success — retries must be idempotent.
    if statuses == {"imported"}:
        return json.dumps({
            "status": "already_imported",
            "submission_id": submission_id,
            "message": "All observations for this submission have already been imported. Skipping.",
            "observation_count": len(observations),
            "actions": 0,
        })
    if statuses - {"reviewed", "approved", "imported"}:
        return json.dumps({
            "error": f"Submission has unexpected statuses: {statuses}. "
                     "Only 'reviewed', 'approved', or 'imported' (skipped) can be processed.",
        })

    section_id = observations[0].get("section_id", "")
    mode = observations[0].get("mode", "")
    obs_date = observations[0].get("timestamp", "")[:10]  # YYYY-MM-DD

    # ── Photo pipeline setup (April 15 2026 redesign — ADR 0001) ──
    #
    # Architecture: always attach photos to the log unconditionally.
    # PlantNet verification is used ONLY to decide whether to promote a
    # photo as the plant_type reference photo. Verification failure never
    # loses the photo, only demotes the quality signal.
    #
    # Every failure mode surfaces in ``photo_pipeline_report`` so the
    # operator can see what actually happened. No more silent zero counts.
    from plantnet_verify import (
        build_botanical_lookup,
        verify_species_photo,
        get_call_count,
        reset_call_count,
    )

    actions = []
    errors: list = []
    report = _new_photo_pipeline_report()
    reset_call_count()
    report["verification"]["plantnet_key_present"] = bool(
        os.getenv("PLANTNET_API_KEY", "").strip()
    )

    # Always fetch media for non-dry-run imports. Apps Script handleGetMedia
    # filters Drive files by the 8-char submission_id prefix and does not
    # depend on the sheet's media_files column being populated. The earlier
    # gate on any_media_listed was fragile — an upstream regression that
    # emptied the column (observed 2026-04-21) silently dropped ~13 photo
    # attachments from farmOS even though the files were safely in Drive.
    # Cost of removing the gate: one extra Drive scan per submission on
    # imports where the observer didn't upload photos — cheap. Benefit:
    # photo attachment is driven by the photos actually existing, not by
    # a bookkeeping column that can regress without warning.
    submission_media: list = []
    any_media_listed = any((obs.get("media_files") or "").strip() for obs in observations)
    if not dry_run:
        try:
            media_resp = obs_client.get_media(submission_id)
            if media_resp.get("success"):
                submission_media = media_resp.get("files") or []
            else:
                errors.append(
                    f"Media fetch returned not-ok: {media_resp.get('error', 'unknown')}"
                )
        except Exception as exc:
            errors.append(f"Media fetch threw: {exc}")
            submission_media = []
    report["media_files_fetched"] = len(submission_media)
    # Warn if the column-based gate would have gated photos we just found.
    # This is an early-warning signal that the QR form or Apps Script
    # write path has regressed — photos still attach, but fix upstream.
    if not dry_run and not any_media_listed and len(submission_media) > 0:
        errors.append(
            f"WARN: sheet media_files column was empty but Drive had "
            f"{len(submission_media)} photos for submission {submission_id}. "
            f"Photos attached successfully via submission_id-prefix lookup. "
            f"Upstream regression — investigate QR form or Apps Script "
            f"mediaFilesList write path."
        )

    botanical_lookup = build_botanical_lookup() if submission_media else {}
    # Strip the internal "__reverse__" key before measuring size
    _reverse = botanical_lookup.get("__reverse__", {}) if botanical_lookup else {}
    report["verification"]["botanical_lookup_size"] = len(_reverse) if isinstance(_reverse, dict) else 0

    species_photo_updates: set = set()  # Track species we've already refreshed.

    # ── ADR 0008 I9 + Phase 3c — submission-level photo routing ──
    # Rule: in a multi-observation submission, photos attach to ONE
    # section-level log (asset_ids=[]) rather than fanning across
    # every per-plant log. In a single-observation submission, the
    # one log receives its own photos as before.
    # Also: section_notes are consolidated onto the section log and
    # removed from per-plant log notes (Phase 3c).
    _species_obs = [o for o in observations if (o.get("species") or "").strip()]
    _has_plant_obs = bool(_species_obs)
    _is_multi_plant = len(_species_obs) > 1
    # Inventory-mode submissions carry the same section_notes on every
    # species row after the QR form's sheet expansion, so concatenating
    # all rows produced N duplicate copies (bug discovered 2026-04-22
    # mid-import — Cuban Jute note appeared 4× on the P2R5.22-29 section
    # log). Dedupe unique non-empty section_notes strings before joining.
    _seen_notes: set = set()
    _dedup_notes: list = []
    for _o in observations:
        _n = (_o.get("section_notes") or "").strip()
        if _n and _n not in _seen_notes:
            _seen_notes.add(_n)
            _dedup_notes.append(_n)
    _combined_section_notes = "\n\n".join(_dedup_notes).strip()
    _route_photos_to_section = bool(_is_multi_plant and submission_media)
    # A dedicated section log is needed only when plant observations
    # ALSO exist (otherwise the section-only Case A already creates
    # the single section log itself).
    _needs_section_log = (
        (_has_plant_obs and bool(_combined_section_notes))
        or _route_photos_to_section
    )
    _section_log_info: dict = {"id": None, "created": False}
    _first_section_id = observations[0].get("section_id") if observations else None

    def _ensure_section_log() -> Optional[str]:
        """Create the submission's section-level log on first need.

        Idempotent per submission. Attaches all submission media once
        when created. Returns the log id (or None on dry_run / error).
        """
        if _section_log_info["created"]:
            return _section_log_info["id"]
        _section_log_info["created"] = True
        if not _needs_section_log or dry_run or not _first_section_id:
            return None
        first_obs = _species_obs[0] if _species_obs else observations[0]
        section_notes_text = _combined_section_notes or (
            "Section-level submission evidence"
            if _route_photos_to_section else ""
        )
        section_log_obs = {
            "observer": first_obs.get("observer"),
            "timestamp": first_obs.get("timestamp"),
            "mode": first_obs.get("mode"),
            "section_notes": section_notes_text,
            "section_id": _first_section_id,
            "submission_id": submission_id,
        }
        try:
            result_json = json.loads(create_activity(
                section_id=_first_section_id,
                activity_type="observation",
                notes=_build_import_notes(section_log_obs),
                date=(first_obs.get("timestamp") or "")[:10] or None,
            ))
            _section_log_info["id"] = result_json.get("log_id")
            # Attach all submission media to the section log exactly once.
            photos_attached = 0
            if submission_media and _section_log_info["id"]:
                before = report["photos_uploaded"]
                _upload_media_to_log(
                    client, "activity", _section_log_info["id"],
                    submission_media, report,
                    f"section/{_first_section_id}",
                )
                photos_attached = report["photos_uploaded"] - before
            # Record the section-log creation as an action so the
            # import report surfaces it.
            actions.append({
                "type": "activity",
                "section": _first_section_id,
                "scope": "section_level",
                "log_id": _section_log_info["id"],
                "result": result_json.get("status", "unknown"),
                "photos_uploaded": photos_attached,
                "notes": _combined_section_notes[:200] if _combined_section_notes else "",
            })
        except Exception as e:
            errors.append(f"Section log creation: {e}")
            _section_log_info["id"] = None
        return _section_log_info["id"]

    def _should_attach_per_log() -> bool:
        """Per-plant logs receive photos only in single-plant submissions."""
        return not _route_photos_to_section

    # I11 — classifier: derive log type and status from notes content.
    from classifier import classify_observation

    def _classify_and_annotate(notes: str, default_log_type: str) -> tuple[str, str, str]:
        """Run the classifier. Return (possibly-annotated notes, status, type_hint).

        - If classifier confidence is low/ambiguous, prepend a flag marker so
          the log surfaces for human review.
        - If the classified type differs from `default_log_type` (e.g. notes
          read as 'seeded' but we're routing through `create_observation`),
          prepend a `[CLASSIFIER-HINT: type=<x>]` line so auditor can re-type.
        - Return the classifier-determined status ('done' or 'pending').
        """
        if not notes:
            return notes or "", "done", ""
        classified = classify_observation(notes)
        status = classified["status"]
        ctype = classified["type"]
        annotations = []
        if classified.get("ambiguous"):
            annotations.append(
                f"[FLAG classifier-ambiguous: {classified.get('reason','unknown')}]"
            )
        # Only hint when the classifier strongly disagrees with the default
        # route (e.g. seeding/transplanting/harvest going through observation).
        if ctype not in (default_log_type, "observation") and not classified.get("ambiguous"):
            annotations.append(f"[CLASSIFIER-HINT: type={ctype}]")
        if annotations:
            return "\n".join(annotations) + "\n" + notes, status, ctype
        return notes, status, ctype

    def _verify_one_photo(media: dict, species: str) -> dict:
        """Run a single photo through PlantNet. Records results in the report.

        Once verification is marked degraded (e.g. first call hits HTTP 403),
        short-circuits for the rest of the import so we don't burn quota
        on calls that will all fail.
        """
        if report["verification"]["degraded"]:
            return {"verified": False, "reason": "verification_degraded"}
        if not report["verification"]["plantnet_key_present"]:
            return {"verified": False, "reason": "no_api_key"}
        if not botanical_lookup or report["verification"]["botanical_lookup_size"] == 0:
            return {"verified": False, "reason": "no_botanical_lookup"}
        if not species:
            return {"verified": True, "reason": "no_species_claim"}
        decoded = _decode_media_file(media)
        if decoded is None:
            return {"verified": False, "reason": "decode_failed"}
        _filename, _mime, binary = decoded
        result = verify_species_photo(binary, species, botanical_lookup)
        # Auth-failure short-circuit — disable verification for rest of import
        reason = result.get("reason", "")
        if (not result.get("verified")) and ("api_http_401" in reason or "api_http_403" in reason):
            report["verification"]["degraded"] = True
            report["verification"]["degraded_reason"] = (
                f"PlantNet authentication failed ({reason}). "
                f"Check the API key and its authorized domains on my.plantnet.org. "
                f"Photos are still being attached to logs — only species-reference "
                f"promotion is disabled."
            )
            print(f"  [plantnet] {report['verification']['degraded_reason']}")
        return result

    def _attach_and_maybe_promote(
        log_id: Optional[str],
        log_type: str,
        species: str,
        context_label: str,
    ) -> int:
        """Attach all submission photos to the log; promote if verified.

        Every photo is uploaded UNCONDITIONALLY. Verification only affects
        species-reference-photo promotion. Returns the count of successfully
        uploaded photos for this log.
        """
        if not log_id or not submission_media:
            return 0

        before = report["photos_uploaded"]
        _upload_media_to_log(
            client, log_type, log_id, submission_media, report, context_label
        )
        uploaded_count = report["photos_uploaded"] - before

        # Species-reference-photo promotion — not a gate on attachment.
        if not species or species in species_photo_updates:
            return uploaded_count

        verified_for_promotion = []
        for f in submission_media:
            v = _verify_one_photo(f, species)
            if v.get("verified"):
                report["verification"]["photos_verified"] += 1
                verified_for_promotion.append(f)
                # First verified photo is enough — stop burning PlantNet calls
                break
            elif v.get("reason") not in (
                "verification_degraded", "no_api_key", "no_botanical_lookup"
            ):
                report["verification"]["photos_rejected"] += 1

        if verified_for_promotion:
            ref_id = _update_species_reference_photo(
                client, species, verified_for_promotion
            )
            if ref_id:
                species_photo_updates.add(species)
                report["species_reference_photos_updated"] += 1
        return uploaded_count

    for obs in observations:
        species = obs.get("species", "").strip()
        new_count = obs.get("new_count")
        previous_count = obs.get("previous_count")
        condition = obs.get("condition", "")
        plant_notes = obs.get("plant_notes", "")
        section_notes = obs.get("section_notes", "")
        obs_section = obs.get("section_id", section_id)
        obs_mode = obs.get("mode", mode)

        # Case A: Section comment only (no species)
        if not species and section_notes:
            # I9 / Phase 3c: if this submission also has plant
            # observations, the dedicated section log is created lazily
            # via _ensure_section_log and captures section_notes from
            # all obs plus media. Route to it to avoid duplication.
            if _needs_section_log:
                # _ensure_section_log appends its own action on creation
                # (scope=section_level). Just route here without adding
                # a duplicate entry. In dry_run we still record the
                # intent so the report surfaces it.
                if dry_run:
                    actions.append({
                        "type": "activity",
                        "section": obs_section,
                        "notes": "[will route to section-level submission log]",
                        "result": "dry_run",
                        "scope": "section_level",
                    })
                else:
                    _ensure_section_log()
                continue
            action = {
                "type": "activity",
                "section": obs_section,
                "notes": section_notes,
            }
            if not dry_run:
                try:
                    result_json = json.loads(create_activity(
                        section_id=obs_section,
                        activity_type="observation",
                        notes=_build_import_notes(obs),
                        date=obs_date or None,
                    ))
                    action["result"] = result_json.get("status", "unknown")
                    action["log_id"] = result_json.get("log_id")
                    # Single-obs section log gets its own photos.
                    if _should_attach_per_log():
                        photo_count = _attach_and_maybe_promote(
                            action.get("log_id"), "activity", "",
                            f"activity/{obs_section}",
                        )
                        if photo_count > 0:
                            action["photos_uploaded"] = photo_count
                except Exception as e:
                    action["result"] = "error"
                    errors.append(f"Activity for {obs_section}: {e}")
            else:
                action["result"] = "dry_run"
            actions.append(action)
            continue

        # Skip rows with no species (e.g., empty padding rows)
        if not species:
            continue

        # Case B: New plant (mode=new_plant or inferred from previous_count=0)
        if obs_mode == "new_plant" or (previous_count == 0 and new_count and new_count > 0):
            count = int(new_count) if new_count else 1
            action = {
                "type": "create_plant",
                "species": species,
                "section": obs_section,
                "count": count,
                "notes": plant_notes,
            }
            if not dry_run:
                try:
                    result_json = json.loads(create_plant(
                        species=species,
                        section_id=obs_section,
                        count=count,
                        planted_date=obs_date or None,
                        notes=_build_import_notes(
                            obs, "New plant added via field observation",
                            include_section_notes=not _needs_section_log,
                        ),
                    ))
                    action["result"] = result_json.get("status", "unknown")
                    action["plant_name"] = result_json.get("plant", {}).get("name")
                    # create_plant emits an "Inventory" observation log (sets
                    # location + initial count) whose id is returned in
                    # result_json["observation_log"]["id"]. Attach photos there
                    # so the media is associated with the planting event.
                    photo_log_id = (result_json.get("observation_log") or {}).get("id")
                    # I9: attach photos to this per-plant log only if this
                    # is a single-plant submission; otherwise photos go to
                    # the section log (via _ensure_section_log).
                    if _should_attach_per_log():
                        photo_count = _attach_and_maybe_promote(
                            photo_log_id, "observation", species,
                            f"new_plant/{obs_section}/{species}",
                        )
                        if photo_count > 0:
                            action["photos_uploaded"] = photo_count
                        if species in species_photo_updates:
                            action["species_reference_photo"] = True
                    else:
                        _ensure_section_log()
                        action["photos_routed"] = "section_log"
                except Exception as e:
                    action["result"] = "error"
                    errors.append(f"Create {species} in {obs_section}: {e}")
            else:
                action["result"] = "dry_run"
            actions.append(action)
            continue

        # Case C: Inventory update (existing plant, count changed or has notes)
        if new_count is not None or plant_notes or condition:
            # Find existing plant asset by species + section
            plants = client.get_plant_assets(section_id=obs_section, species=species)
            if not plants:
                errors.append(
                    f"Plant '{species}' not found in section {obs_section}. "
                    "Use import as new plant instead."
                )
                continue

            plant = plants[0]
            plant_name = plant.get("attributes", {}).get("name", "")
            formatted = format_plant_asset(plant)

            # Build notes — preserve all raw data from the field observation.
            # I3 / Phase 3c: strip section_notes when they're routed to a
            # section-level log instead.
            combined_notes = _build_import_notes(
                obs, include_section_notes=not _needs_section_log,
            )

            # Split observation + action text into separate farmOS logs
            # Nursery inline forms send "Observation: X\nAction: Y" in plant_notes
            obs_text = ""
            action_text = ""
            if plant_notes:
                for line in plant_notes.split("\n"):
                    line = line.strip()
                    if line.startswith("Observation:"):
                        obs_text = line[len("Observation:"):].strip()
                    elif line.startswith("Action:"):
                        action_text = line[len("Action:"):].strip()

            # Only update if count changed or there are meaningful notes
            count_val = int(new_count) if new_count is not None else None
            prev_val = int(previous_count) if previous_count is not None else None
            count_changed = count_val is not None and count_val != prev_val

            if count_changed or combined_notes:
                # 1. Observation log (inventory count + observation text)
                obs_notes = _build_import_notes(
                    obs, include_section_notes=not _needs_section_log,
                )
                if obs_text:
                    obs_notes += f"\nObservation: {obs_text}"

                action = {
                    "type": "observation",
                    "plant_name": plant_name,
                    "species": species,
                    "section": obs_section,
                    "previous_count": prev_val,
                    "new_count": count_val,
                    "notes": obs_notes,
                }
                # I11: classify from plant_notes (human-authored text only,
                # skipping the import-payload headers the classifier would
                # otherwise trip on). Attach hints/flags to the farmOS log.
                _classifier_source = (plant_notes or "").strip()
                _annotated_notes, _classified_status, _ = _classify_and_annotate(
                    obs_notes, default_log_type="observation",
                ) if _classifier_source else (obs_notes, "done", "")
                if not dry_run and count_val is not None:
                    try:
                        result_json = json.loads(create_observation(
                            plant_name=plant_name,
                            count=count_val,
                            notes=_annotated_notes,
                            date=obs_date or None,
                            status=_classified_status,
                            submission_id=submission_id,
                        ))
                        action["result"] = result_json.get("status", "unknown")
                        action["log_status"] = _classified_status
                        action["log_id"] = result_json.get("log_id")
                        # I9: attach photos here only if single-plant submission.
                        if _should_attach_per_log():
                            photo_count = _attach_and_maybe_promote(
                                action.get("log_id"), "observation", species,
                                f"observation/{obs_section}/{species}",
                            )
                            if photo_count > 0:
                                action["photos_uploaded"] = photo_count
                            if species in species_photo_updates:
                                action["species_reference_photo"] = True
                        else:
                            _ensure_section_log()
                            action["photos_routed"] = "section_log"
                    except Exception as e:
                        action["result"] = "error"
                        errors.append(f"Observation for {species} in {obs_section}: {e}")
                elif not dry_run and count_val is None and not action_text:
                    # Notes-only, no action text — classifier decides
                    # activity_type + status (I11).
                    _annot_notes, _act_status, _classified_type = _classify_and_annotate(
                        obs_notes, default_log_type="activity",
                    )
                    # Use the classified verb as activity_type when it's
                    # a recognised action; fall back to "observation".
                    _activity_type = (
                        _classified_type
                        if _classified_type in ("activity", "seeding",
                                                 "transplanting", "harvest")
                        else "observation"
                    )
                    try:
                        result_json = json.loads(create_activity(
                            section_id=obs_section,
                            activity_type=_activity_type,
                            notes=_annot_notes,
                            date=obs_date or None,
                            status=_act_status,
                        ))
                        action["result"] = result_json.get("status", "unknown")
                        action["type"] = "activity"
                        action["log_status"] = _act_status
                        action["classified_type"] = _classified_type
                        # I9: same routing rule for activity logs.
                        if _should_attach_per_log():
                            photo_count = _attach_and_maybe_promote(
                                result_json.get("log_id"), "activity", species,
                                f"activity/{obs_section}/{species}",
                            )
                            if photo_count > 0:
                                action["photos_uploaded"] = photo_count
                            if species in species_photo_updates:
                                action["species_reference_photo"] = True
                        else:
                            _ensure_section_log()
                            action["photos_routed"] = "section_log"
                    except Exception as e:
                        action["result"] = "error"
                        errors.append(f"Activity for {species} in {obs_section}: {e}")
                else:
                    action["result"] = "dry_run"
                actions.append(action)

                # 2. Separate activity log for action text (if present)
                if action_text:
                    act_action = {
                        "type": "activity",
                        "plant_name": plant_name,
                        "species": species,
                        "section": obs_section,
                        "notes": f"Action: {action_text}",
                    }
                    if not dry_run:
                        try:
                            act_notes = f"Reporter: {obs.get('observer', '')}\nAction: {action_text}"
                            result_json = json.loads(create_activity(
                                section_id=obs_section,
                                activity_type="nursery action",
                                notes=act_notes,
                                date=obs_date or None,
                                status="pending",
                            ))
                            act_action["result"] = result_json.get("status", "unknown")
                            act_action["log_id"] = result_json.get("log_id")
                        except Exception as e:
                            act_action["result"] = "error"
                            errors.append(f"Activity for {species} in {obs_section}: {e}")
                    else:
                        act_action["result"] = "dry_run"
                    actions.append(act_action)

    # I9 / Phase 3c — end-of-loop guarantee: if a section log was needed
    # (section_notes present or multi-plant-with-photos) but wasn't
    # triggered via _ensure_section_log (e.g. all per-plant writes
    # erred out), create it now so section_notes + photos aren't lost.
    if _needs_section_log and not _section_log_info["created"]:
        _ensure_section_log()

    # Update Sheet status to imported (unless dry_run or all failed)
    imported_count = sum(1 for a in actions if a.get("result") == "created")
    sheet_status = "dry_run" if dry_run else "pending"
    if not dry_run and (imported_count > 0 or not errors):
        try:
            obs_client.update_status([{
                "submission_id": submission_id,
                "status": "imported",
                "reviewer": reviewer,
                "notes": f"{imported_count} actions imported to farmOS",
            }])
            sheet_status = "imported"
        except Exception as e:
            errors.append(f"Failed to update Sheet status: {e}")
            sheet_status = "partial"

        # Delete imported rows from Sheet (raw data preserved in farmOS log notes)
        if sheet_status == "imported":
            try:
                obs_client.delete_imported(submission_id)
                sheet_status = "imported_and_cleaned"
            except Exception as e:
                errors.append(f"Failed to clean up Sheet rows: {e}")

    # Auto-regenerate QR landing pages if on a machine with the project repo
    regen_message = None
    if not dry_run and actions:
        if os.path.isfile(_MAIN_VENV_PYTHON):
            try:
                regen_result = json.loads(regenerate_pages(push_to_github=True))
                regen_message = regen_result.get("status", "unknown")
            except Exception as e:
                regen_message = f"regeneration failed: {e}"
        else:
            regen_message = (
                "Pages need regeneration. Run regenerate_pages tool on a machine "
                "with the project repo, or ask Agnes."
            )

    # Snapshot PlantNet call count into the report (counter was reset at
    # the start of the import, so this is the per-import total).
    report["verification"]["plantnet_api_calls"] = get_call_count()

    # Emit loud warnings if the pipeline is silently degraded — the
    # operator should never have to go digging in farmOS to find out
    # what happened. Matches ADR 0001 / the TypeScript server.
    photo_health_warnings = []
    if report["media_files_fetched"] > 0 and report["photos_uploaded"] == 0:
        photo_health_warnings.append(
            f"CRITICAL: {report['media_files_fetched']} media files fetched but "
            f"0 uploaded. Check upload_errors in photo_pipeline for specifics."
        )
    if (
        report["media_files_fetched"] > 0
        and report["verification"]["photos_verified"] == 0
        and report["verification"]["plantnet_api_calls"] == 0
        and report["verification"]["plantnet_key_present"]
        and report["verification"]["botanical_lookup_size"] > 0
        and not report["verification"]["degraded"]
    ):
        photo_health_warnings.append(
            "WARNING: PlantNet is configured but was never called. "
            "Verification may be silently short-circuiting."
        )
    if report["verification"]["degraded"]:
        photo_health_warnings.append(
            f"INFO: Verification degraded mid-import. Photos still attached "
            f"to logs; species-reference-photo promotion disabled. "
            f"Reason: {report['verification']['degraded_reason']}"
        )

    return json.dumps({
        "submission_id": submission_id,
        "section_id": section_id,
        "dry_run": dry_run,
        "total_actions": len(actions),
        "actions": actions,
        "errors": errors if errors else None,
        "sheet_status": sheet_status,
        "pages_regenerated": regen_message,

        # Flat metrics — backwards compatible with earlier callers that
        # still read these keys directly.
        "photos_uploaded": report["photos_uploaded"],
        "photos_verified": report["verification"]["photos_verified"],
        "photos_rejected": report["verification"]["photos_rejected"],
        "plantnet_api_calls": report["verification"]["plantnet_api_calls"],
        "species_reference_photos_updated": report["species_reference_photos_updated"],
        "submission_media_fetched": len(submission_media) if not dry_run else 0,

        # Rich pipeline diagnostics — this is where the operator looks to
        # understand what actually happened. "photos_uploaded: 0" is never
        # a mystery anymore. Mirrors the TypeScript response shape. ADR 0001.
        "photo_pipeline": {
            **report,
            "warnings": photo_health_warnings if photo_health_warnings else None,
        },
    }, indent=2)


# ═══════════════════════════════════════════════════════════════
# TOOLS — Batch observation management (April 15 2026)
# ═══════════════════════════════════════════════════════════════
#
# The batch tools exist to collapse many tool calls into one for
# multi-submission flows. The trigger was Leah's April 14 walk: 15
# submissions required ~45 tool calls through the single-submission
# tools (1 approve + 1 import per submission + overhead). These
# batch versions reduce that to a handful of calls.


@mcp.tool
def update_observation_status_batch(
    submission_ids: list,
    new_status: str,
    reviewer: str,
    notes: str = "",
) -> str:
    """Batch version of update_observation_status.

    Updates the review status of many submissions in ONE Apps Script call.
    Use this when you need to flip more than 2-3 submissions at once — e.g.
    marking a whole WWOOFer walk as 'approved' before running
    import_observations_batch. For single submissions, prefer the
    non-batch tool.

    Args:
        submission_ids: List of submission IDs to update (1+).
        new_status: New status applied to all: reviewed, approved, rejected, or imported.
        reviewer: Name of the reviewer.
        notes: Review notes applied to every entry. Optional.

    Returns:
        Batch update summary with per-submission outcome and total row count.
    """
    valid_statuses = ["reviewed", "approved", "rejected", "imported"]
    if new_status not in valid_statuses:
        return json.dumps({
            "error": f"Invalid status '{new_status}'. Must be one of: {', '.join(valid_statuses)}"
        })

    if not submission_ids:
        return json.dumps({"error": "submission_ids must contain at least one id"})

    ids = list(dict.fromkeys(submission_ids))  # dedupe preserving order
    entries = [
        {
            "submission_id": sid,
            "status": new_status,
            "reviewer": reviewer,
            "notes": notes,
        }
        for sid in ids
    ]

    obs_client = get_observe_client()
    result = obs_client.update_status(entries)

    if not result.get("success"):
        return json.dumps({
            "error": result.get("error", "Failed to update status"),
            "submission_ids": ids,
        })

    return json.dumps({
        "status": "updated",
        "submission_count": len(ids),
        "submission_ids": ids,
        "new_status": new_status,
        "reviewer": reviewer,
        "notes": notes,
        "rows_updated": result.get("updated", 0),
    }, indent=2)


@mcp.tool
def import_observations_batch(
    submission_ids: list,
    reviewer: str = "Claude",
    dry_run: bool = False,
    continue_on_error: bool = True,
) -> str:
    """Batch version of import_observations.

    Imports many submissions in one tool call by looping the existing
    single-submission importer internally. The loop is sequential — parallel
    imports would race on farmOS deduplication checks and PlantNet rate
    limits.

    Use this when you need to import more than 2-3 submissions at once
    (e.g. clearing a WWOOFer's walk). For single submissions, prefer the
    non-batch tool.

    Args:
        submission_ids: List of submission IDs to import (1+).
        reviewer: Who is performing the import. Default "Claude".
        dry_run: If true, preview only without making changes.
        continue_on_error: If true (default), keep importing after a failure.
            If false, abort on the first error.

    Returns:
        Per-submission results + aggregated photo_pipeline metrics + errors.
    """
    if not submission_ids:
        return json.dumps({"error": "submission_ids must contain at least one id"})

    unique_ids = list(dict.fromkeys(submission_ids))

    # ADR 0007 Fix 6 — batch-size cap. 5 is the safe ceiling given the
    # current 60s MCP timeout (each submission takes 3-10s). Raise this
    # only when Fix 3 (async job queue) ships.
    MAX_BATCH_SIZE = 5
    if len(unique_ids) > MAX_BATCH_SIZE:
        return json.dumps({
            "error": f"Batch size {len(unique_ids)} exceeds limit {MAX_BATCH_SIZE}.",
            "reason": (
                f"The synchronous import path cannot reliably complete more "
                f"than {MAX_BATCH_SIZE} submissions within the 60s MCP "
                f"timeout (each submission takes 3-10s). Import in chunks of "
                f"{MAX_BATCH_SIZE} or fewer, or wait for the async job queue "
                f"(ADR 0007 Fix 3)."
            ),
            "submitted_count": len(unique_ids),
            "limit": MAX_BATCH_SIZE,
            "suggested": f"import_observations_batch(submission_ids=submission_ids[:{MAX_BATCH_SIZE}])",
        })

    per_submission: list = []
    batch_errors: list = []
    total_actions = 0

    # Aggregated photo pipeline report — sum per-submission reports into
    # one roll-up the operator can scan without flipping between entries.
    aggregate = {
        "media_files_fetched": 0,
        "decode_failures": 0,
        "photos_uploaded": 0,
        "upload_errors": [],
        "species_reference_photos_updated": 0,
        "verification": {
            "plantnet_key_present": False,
            "botanical_lookup_size": 0,
            "plantnet_api_calls": 0,
            "photos_verified": 0,
            "photos_rejected": 0,
            "degraded": False,
            "degraded_reason": "",
        },
    }

    for sid in unique_ids:
        try:
            raw = import_observations(
                submission_id=sid, reviewer=reviewer, dry_run=dry_run,
            )
            parsed = json.loads(raw)
        except Exception as exc:
            msg = f"import threw for {sid}: {exc}"
            batch_errors.append(msg)
            per_submission.append({"submission_id": sid, "error": msg})
            if not continue_on_error:
                break
            continue

        if parsed.get("error"):
            msg = f"import returned error for {sid}: {parsed['error']}"
            batch_errors.append(msg)
            per_submission.append({"submission_id": sid, "error": msg})
            if not continue_on_error:
                break
            continue

        per_submission.append({
            "submission_id": sid,
            "section_id": parsed.get("section_id"),
            "total_actions": parsed.get("total_actions"),
            "sheet_status": parsed.get("sheet_status"),
            "photos_uploaded": parsed.get("photos_uploaded"),
            "species_reference_photos_updated": parsed.get("species_reference_photos_updated"),
            "errors": parsed.get("errors"),
        })
        total_actions += parsed.get("total_actions") or 0

        pp = parsed.get("photo_pipeline") or {}
        aggregate["media_files_fetched"] += pp.get("media_files_fetched") or 0
        aggregate["decode_failures"] += pp.get("decode_failures") or 0
        aggregate["photos_uploaded"] += pp.get("photos_uploaded") or 0
        aggregate["species_reference_photos_updated"] += pp.get("species_reference_photos_updated") or 0
        upload_errors = pp.get("upload_errors") or []
        for e in upload_errors:
            aggregate["upload_errors"].append(f"[{sid}] {e}")
        vv = pp.get("verification") or {}
        aggregate["verification"]["plantnet_key_present"] = (
            aggregate["verification"]["plantnet_key_present"] or bool(vv.get("plantnet_key_present"))
        )
        aggregate["verification"]["botanical_lookup_size"] = max(
            aggregate["verification"]["botanical_lookup_size"],
            vv.get("botanical_lookup_size") or 0,
        )
        aggregate["verification"]["plantnet_api_calls"] += vv.get("plantnet_api_calls") or 0
        aggregate["verification"]["photos_verified"] += vv.get("photos_verified") or 0
        aggregate["verification"]["photos_rejected"] += vv.get("photos_rejected") or 0
        if vv.get("degraded"):
            aggregate["verification"]["degraded"] = True
            if not aggregate["verification"]["degraded_reason"]:
                aggregate["verification"]["degraded_reason"] = vv.get("degraded_reason", "")

        nested_errors = parsed.get("errors") or []
        for e in nested_errors:
            batch_errors.append(f"[{sid}] {e}")

    processed = len(per_submission)
    succeeded = sum(1 for r in per_submission if "error" not in r)

    return json.dumps({
        "status": "ok" if succeeded == len(unique_ids) else "partial",
        "submitted": len(unique_ids),
        "processed": processed,
        "succeeded": succeeded,
        "dry_run": dry_run,
        "total_actions": total_actions,
        "submissions": per_submission,
        "errors": batch_errors if batch_errors else None,
        "photo_pipeline": aggregate,
    }, indent=2)


# ═══════════════════════════════════════════════════════════════
# TOOLS — Site generation (regenerate QR landing pages)
# ═══════════════════════════════════════════════════════════════

# Resolve project paths relative to server.py location
_SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SERVER_DIR)
_MAIN_VENV_PYTHON = os.path.join(_PROJECT_ROOT, "venv", "bin", "python3")
_SCRIPTS_DIR = os.path.join(_PROJECT_ROOT, "scripts")
_SECTIONS_JSON = os.path.join(_PROJECT_ROOT, "site", "src", "data", "sections.json")
_PLANT_TYPES_CSV = os.path.join(_PROJECT_ROOT, "knowledge", "plant_types.csv")

# Observe endpoint (Apps Script URL baked into generated observe pages)
_OBSERVE_ENDPOINT = os.getenv(
    "OBSERVE_ENDPOINT",
    "https://script.google.com/macros/s/AKfycbwxz3n9MSH45tQ1KX1_MacGAheIP_KcFMmlX_AWnYMI4-wwQ0ZNjYO5U8DJqHebcGPa/exec",
)


def _run_script(script_name: str, args: list = None) -> dict:
    """Run a project script using the main project venv Python.

    Returns dict with stdout, stderr, returncode.
    """
    script_path = os.path.join(_SCRIPTS_DIR, script_name)
    cmd = [_MAIN_VENV_PYTHON, script_path] + (args or [])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=_PROJECT_ROOT,
            env={**os.environ, "PYTHONPATH": _PROJECT_ROOT},
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout,
            "stderr": result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "stdout": "", "stderr": "Script timed out after 120 seconds"}
    except Exception as e:
        return {"returncode": -1, "stdout": "", "stderr": str(e)}


# ── Farm Context (Intelligence Layer) ──────────────────────────────


@mcp.tool
def farm_context(
    subject: Optional[str] = None,
    section: Optional[str] = None,
    topic: Optional[str] = None,
) -> str:
    """Cross-reference farmOS, Knowledge Base, and plant types in one call.

    Returns interpreted farm intelligence with all five layers:
    ontology (what exists), facts (what's true), interpretation (what it means),
    context (what we did about it), and gaps (what's missing).

    Provide exactly ONE of:
    - subject: Species name (e.g., "Pigeon Pea") — distribution + KB + metadata
    - section: Section ID (e.g., "P2R3.15-21") — health assessment + pending tasks
    - topic: Farm domain (e.g., "nursery") — domain overview + transplant readiness
    """
    from semantics import (
        assess_section_health,
        find_transplant_ready,
        detect_knowledge_gaps,
        detect_decision_gaps,
        detect_logging_gaps,
        load_semantics,
    )
    from helpers import TOPIC_FARMOS_MAP

    if not any([subject, section, topic]):
        return json.dumps({"error": "Provide one of: subject, section, or topic"})

    client = get_client()
    kb_client = get_knowledge_client()
    semantics = load_semantics()
    result = {}

    # ── Section mode ──────────────────────────────────────────
    if section:
        result["query"] = {"type": "section", "id": section}

        # Determine section type and constraints
        is_nursery = section.startswith("NURS.")
        has_trees = not is_nursery  # nursery zones don't have tree expectations
        entity_type = "nursery_zone" if is_nursery else "paddock_section"

        result["ontology"] = {
            "entity_type": entity_type,
            "constraints": [
                "expects 4 strata layers (emergent, high, medium, low)" if has_trees else "nursery zone — no strata expectation",
            ],
        }

        # Layer 2: Facts
        plants_raw = client.get_plant_assets(section_id=section)
        plants = [format_plant_asset(p) for p in plants_raw]

        logs_raw = client.get_logs(section_id=section)
        logs = [format_log(l) for l in logs_raw]

        # Build plant_types_db from cached taxonomy
        all_types = client.get_all_plant_types_cached()
        plant_types_db = {}
        for pt in all_types:
            fmt = format_plant_type(pt)
            plant_types_db[fmt["name"]] = fmt

        # KB entries
        kb_entries = []
        if kb_client:
            try:
                kb_result = kb_client.search(section)
                kb_entries = kb_result if isinstance(kb_result, list) else kb_result.get("results", [])
            except Exception:
                pass

        result["facts"] = {
            "total_plants": len(plants),
            "total_species": len(set(p.get("species", "") for p in plants)),
            "plants": [{"species": p.get("species", ""), "count": p.get("inventory_count"), "status": p.get("status")} for p in plants],
            "recent_logs": len(logs),
            "kb_entries": [{"title": e.get("title", ""), "category": e.get("category", "")} for e in kb_entries[:5]],
        }

        # Layer 3: Interpretation
        plant_data = [{"species": p.get("species", ""), "count": p.get("inventory_count") or 0, "strata": p.get("strata", "")} for p in plants]
        log_data = [{"timestamp": l.get("timestamp", "")} for l in logs]

        health = assess_section_health(plant_data, log_data, plant_types_db, has_trees, semantics)
        result["interpretation"] = health

        # Layer 4: Context
        pending = [l for l in logs if l.get("status") == "pending"]
        recent_obs = [l for l in logs if l.get("type") == "observation"][:5]

        # Cross-reference team memory against farmOS logs
        logging_gaps = []
        try:
            memory_client = get_memory_client()
        except (ValueError, Exception):
            memory_client = None
        if memory_client and memory_client.is_connected:
            try:
                memory_result = memory_client.search_memory(section, days=30)
                sessions = memory_result.get("results", []) if isinstance(memory_result, dict) else []
                if sessions:
                    logging_gaps = detect_logging_gaps(sessions, logs, section_filter=section)
            except Exception:
                pass

        result["context"] = {
            "pending_tasks": [{"name": t.get("name", ""), "timestamp": t.get("timestamp", "")} for t in pending],
            "recent_observations": [{"name": o.get("name", ""), "timestamp": o.get("timestamp", ""), "notes": o.get("notes", "")} for o in recent_obs],
            "logging_gaps": [
                {"user": g["user"], "session": g["session_id"],
                 "claimed": g["claimed_change"]["details"],
                 "evidence": g["evidence"]}
                for g in logging_gaps
            ],
        }

        # Gaps
        species_in_section = [p.get("species", "") for p in plants if p.get("species")]
        kb_gaps = detect_knowledge_gaps(species_in_section, kb_entries)
        decision_gaps = detect_decision_gaps(pending, recent_obs)

        gaps = []
        if kb_gaps.get("uncovered_species"):
            gaps.append(f"No KB entries for species: {', '.join(kb_gaps['uncovered_species'][:5])}")
        gaps.extend(decision_gaps)
        if health.get("activity_recency", {}).get("status") == "neglected":
            gaps.append("Section has not been visited in over 60 days")
        if health.get("strata_coverage", {}).get("status") == "poor":
            gaps.append("Poor strata coverage — missing most canopy layers")
        for g in logging_gaps:
            gaps.append(f"INTEGRITY: {g['user']} claimed '{g['claimed_change']['details']}' (session {g['session_id']}) but no matching farmOS log found")

        result["gaps"] = gaps

        # Data integrity gate — if logging gaps exist, flag for human confirmation
        if logging_gaps:
            result["data_integrity"] = {
                "requires_confirmation": True,
                "reason": "Team memory records changes that are not reflected in farmOS. "
                          "The facts shown above may be INCOMPLETE. "
                          "Confirm with the human what actually happened before acting on this data.",
                "discrepancies": [
                    {
                        "who": g["user"],
                        "session": g["session_id"],
                        "claimed": g["claimed_change"]["details"],
                        "type": g["claimed_change"].get("type", "unknown"),
                    }
                    for g in logging_gaps
                ],
            }
        else:
            result["data_integrity"] = {"requires_confirmation": False}

    # ── Subject (species) mode ────────────────────────────────
    elif subject:
        result["query"] = {"type": "species", "name": subject}

        # Layer 1: Ontology
        result["ontology"] = {
            "entity_type": "Species",
            "canonical_source": "farmOS taxonomy_term/plant_type",
        }

        # Layer 2: Facts — all plants of this species
        plants_raw = client.get_plant_assets(species=subject)
        plants = [format_plant_asset(p) for p in plants_raw]

        # Species metadata
        all_types = client.get_all_plant_types_cached()
        species_meta = None
        for pt in all_types:
            fmt = format_plant_type(pt)
            if fmt["name"].lower() == subject.lower():
                species_meta = fmt
                break

        # KB entries
        kb_entries = []
        if kb_client:
            try:
                kb_result = kb_client.search(subject)
                kb_entries = kb_result if isinstance(kb_result, list) else kb_result.get("results", [])
            except Exception:
                pass

        # Group plants by section
        sections = {}
        for p in plants:
            sec = p.get("section", "unknown")
            if sec not in sections:
                sections[sec] = {"count": 0, "plants": []}
            count = p.get("inventory_count") or 0
            sections[sec]["count"] += count
            sections[sec]["plants"].append(p.get("name", ""))

        result["facts"] = {
            "total_plants": len(plants),
            "total_count": sum(s["count"] for s in sections.values()),
            "sections": {k: v["count"] for k, v in sections.items()},
            "distribution": len(sections),
            "species_metadata": species_meta,
            "kb_entries": [{"title": e.get("title", ""), "category": e.get("category", "")} for e in kb_entries[:5]],
        }

        # Layer 3: Interpretation
        result["interpretation"] = {
            "strata": species_meta.get("strata", "unknown") if species_meta else "unknown",
            "succession": species_meta.get("succession_stage", "unknown") if species_meta else "unknown",
            "functions": species_meta.get("plant_functions", "") if species_meta else "",
            "distribution_sections": len(sections),
        }

        # Layer 4: Context
        result["context"] = {
            "kb_coverage": len(kb_entries) > 0,
        }

        # Gaps
        gaps = []
        if not kb_entries:
            gaps.append(f"No Knowledge Base entries for {subject}")
        if not species_meta:
            gaps.append(f"{subject} not found in plant type taxonomy")
        result["gaps"] = gaps

    # ── Topic (domain) mode ───────────────────────────────────
    elif topic:
        topic_lower = topic.lower()
        result["query"] = {"type": "topic", "name": topic_lower}

        topic_config = TOPIC_FARMOS_MAP.get(topic_lower, {})
        prefix = topic_config.get("section_prefix")

        result["ontology"] = {
            "entity_type": "farm_domain",
            "topic": topic_lower,
            "section_prefix": prefix,
        }

        # Layer 2: Facts
        plants = []
        sections_data = {}
        if prefix:
            # Get inventory for all sections with this prefix
            section_assets = client.get_plant_assets(section_id=prefix)
            plants = [format_plant_asset(p) for p in section_assets]

            for p in plants:
                sec = p.get("section", "unknown")
                if sec not in sections_data:
                    sections_data[sec] = {"count": 0, "species": set()}
                count = p.get("inventory_count") or 0
                sections_data[sec]["count"] += count
                sections_data[sec]["species"].add(p.get("species", ""))

        # KB entries for this topic
        kb_entries = []
        if kb_client:
            try:
                kb_result = kb_client.search(topic_lower)
                kb_entries = kb_result if isinstance(kb_result, list) else kb_result.get("results", [])
            except Exception:
                pass

        result["facts"] = {
            "total_plants": len(plants),
            "total_sections": len(sections_data),
            "sections_summary": {k: v["count"] for k, v in sections_data.items()},
            "total_species": len(set(p.get("species", "") for p in plants)),
            "kb_entries": [{"title": e.get("title", ""), "category": e.get("category", "")} for e in kb_entries[:10]],
        }

        # Layer 3: Interpretation — transplant readiness for nursery
        if topic_lower == "nursery":
            all_types = client.get_all_plant_types_cached()
            plant_types_db = {}
            for pt in all_types:
                fmt = format_plant_type(pt)
                plant_types_db[fmt["name"]] = fmt

            nursery_plants = [
                {"species": p.get("species", ""), "planted_date": p.get("planted_date", ""),
                 "name": p.get("name", ""), "count": p.get("inventory_count") or 0,
                 "section": p.get("section", "")}
                for p in plants
            ]
            ready = find_transplant_ready(nursery_plants, plant_types_db, semantics)
            result["interpretation"] = {
                "transplant_ready": [{"species": r["species"], "section": r["section"],
                                      "count": r["count"], "days_overdue": r["days_overdue"]} for r in ready[:10]],
                "total_transplant_ready": len(ready),
            }
        else:
            result["interpretation"] = {}

        # Layer 4: Context — pending tasks
        result["context"] = {"kb_entry_count": len(kb_entries)}

        # Gaps
        gaps = []
        if not kb_entries:
            gaps.append(f"No Knowledge Base entries for topic '{topic_lower}'")
        result["gaps"] = gaps

    return json.dumps(result, indent=2, default=str)


# ── Site Management ────────────────────────────────────────────────


@mcp.tool
def regenerate_pages(push_to_github: bool = True) -> str:
    """Regenerate QR landing pages from live farmOS data and optionally push to GitHub Pages.

    Runs the full pipeline:
    1. Export farmOS data → sections.json (enriched with inventory counts, log history)
    2. Generate HTML pages from sections.json + plant_types.csv
    3. Git commit and push to trigger GitHub Pages deployment

    This should be run after importing observations or making changes in farmOS
    to update the public QR landing pages.

    Args:
        push_to_github: If True (default), commit and push changes to GitHub Pages.
                       Set to False for a dry-run that generates but doesn't deploy.

    Returns:
        Status of each pipeline step.
    """
    steps = []

    # Step 1: Export farmOS → sections.json
    export_args = [
        "--sections-json",
        "--output", _SECTIONS_JSON,
        "--existing", _SECTIONS_JSON,
        "--plants", _PLANT_TYPES_CSV,
    ]
    result = _run_script("export_farmos.py", export_args)
    steps.append({
        "step": "export_farmos",
        "success": result["returncode"] == 0,
        "output": result["stdout"].strip() if result["returncode"] == 0 else result["stderr"].strip(),
    })
    if result["returncode"] != 0:
        return json.dumps({"status": "failed", "failed_at": "export_farmos", "steps": steps}, indent=2)

    # Step 2: Generate HTML pages
    generate_args = [
        "--data", _SECTIONS_JSON,
        "--plants", _PLANT_TYPES_CSV,
        "--observe-endpoint", _OBSERVE_ENDPOINT,
    ]
    result = _run_script("generate_site.py", generate_args)
    steps.append({
        "step": "generate_site",
        "success": result["returncode"] == 0,
        "output": result["stdout"].strip() if result["returncode"] == 0 else result["stderr"].strip(),
    })
    if result["returncode"] != 0:
        return json.dumps({"status": "failed", "failed_at": "generate_site", "steps": steps}, indent=2)

    # Step 3: Git commit and push (optional)
    if push_to_github:
        try:
            # Check if there are changes to commit
            status = subprocess.run(
                ["git", "status", "--porcelain", "site/public/"],
                capture_output=True, text=True, cwd=_PROJECT_ROOT,
            )
            if not status.stdout.strip():
                steps.append({
                    "step": "git_push",
                    "success": True,
                    "output": "No changes to deploy — pages are already up to date.",
                })
            else:
                changed_files = len(status.stdout.strip().split("\n"))
                # Stage, commit, push
                subprocess.run(["git", "add", "site/public/"], cwd=_PROJECT_ROOT, check=True)
                subprocess.run(
                    ["git", "commit", "-m",
                     f"Regenerate QR landing pages from farmOS ({changed_files} files updated)"],
                    cwd=_PROJECT_ROOT, check=True,
                    capture_output=True,
                )
                push_result = subprocess.run(
                    ["git", "push"],
                    capture_output=True, text=True, cwd=_PROJECT_ROOT, timeout=60,
                )
                steps.append({
                    "step": "git_push",
                    "success": push_result.returncode == 0,
                    "output": f"Pushed {changed_files} updated files to GitHub Pages."
                             if push_result.returncode == 0
                             else push_result.stderr.strip(),
                })
        except Exception as e:
            steps.append({
                "step": "git_push",
                "success": False,
                "output": str(e),
            })

    all_success = all(s["success"] for s in steps)
    return json.dumps({
        "status": "success" if all_success else "partial",
        "steps": steps,
        "pages_url": "https://agnesfa.github.io/firefly-farm-ai/" if all_success and push_to_github else None,
    }, indent=2)


# ═══════════════════════════════════════════════════════════════
# TOOLS — Team Memory (shared intelligence across users)
# ═══════════════════════════════════════════════════════════════


@mcp.tool
def write_session_summary(
    user: str,
    topics: str = "",
    decisions: str = "",
    farmos_changes: str = "",
    questions: str = "",
    summary: str = "",
    skip: bool = False,
) -> str:
    """Write a session summary to the shared Team Memory.

    Call this at the end of significant sessions to share what was discussed
    and decided with the rest of the team.

    Args:
        user: Who this summary is from (e.g., "Claire", "Agnes", "Olivier").
        topics: Comma-separated topic keywords (e.g., "compost, P2R3, pigeon pea").
        decisions: Key decisions made in this session.
        farmos_changes: JSON string of farmOS changes made, e.g., '[{"type":"observation","id":"uuid","name":"..."}]'.
        questions: Open questions or things to follow up on.
        summary: Free-text session summary.
        skip: If True, mark as private/skipped (not shared with team). Default False.
    """
    try:
        mem_client = get_memory_client()
    except ValueError as e:
        return json.dumps({"error": str(e), "hint": "MEMORY_ENDPOINT env var not set"})

    # Build interaction stamp
    stamp = build_mcp_stamp(
        action="created", target="session_summary",
        initiator=user,
        executor="apps_script",
    )
    stamped_summary = append_stamp(summary, stamp)

    try:
        result = mem_client.write_summary(
            user=user,
            topics=topics,
            decisions=decisions,
            farmos_changes=farmos_changes,
            questions=questions,
            summary=stamped_summary,
            skip=skip,
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to write summary: {e}"})


@mcp.tool
def read_team_activity(
    days: int = 7,
    user: Optional[str] = None,
    limit: int = 20,
    only_fresh_for: Optional[str] = None,
) -> str:
    """Read recent team session summaries from shared memory.

    Call this at the start of sessions to see what the team has been doing.

    Args:
        days: How many days back to look (default 7).
        user: Filter by team member name (optional).
        limit: Max results to return (default 20).
        only_fresh_for: If set, exclude entries already acknowledged by this
            user. Use at session start to see only new updates (e.g., "Claire").
    """
    try:
        mem_client = get_memory_client()
    except ValueError as e:
        return json.dumps({"error": str(e), "hint": "MEMORY_ENDPOINT env var not set"})

    try:
        result = mem_client.read_activity(
            days=days, user=user, limit=limit, only_fresh_for=only_fresh_for
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to read team activity: {e}"})


@mcp.tool
def search_team_memory(
    query: str,
    days: int = 30,
) -> str:
    """Search team memory for matching session summaries.

    Searches across topics, decisions, questions, and summary text.

    Args:
        query: Text to search for (e.g., "compost", "pigeon pea", "nursery").
        days: How many days back to search (default 30).
    """
    try:
        mem_client = get_memory_client()
    except ValueError as e:
        return json.dumps({"error": str(e), "hint": "MEMORY_ENDPOINT env var not set"})

    try:
        result = mem_client.search_memory(query=query, days=days)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to search team memory: {e}"})


@mcp.tool
def acknowledge_memory(
    summary_id: str,
    user: str,
) -> str:
    """Mark a team memory entry as acknowledged (read and processed).

    Call this after reading and acting on a team memory entry so it won't
    appear again in fresh-only queries for this user.

    Args:
        summary_id: The summary/entry ID to acknowledge.
        user: Who is acknowledging (e.g., "Claire", "Agnes", "James").
    """
    try:
        mem_client = get_memory_client()
    except ValueError as e:
        return json.dumps({"error": str(e), "hint": "MEMORY_ENDPOINT env var not set"})

    try:
        result = mem_client.acknowledge_memory(summary_id=summary_id, user=user)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to acknowledge memory: {e}"})


# ═══════════════════════════════════════════════════════════════
# TOOLS — Plant type taxonomy management
# ═══════════════════════════════════════════════════════════════


@mcp.tool
def add_plant_type(
    farmos_name: str,
    botanical_name: Optional[str] = None,
    strata: Optional[str] = None,
    succession_stage: Optional[str] = None,
    plant_functions: Optional[str] = None,
    crop_family: Optional[str] = None,
    origin: Optional[str] = None,
    description: Optional[str] = None,
    lifespan_years: Optional[str] = None,
    lifecycle_years: Optional[str] = None,
    source: Optional[str] = None,
    maturity_days: Optional[int] = None,
    transplant_days: Optional[int] = None,
) -> str:
    """Add a new plant type to the farmOS taxonomy.

    Creates a plant_type taxonomy term with syntropic agriculture metadata
    embedded in the description.

    Args:
        farmos_name: The canonical name (e.g., "Tomato (Marmande)", "Pigeon Pea"). Must not already exist.
        botanical_name: Scientific name (e.g., "Cajanus cajan").
        strata: Height layer — emergent, high, medium, or low.
        succession_stage: Temporal role — pioneer, secondary, or climax.
        plant_functions: Comma-separated function tags (e.g., "nitrogen_fixer,edible_seed,biomass_producer").
        crop_family: Botanical family (e.g., "Fabaceae").
        origin: Geographic origin (e.g., "India/Africa").
        description: Free-text description of the plant.
        lifespan_years: How long the plant lives (e.g., "5-10", "20+").
        lifecycle_years: Production/harvest cycle (e.g., "0.5", "3-5").
        source: Where seeds/plants come from (e.g., "EDEN Seeds", "Daleys Fruit Nursery").
        maturity_days: Days to maturity (numeric, optional).
        transplant_days: Days from seed to transplant (numeric, optional).
    """
    client = get_client()

    # Check if already exists
    existing = client.fetch_by_name("taxonomy_term/plant_type", farmos_name)
    if existing:
        return json.dumps({
            "error": f"Plant type '{farmos_name}' already exists in farmOS.",
            "existing_id": existing[0]["id"],
        })

    # Build description with syntropic metadata
    fields = {
        "description": description or "",
        "botanical_name": botanical_name,
        "lifecycle_years": lifecycle_years,
        "strata": strata,
        "succession_stage": succession_stage,
        "plant_functions": plant_functions,
        "crop_family": crop_family,
        "lifespan_years": lifespan_years,
        "source": source,
    }
    full_description = build_plant_type_description(fields)

    # Build interaction stamp
    stamp = build_mcp_stamp(
        action="created", target="plant_type",
        related_entities=[farmos_name],
    )
    full_description = append_stamp(full_description, stamp)

    try:
        uuid = client.create_plant_type(
            name=farmos_name,
            description=full_description,
            maturity_days=maturity_days,
            transplant_days=transplant_days,
        )
        # Clear cache so new type is immediately available
        client._plant_type_cache.pop(farmos_name, None)

        # Sync to Google Sheet (if configured)
        sheet_status = "not_configured"
        pt_client = get_plant_types_client()
        if pt_client:
            try:
                # Derive common_name and variety from farmos_name
                common_name = farmos_name
                variety = ""
                if " (" in farmos_name and farmos_name.endswith(")"):
                    common_name = farmos_name[:farmos_name.rindex(" (")]
                    variety = farmos_name[farmos_name.rindex(" (") + 2:-1]

                sheet_fields = {
                    "common_name": common_name,
                    "variety": variety,
                    "farmos_name": farmos_name,
                    "botanical_name": botanical_name or "",
                    "crop_family": crop_family or "",
                    "origin": origin or "",
                    "description": description or "",
                    "lifespan_years": lifespan_years or "",
                    "lifecycle_years": lifecycle_years or "",
                    "maturity_days": str(maturity_days) if maturity_days else "",
                    "strata": strata or "",
                    "succession_stage": succession_stage or "",
                    "plant_functions": plant_functions or "",
                    "transplant_days": str(transplant_days) if transplant_days else "",
                    "source": source or "",
                }
                result = pt_client.add(sheet_fields)
                sheet_status = "synced" if result.get("success") else result.get("error", "failed")
            except Exception as se:
                sheet_status = f"sync_error: {se}"

        return json.dumps({
            "status": "created",
            "id": uuid,
            "name": farmos_name,
            "strata": strata,
            "succession_stage": succession_stage,
            "sheet_sync": sheet_status,
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to create plant type: {e}"})


@mcp.tool
def update_plant_type(
    farmos_name: str,
    botanical_name: Optional[str] = None,
    strata: Optional[str] = None,
    succession_stage: Optional[str] = None,
    plant_functions: Optional[str] = None,
    crop_family: Optional[str] = None,
    origin: Optional[str] = None,
    description: Optional[str] = None,
    lifespan_years: Optional[str] = None,
    lifecycle_years: Optional[str] = None,
    source: Optional[str] = None,
    maturity_days: Optional[int] = None,
    transplant_days: Optional[int] = None,
) -> str:
    """Update an existing plant type in the farmOS taxonomy.

    Fetches the existing term, merges in the provided updates,
    rebuilds the description with syntropic metadata, and patches.

    Args:
        farmos_name: The exact name of the plant type to update. Must already exist.
        botanical_name: New scientific name (optional).
        strata: New height layer (optional).
        succession_stage: New temporal role (optional).
        plant_functions: New function tags, comma-separated (optional).
        crop_family: New botanical family (optional).
        origin: New geographic origin (optional).
        description: New free-text description (optional).
        lifespan_years: New lifespan (optional).
        lifecycle_years: New lifecycle (optional).
        source: New source (optional).
        maturity_days: New days to maturity (optional).
        transplant_days: New days to transplant (optional).
    """
    client = get_client()

    # Find existing term
    existing = client.fetch_by_name("taxonomy_term/plant_type", farmos_name)
    if not existing:
        return json.dumps({"error": f"Plant type '{farmos_name}' not found in farmOS."})

    term = existing[0]
    uuid = term["id"]
    attrs = term.get("attributes", {})

    # Parse existing metadata from description
    existing_desc = attrs.get("description", {})
    if isinstance(existing_desc, dict):
        existing_text = existing_desc.get("value", "")
    else:
        existing_text = str(existing_desc) if existing_desc else ""

    current_meta = parse_plant_type_metadata(existing_text)

    # Extract the plain description (before the --- separator)
    plain_desc = existing_text.split("\n\n---\n")[0] if "\n\n---\n" in existing_text else existing_text

    # Merge updates into current metadata
    fields = {
        "description": description if description is not None else plain_desc,
        "botanical_name": botanical_name or current_meta.get("botanical_name"),
        "lifecycle_years": lifecycle_years or current_meta.get("lifecycle_years"),
        "strata": strata or current_meta.get("strata"),
        "succession_stage": succession_stage or current_meta.get("succession_stage"),
        "plant_functions": plant_functions or current_meta.get("plant_functions"),
        "crop_family": crop_family or current_meta.get("crop_family"),
        "lifespan_years": lifespan_years or current_meta.get("lifespan_years"),
        "source": source or current_meta.get("source"),
    }
    new_description = build_plant_type_description(fields)

    # Build interaction stamp
    stamp = build_mcp_stamp(
        action="updated", target="plant_type",
        related_entities=[farmos_name],
    )
    new_description = append_stamp(new_description, stamp)

    # Build PATCH attributes
    patch_attrs = {
        "description": {"value": new_description, "format": "default"},
    }
    if maturity_days is not None:
        patch_attrs["maturity_days"] = maturity_days
    if transplant_days is not None:
        patch_attrs["transplant_days"] = transplant_days

    try:
        client.update_plant_type(uuid, patch_attrs)
        # Clear cache
        client._plant_type_cache.pop(farmos_name, None)

        updated_fields = [k for k, v in {
            "botanical_name": botanical_name, "strata": strata,
            "succession_stage": succession_stage, "plant_functions": plant_functions,
            "crop_family": crop_family, "description": description,
            "lifespan_years": lifespan_years, "lifecycle_years": lifecycle_years,
            "source": source, "maturity_days": maturity_days,
            "transplant_days": transplant_days,
        }.items() if v is not None]

        # Sync to Google Sheet (if configured)
        sheet_status = "not_configured"
        pt_client = get_plant_types_client()
        if pt_client:
            try:
                sheet_fields = {}
                if botanical_name is not None:
                    sheet_fields["botanical_name"] = botanical_name
                if strata is not None:
                    sheet_fields["strata"] = strata
                if succession_stage is not None:
                    sheet_fields["succession_stage"] = succession_stage
                if plant_functions is not None:
                    sheet_fields["plant_functions"] = plant_functions
                if crop_family is not None:
                    sheet_fields["crop_family"] = crop_family
                if origin is not None:
                    sheet_fields["origin"] = origin
                if description is not None:
                    sheet_fields["description"] = description
                if lifespan_years is not None:
                    sheet_fields["lifespan_years"] = lifespan_years
                if lifecycle_years is not None:
                    sheet_fields["lifecycle_years"] = lifecycle_years
                if source is not None:
                    sheet_fields["source"] = source
                if maturity_days is not None:
                    sheet_fields["maturity_days"] = str(maturity_days)
                if transplant_days is not None:
                    sheet_fields["transplant_days"] = str(transplant_days)

                if sheet_fields:
                    result = pt_client.update(farmos_name, sheet_fields)
                    sheet_status = "synced" if result.get("success") else result.get("error", "failed")
                else:
                    sheet_status = "no_sheet_fields"
            except Exception as se:
                sheet_status = f"sync_error: {se}"

        return json.dumps({
            "status": "updated",
            "id": uuid,
            "name": farmos_name,
            "updated_fields": updated_fields,
            "sheet_sync": sheet_status,
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to update plant type: {e}"})


@mcp.tool
def reconcile_plant_types() -> str:
    """Compare plant types between the Google Sheet and farmOS taxonomy.

    Detects drift: strata mismatches, missing entries, metadata differences.
    Returns a report of discrepancies that need to be resolved.

    Requires PLANT_TYPES_ENDPOINT to be configured.
    """
    pt_client = get_plant_types_client()
    if not pt_client:
        return json.dumps({
            "error": "PLANT_TYPES_ENDPOINT not configured. Cannot reconcile without the Google Sheet."
        })

    client = get_client()

    # Fetch sheet data
    try:
        sheet_data = pt_client.get_reconcile_data()
        if not sheet_data.get("success"):
            return json.dumps({"error": f"Failed to fetch sheet data: {sheet_data.get('error')}"})
    except Exception as e:
        return json.dumps({"error": f"Failed to connect to Plant Types sheet: {e}"})

    sheet_types = {pt["farmos_name"]: pt for pt in sheet_data.get("plant_types", [])}

    # Fetch all plant types from farmOS
    try:
        farmos_types_raw = client.fetch_all_paginated("taxonomy_term/plant_type")
    except Exception as e:
        return json.dumps({"error": f"Failed to fetch farmOS taxonomy: {e}"})

    # Parse farmOS types into comparable format
    farmos_types = {}
    for term in farmos_types_raw:
        attrs = term.get("attributes", {})
        name = attrs.get("name", "")
        if name.startswith("[ARCHIVED]"):
            continue

        desc = attrs.get("description", {})
        desc_text = desc.get("value", "") if isinstance(desc, dict) else str(desc or "")
        meta = parse_plant_type_metadata(desc_text)

        farmos_types[name] = {
            "farmos_name": name,
            "strata": meta.get("strata", ""),
            "succession_stage": meta.get("succession_stage", ""),
            "botanical_name": meta.get("botanical_name", ""),
            "crop_family": meta.get("crop_family", ""),
            "plant_functions": meta.get("plant_functions", ""),
        }

    # Compare
    mismatches = []
    in_sheet_not_farmos = []
    in_farmos_not_sheet = []

    for name, sheet_entry in sheet_types.items():
        if name not in farmos_types:
            in_sheet_not_farmos.append(name)
            continue

        farmos_entry = farmos_types[name]
        diffs = []
        for field in ["strata", "succession_stage", "botanical_name", "crop_family"]:
            sv = (sheet_entry.get(field) or "").strip().lower()
            fv = (farmos_entry.get(field) or "").strip().lower()
            if sv and fv and sv != fv:
                diffs.append({
                    "field": field,
                    "sheet": sheet_entry.get(field, ""),
                    "farmos": farmos_entry.get(field, ""),
                })
        if diffs:
            mismatches.append({"farmos_name": name, "differences": diffs})

    for name in farmos_types:
        if name not in sheet_types:
            in_farmos_not_sheet.append(name)

    report = {
        "sheet_count": len(sheet_types),
        "farmos_count": len(farmos_types),
        "mismatches": mismatches,
        "mismatch_count": len(mismatches),
        "in_sheet_not_farmos": in_sheet_not_farmos,
        "in_farmos_not_sheet": in_farmos_not_sheet,
        "status": "clean" if not mismatches and not in_sheet_not_farmos and not in_farmos_not_sheet else "drift_detected",
    }

    return json.dumps(report, indent=2)


# ═══════════════════════════════════════════════════════════════
# TOOLS — Knowledge Base (shared farm knowledge library)
# ═══════════════════════════════════════════════════════════════


def _summarize_kb_entries(entries: list) -> list:
    """Trim KB entries to summary: entry_id, title, category, topics, tags, author, content preview."""
    summary_keys = ("entry_id", "title", "category", "topics", "tags", "author")
    summarized = []
    for entry in entries:
        item = {k: entry.get(k, "") for k in summary_keys}
        content = entry.get("content", "")
        item["content_preview"] = content[:100] + ("..." if len(content) > 100 else "")
        summarized.append(item)
    return summarized


@mcp.tool
def search_knowledge(
    query: str,
    category: Optional[str] = None,
    topics: Optional[str] = None,
    summary_only: bool = False,
) -> str:
    """Search the farm knowledge base for articles, tutorials, guides, and SOPs.

    Searches across titles, content, tags, related plants, and authors.
    Use this to find farm practices, syntropic agriculture guides, composting
    methods, pest management strategies, or any documented farm knowledge.

    Args:
        query: Text to search for (e.g., "pigeon pea", "frost damage", "composting").
        category: Optional category filter (e.g., "syntropic", "composting",
                  "irrigation", "nursery", "pests", "harvest", "equipment", "general").
        topics: Optional farm domain filter (e.g., "nursery", "compost", "syntropic").
                Valid topics: nursery, compost, irrigation, syntropic, seeds,
                harvest, paddock, equipment, cooking, infrastructure, camp.
        summary_only: If true, return only entry_id, title, category, topics, tags,
                      author, and first 100 chars of content. Default false.
    """
    kb_client = get_knowledge_client()
    if not kb_client:
        return json.dumps({
            "error": "Knowledge base not available",
            "hint": "KNOWLEDGE_ENDPOINT env var not configured",
        })

    try:
        result = kb_client.search(query=query, category=category, topics=topics)
        if summary_only and result.get("results"):
            result["results"] = _summarize_kb_entries(result["results"])
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Knowledge search failed: {e}"})


@mcp.tool
def list_knowledge(
    category: Optional[str] = None,
    limit: int = 20,
    topics: Optional[str] = None,
    summary_only: bool = False,
) -> str:
    """List knowledge base entries, optionally filtered by category and/or topics.

    Use this to browse the farm knowledge library or see what's available
    in a specific category.

    Args:
        category: Optional category filter (e.g., "syntropic", "composting").
        limit: Max entries to return (default 20).
        topics: Optional farm domain filter (e.g., "nursery", "compost").
                Valid topics: nursery, compost, irrigation, syntropic, seeds,
                harvest, paddock, equipment, cooking, infrastructure, camp.
        summary_only: If true, return only entry_id, title, category, topics, tags,
                      author, and first 100 chars of content. Default false.
    """
    kb_client = get_knowledge_client()
    if not kb_client:
        return json.dumps({
            "error": "Knowledge base not available",
            "hint": "KNOWLEDGE_ENDPOINT env var not configured",
        })

    try:
        result = kb_client.list_entries(category=category, limit=limit, topics=topics)
        if summary_only and result.get("entries"):
            result["entries"] = _summarize_kb_entries(result["entries"])
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to list knowledge entries: {e}"})


@mcp.tool
def add_knowledge(
    title: str,
    content: str,
    category: str,
    author: str = "",
    tags: str = "",
    source_type: str = "guide",
    related_plants: str = "",
    related_sections: str = "",
    media_links: str = "",
    topics: str = "",
) -> str:
    """Add a new entry to the farm knowledge base.

    Use this to document farming practices, field learnings, tutorials,
    composting methods, pest solutions, or any knowledge that should be
    preserved and shared with the team and future workers.

    Args:
        title: Article/guide title (e.g., "Pigeon Pea Chop-and-Drop Technique").
        content: Full text content of the knowledge entry.
        category: Category tag — one of: syntropic, composting, irrigation,
                  nursery, pests, harvest, equipment, general.
        author: Who wrote/contributed this (e.g., "Claire", "Olivier").
        tags: Comma-separated search tags (e.g., "nitrogen_fixer,biomass,pioneer").
        source_type: Type of entry — tutorial, sop, guide, observation, recipe, reference, source-material.
        related_plants: Comma-separated farmos_names of related plant types
                        (e.g., "Pigeon Pea,Comfrey,Sweet Potato").
        related_sections: Comma-separated section IDs (e.g., "P2R3.15-21,P2R4.20-30").
        media_links: Comma-separated Google Drive file IDs or URLs for
                     photos, PDFs, or audio files related to this entry.
        topics: Comma-separated farm domain topics (e.g., "nursery,propagation").
                Valid topics: nursery, compost, irrigation, syntropic, seeds,
                harvest, paddock, equipment, cooking, infrastructure, camp.
    """
    kb_client = get_knowledge_client()
    if not kb_client:
        return json.dumps({
            "error": "Knowledge base not available",
            "hint": "KNOWLEDGE_ENDPOINT env var not configured",
        })

    # Build interaction stamp
    stamp = build_mcp_stamp(
        action="created", target="knowledge",
        initiator=author or None,
        executor="apps_script",
    )
    stamped_content = append_stamp(content, stamp)

    try:
        result = kb_client.add(fields={
            "title": title,
            "content": stamped_content,
            "category": category,
            "author": author,
            "tags": tags,
            "topics": topics,
            "source_type": source_type,
            "related_plants": related_plants,
            "related_sections": related_sections,
            "media_links": media_links,
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to add knowledge entry: {e}"})


@mcp.tool
def update_knowledge(
    entry_id: str,
    title: Optional[str] = None,
    content: Optional[str] = None,
    category: Optional[str] = None,
    tags: Optional[str] = None,
    topics: Optional[str] = None,
    related_plants: Optional[str] = None,
    related_sections: Optional[str] = None,
    media_links: Optional[str] = None,
) -> str:
    """Update an existing knowledge base entry.

    Only the fields you provide will be updated — others are preserved.

    Args:
        entry_id: The UUID of the entry to update (from search_knowledge or list_knowledge).
        title: New title (optional).
        content: New/updated content (optional).
        category: New category (optional).
        tags: New comma-separated tags (optional).
        topics: New comma-separated farm domain topics (optional).
                Valid topics: nursery, compost, irrigation, syntropic, seeds,
                harvest, paddock, equipment, cooking, infrastructure, camp.
        related_plants: New related plant types (optional).
        related_sections: New related sections (optional).
        media_links: New media links (optional).
    """
    kb_client = get_knowledge_client()
    if not kb_client:
        return json.dumps({
            "error": "Knowledge base not available",
            "hint": "KNOWLEDGE_ENDPOINT env var not configured",
        })

    fields = {}
    for key, val in {
        "title": title, "content": content, "category": category,
        "tags": tags, "topics": topics, "related_plants": related_plants,
        "related_sections": related_sections, "media_links": media_links,
    }.items():
        if val is not None:
            fields[key] = val

    if not fields:
        return json.dumps({"error": "No fields to update"})

    # Build interaction stamp — append to content if content is being updated
    stamp = build_mcp_stamp(
        action="updated", target="knowledge",
        executor="apps_script",
    )
    if "content" in fields:
        fields["content"] = append_stamp(fields["content"], stamp)

    try:
        result = kb_client.update(entry_id=entry_id, fields=fields)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to update knowledge entry: {e}"})


# ═══════════════════════════════════════════════════════════════
# SYSTEM HEALTH — Growth maturity & scale triggers
# ═══════════════════════════════════════════════════════════════


@mcp.tool
def system_health() -> str:
    """Assess farm maturity across four dimensions: Farm (biological),
    System (technical), Team (human), and Data (quality). Returns current
    growth stage per dimension, metric scores, and active scale triggers
    with recommended build actions.

    All thresholds and interpretation rules are defined in
    knowledge/farm_growth.yaml (human-reviewable, not hardcoded).
    """
    from semantics import (
        assess_farm_maturity,
        assess_system_maturity,
        assess_team_maturity,
        assess_data_maturity,
        load_growth_config,
        assess_section_health,
        load_semantics,
    )
    from concurrent.futures import ThreadPoolExecutor
    from helpers import parse_plant_type_metadata

    config = load_growth_config()
    client = get_client()
    semantics_config = load_semantics()

    result = {"dimensions": {}, "scale_triggers": [], "assumptions": []}

    # Farm/System/Team dimensions are independent — run in parallel via threads.
    # Within Farm, the 20 section assessments also run in parallel.
    # The farmOS client is sync/blocking HTTP, so ThreadPoolExecutor unblocks
    # the I/O wait. Turns ~40 sequential roundtrips into a couple of parallel waves.

    def _assess_one_section(sec, plant_types_db):
        sec_name = sec.get("attributes", {}).get("name", "")
        with ThreadPoolExecutor(max_workers=2) as inner:
            plants_fut = inner.submit(client.get_plant_assets, section_id=sec_name)
            logs_fut = inner.submit(client.get_logs, section_id=sec_name)
            sec_plants_raw = plants_fut.result()
            sec_logs_raw = logs_fut.result()
        sec_plants = [format_plant_asset(p) for p in sec_plants_raw]
        sec_logs = [format_log(l) for l in sec_logs_raw]
        health = assess_section_health(
            sec_plants, sec_logs, plant_types_db, has_trees=True,
            semantics=semantics_config,
        )
        return {
            "section": sec_name,
            "strata_score": health.get("strata", {}).get("score", 0),
            "survival_rate": None,
            "status": health.get("overall_status", "unknown"),
        }

    def _farm_dimension():
        with ThreadPoolExecutor(max_workers=3) as ex:
            plants_fut = ex.submit(client.fetch_all_paginated, "asset/plant", filters={"status": "active"})
            types_fut = ex.submit(client.get_all_plant_types_cached)
            sections_fut = ex.submit(client.get_section_assets)
            all_plants = plants_fut.result()
            all_types = types_fut.result()
            sections = sections_fut.result()

        active_plant_count = len(all_plants)

        plant_types_db = {}
        for t in all_types:
            name = t.get("attributes", {}).get("name", "")
            desc = t.get("attributes", {}).get("description", {})
            desc_text = desc.get("value", "") if isinstance(desc, dict) else str(desc)
            plant_types_db[name] = parse_plant_type_metadata(desc_text)

        sampled = sections[:20]
        with ThreadPoolExecutor(max_workers=10) as ex:
            section_scores = list(ex.map(lambda s: _assess_one_section(s, plant_types_db), sampled))

        farm_data = {
            "active_plants": active_plant_count,
            "section_health_scores": section_scores,
        }
        farm_result = assess_farm_maturity(farm_data, config)
        farm_result["sampled_sections"] = len(section_scores)
        farm_result["total_sections"] = len(sections)
        return farm_result, active_plant_count, all_plants, all_types

    def _system_dimension(active_plant_count):
        total_entities = active_plant_count + 1200  # rough estimate for logs + other assets

        def _drift():
            try:
                pt_client = get_plant_types_client()
                drift_result = pt_client.reconcile()
                return drift_result.get("mismatch_count", 0) if isinstance(drift_result, dict) else 0
            except Exception:
                return None

        def _backlog():
            try:
                obs_client = get_observe_client()
                pending = obs_client.list_observations(status="pending")
                return len(pending) if isinstance(pending, list) else 0
            except Exception:
                return None

        with ThreadPoolExecutor(max_workers=2) as ex:
            drift_count = ex.submit(_drift).result()
            backlog_count = ex.submit(_backlog).result()

        system_data = {
            "total_entities": total_entities,
            "plant_type_drift": drift_count,
            "observation_backlog": backlog_count,
        }
        return assess_system_maturity(system_data, config)

    def _team_dimension():
        mem_client = get_memory_client()

        def _kb():
            try:
                kb_client = get_knowledge_client()
                # Apps Script wraps results: {success, entries: [...], count, total}
                resp = kb_client.list_entries(limit=200)
                if isinstance(resp, dict):
                    return resp.get("total") or len(resp.get("entries") or [])
                if isinstance(resp, list):
                    return len(resp)
                return None
            except Exception:
                return None

        with ThreadPoolExecutor(max_workers=2) as ex:
            activity_fut = ex.submit(mem_client.read_activity, days=7)
            kb_fut = ex.submit(_kb)
            recent_activity = activity_fut.result()
            kb_count = kb_fut.result()

        # Apps Script wraps results: {success, summaries: [...], count}
        if isinstance(recent_activity, dict):
            summaries = recent_activity.get("summaries") or []
        elif isinstance(recent_activity, list):
            summaries = recent_activity
        else:
            summaries = []

        distinct_users = len({
            entry.get("user", "") for entry in summaries if entry.get("user")
        })
        memory_velocity = len(summaries)

        team_data = {
            "active_users_weekly": distinct_users,
            "team_memory_velocity": memory_velocity,
            "kb_entry_count": kb_count,
        }
        return assess_team_maturity(team_data, config)

    # Run Farm first (System/Data depend on its active_plant_count/types),
    # then System + Team + Data in parallel.
    active_plant_count = 0
    all_plants = []
    all_types = []
    try:
        farm_result, active_plant_count, all_plants, all_types = _farm_dimension()
        result["dimensions"]["farm"] = farm_result
        result["scale_triggers"].extend(farm_result.get("scale_triggers", []))
    except Exception as e:
        result["dimensions"]["farm"] = {"error": str(e)}

    def _data_dimension(all_plants, all_types):
        from interaction_stamp import count_stamps_in_logs

        # species_photo_coverage: species with TIER 1 (farm-sourced) photo only.
        # Tier 2 stock photos (wikimedia_stock) don't count — they're display aids.
        # Photo source tracked in plant_type description metadata (photo_source field).
        formatted_plants = [format_plant_asset(p) for p in all_plants]
        distinct_species = set()
        for p in formatted_plants:
            sp = p.get("species", "")
            if sp:
                distinct_species.add(sp)
        farm_sourced_photos = 0
        for t in all_types:
            name = t.get("attributes", {}).get("name", "")
            if name not in distinct_species:
                continue
            image_rel = t.get("relationships", {}).get("image", {}).get("data")
            if not image_rel:
                continue
            desc = t.get("attributes", {}).get("description", {})
            desc_text = desc.get("value", "") if isinstance(desc, dict) else str(desc or "")
            meta = parse_plant_type_metadata(desc_text)
            src = meta.get("photo_source", "")
            # farm_observation = Tier 1. Empty = legacy (pre-batch, all were farm-sourced).
            if src in ("farm_observation", ""):
                farm_sourced_photos += 1
        photo_coverage = farm_sourced_photos / len(distinct_species) if distinct_species else 0.0

        # observation_pipeline_age: max days any observation has been pending
        pipeline_age = 0
        try:
            obs_client = get_observe_client()
            pending = obs_client.list_observations(status="pending")
            if isinstance(pending, list) and pending:
                from datetime import datetime as _dt, timezone as _tz
                today = _dt.now(tz=_tz.utc)
                max_age = 0
                for obs in pending:
                    ts = obs.get("timestamp") or obs.get("date") or ""
                    if not ts:
                        continue
                    try:
                        obs_dt = _dt.fromisoformat(ts.replace("Z", "+00:00"))
                        age = (today - obs_dt).days
                        if age > max_age:
                            max_age = age
                    except (ValueError, TypeError):
                        continue
                pipeline_age = max_age
        except Exception:
            pipeline_age = None

        # provenance_coverage: fraction of recent logs with interaction stamps
        prov_coverage = 0.0
        try:
            recent_logs = client.get_logs(max_results=50)
            stamp_result = count_stamps_in_logs(
                [{"notes": l.get("attributes", {}).get("notes", "")} for l in recent_logs]
            )
            prov_coverage = stamp_result.get("coverage", 0.0)
        except Exception:
            prov_coverage = None

        # source_conflict_count: pending activity logs with discrepancy/conflict
        conflict_count = 0
        try:
            pending_activities = client.get_logs(log_type="activity", status="pending")
            for log in pending_activities:
                name = log.get("attributes", {}).get("name", "") or ""
                notes = log.get("attributes", {}).get("notes", {})
                notes_text = notes.get("value", "") if isinstance(notes, dict) else str(notes)
                combined = (name + " " + notes_text).lower()
                if "discrepancy" in combined or "conflict" in combined:
                    conflict_count += 1
        except Exception:
            conflict_count = None

        data_data = {
            "species_photo_coverage": round(photo_coverage, 3),
            "observation_pipeline_age": pipeline_age,
            "provenance_coverage": round(prov_coverage, 3) if prov_coverage is not None else None,
            "source_conflict_count": conflict_count,
        }
        return assess_data_maturity(data_data, config)

    with ThreadPoolExecutor(max_workers=3) as ex:
        system_fut = ex.submit(_system_dimension, active_plant_count)
        team_fut = ex.submit(_team_dimension)
        data_fut = ex.submit(_data_dimension, all_plants, all_types)
        try:
            system_result = system_fut.result()
            result["dimensions"]["system"] = system_result
            result["scale_triggers"].extend(system_result.get("scale_triggers", []))
        except Exception as e:
            result["dimensions"]["system"] = {"error": str(e)}
        try:
            team_result = team_fut.result()
            result["dimensions"]["team"] = team_result
            result["scale_triggers"].extend(team_result.get("scale_triggers", []))
        except Exception as e:
            result["dimensions"]["team"] = {"error": str(e)}
        try:
            data_result = data_fut.result()
            result["dimensions"]["data"] = data_result
            result["scale_triggers"].extend(data_result.get("scale_triggers", []))
        except Exception as e:
            result["dimensions"]["data"] = {"error": str(e)}

    # ── Overall maturity summary ───────────────────────────────

    stages = []
    for dim_name in ["farm", "system", "team", "data"]:
        dim = result["dimensions"].get(dim_name, {})
        if "stage" in dim:
            stages.append(f"{dim_name.title()}: {dim['stage']}")

    result["overall_maturity"] = " | ".join(stages) if stages else "Unable to assess"

    # Surface assumptions from the YAML so the human reviewer knows what's baked in
    for dim_name, dim_config in config.get("dimensions", {}).items():
        for stage in dim_config.get("stages", []):
            if "assumption" in stage:
                result["assumptions"].append({
                    "dimension": dim_name,
                    "stage": stage["label"],
                    "assumption": stage["assumption"],
                })
        for metric_name, metric_config in dim_config.get("metrics", {}).items():
            if "assumption" in metric_config:
                result["assumptions"].append({
                    "dimension": dim_name,
                    "metric": metric_name,
                    "assumption": metric_config["assumption"],
                })

    return json.dumps(result, indent=2, default=str)


# ═══════════════════════════════════════════════════════════════
# PROMPTS — Conversation templates
# ═══════════════════════════════════════════════════════════════

@mcp.prompt
def log_field_observation(section_id: str) -> str:
    """Template for recording field observations in a section.

    Args:
        section_id: The section being observed (e.g., "P2R3.15-21").
    """
    return f"""I want to record field observations for section {section_id}.

Please help me:
1. First, show me what's currently planted in {section_id} using the query_plants tool
2. Ask me about each species — how many are alive, any health issues, new plantings
3. For each change, create the appropriate observation log using create_observation
4. Summarize all changes made

Let's start — show me the current inventory for {section_id}."""


@mcp.prompt
def check_section_status(section_id: str) -> str:
    """Template for reviewing the current state of a section.

    Args:
        section_id: The section to review (e.g., "P2R3.15-21").
    """
    return f"""Show me the current state of section {section_id}.

Please:
1. List all plants in the section with their current counts
2. Show the most recent logs for this section
3. Highlight any issues (dead plants, zero counts, recent changes)
4. Suggest any actions that might be needed"""


@mcp.prompt
def compare_inventory(section_id: str) -> str:
    """Template for comparing inventory counts over time.

    Args:
        section_id: The section to compare (e.g., "P2R3.15-21").
    """
    return f"""Compare the inventory history for section {section_id}.

Please:
1. Get the current plant list for {section_id}
2. Query all observation logs for this section
3. Show how counts have changed over time for each species
4. Identify plants with declining counts that may need attention
5. Note any new plantings or replacements"""


# ═══════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    mcp.run()
