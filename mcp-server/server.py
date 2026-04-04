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

        # Fetch plants for each section and aggregate
        all_formatted = []
        for sec_id in sorted(sections_list):
            plants = client.get_plant_assets(section_id=sec_id, species=species)
            all_formatted.extend([format_plant_asset(p) for p in plants])

        formatted = all_formatted
        query_info = {"section_prefix": section_prefix}
        if species:
            query_info["species"] = species
    else:
        # --- original single-section / species mode ---
        plants = client.get_plant_assets(section_id=section_id, species=species)
        formatted = [format_plant_asset(p) for p in plants]
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
) -> str:
    """Create an observation log with inventory count for a plant asset.

    This updates the plant's inventory count in farmOS and records the observation.

    Args:
        plant_name: Exact plant asset name (e.g., "25 APR 2025 - Pigeon Pea - P2R2.0-3").
        count: New inventory count (number of living plants).
        notes: Observation notes (e.g., "2 lost to frost, 3 healthy"). Optional.
        date: Observation date in ISO format (e.g., "2026-03-09"). Defaults to today.

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

    # Build log name — include date so future inventory updates aren't blocked
    species = formatted["species"]
    obs_date = datetime.fromtimestamp(timestamp, tz=AEST).strftime("%Y-%m-%d")
    log_name = f"Observation {section_id} — {species} — {obs_date}"

    # Check if this exact log already exists (same species + section + date)
    existing = client.log_exists(log_name, "observation")
    if existing:
        return json.dumps({
            "status": "skipped",
            "message": f"Observation log '{log_name}' already exists",
            "existing_log_id": existing,
        })

    # Create quantity (inventory count)
    qty_id = client.create_quantity(plant_id, count, adjustment="reset")

    # Create observation log
    log_id = client.create_observation_log(
        plant_id=plant_id,
        section_uuid=section_uuid,
        quantity_id=qty_id,
        timestamp=timestamp,
        name=log_name,
        notes=notes,
    )

    return json.dumps({
        "status": "created",
        "log_id": log_id,
        "log_name": log_name,
        "plant": plant_name,
        "count": count,
        "notes": notes,
        "timestamp": format_timestamp(timestamp),
    }, indent=2)


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

    log_id = client.create_activity_log(
        section_uuid=section_uuid,
        timestamp=timestamp,
        name=log_name,
        notes=notes,
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

    success = client.update_log_status(log_id, "activity", "done")
    if not success:
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
    # Delegate to create_observation with today's date
    date_today = datetime.now(tz=AEST).strftime("%Y-%m-%d")
    update_notes = f"Inventory update: {notes}" if notes else "Inventory update"
    return create_observation(
        plant_name=plant_name,
        count=new_count,
        notes=update_notes,
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

    # Create plant asset
    plant_id = client.create_plant_asset(asset_name, plant_type_uuid, notes=notes)
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
        notes=notes,
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

    # Optionally create an activity log with the reason
    if reason:
        section_id = formatted.get("section", "")
        section_uuid = client.get_section_uuid(section_id) if section_id else None

        if section_uuid:
            timestamp = parse_date(None)
            species = formatted.get("species", "")
            log_name = f"Archived — {species} — {section_id}"
            log_id = client.create_activity_log(
                section_uuid=section_uuid,
                timestamp=timestamp,
                name=log_name,
                notes=reason,
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


def _build_import_notes(obs: dict, extra: str = "") -> str:
    """Build rich notes from observation data for farmOS log.

    Preserves ALL raw data from the field observation so the Google Sheet
    rows can be safely deleted after import.
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
    if obs.get("section_notes"):
        parts.append(f"Section notes: {obs['section_notes']}")
    if obs.get("plant_notes"):
        parts.append(f"Plant notes: {obs['plant_notes']}")
    if obs.get("previous_count") is not None and obs.get("new_count") is not None:
        parts.append(f"Count: {obs['previous_count']} → {obs['new_count']}")
    if extra:
        parts.append(extra)
    return "\n".join(parts)


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
        return json.dumps({"error": f"No observations found for submission '{submission_id}'"})

    # Validate status — must be reviewed or approved
    statuses = set(obs.get("status") for obs in observations)
    if statuses - {"reviewed", "approved"}:
        return json.dumps({
            "error": f"Submission has unexpected statuses: {statuses}. "
                     "Only 'reviewed' or 'approved' observations can be imported.",
        })

    section_id = observations[0].get("section_id", "")
    mode = observations[0].get("mode", "")
    obs_date = observations[0].get("timestamp", "")[:10]  # YYYY-MM-DD

    actions = []
    errors = []

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
                        notes=_build_import_notes(obs, "New plant added via field observation"),
                    ))
                    action["result"] = result_json.get("status", "unknown")
                    action["plant_name"] = result_json.get("plant", {}).get("name")
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

            # Build notes — preserve all raw data from the field observation
            combined_notes = _build_import_notes(obs)

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
                obs_notes = _build_import_notes(obs)
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
                if not dry_run and count_val is not None:
                    try:
                        result_json = json.loads(create_observation(
                            plant_name=plant_name,
                            count=count_val,
                            notes=obs_notes,
                            date=obs_date or None,
                        ))
                        action["result"] = result_json.get("status", "unknown")
                        action["log_id"] = result_json.get("log_id")
                    except Exception as e:
                        action["result"] = "error"
                        errors.append(f"Observation for {species} in {obs_section}: {e}")
                elif not dry_run and count_val is None and not action_text:
                    # Notes-only, no action text — create activity
                    try:
                        result_json = json.loads(create_activity(
                            section_id=obs_section,
                            activity_type="observation",
                            notes=obs_notes,
                            date=obs_date or None,
                        ))
                        action["result"] = result_json.get("status", "unknown")
                        action["type"] = "activity"
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

    return json.dumps({
        "submission_id": submission_id,
        "section_id": section_id,
        "dry_run": dry_run,
        "total_actions": len(actions),
        "actions": actions,
        "errors": errors if errors else None,
        "sheet_status": sheet_status,
        "pages_regenerated": regen_message,
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

    try:
        result = mem_client.write_summary(
            user=user,
            topics=topics,
            decisions=decisions,
            farmos_changes=farmos_changes,
            questions=questions,
            summary=summary,
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

    try:
        result = kb_client.add(fields={
            "title": title,
            "content": content,
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
    """Assess farm maturity across three dimensions: Farm (biological),
    System (technical), and Team (human). Returns current growth stage
    per dimension, metric scores, and active scale triggers with
    recommended build actions.

    All thresholds and interpretation rules are defined in
    knowledge/farm_growth.yaml (human-reviewable, not hardcoded).
    """
    from semantics import (
        assess_farm_maturity,
        assess_system_maturity,
        assess_team_maturity,
        load_growth_config,
        assess_section_health,
        load_semantics,
    )

    config = load_growth_config()
    client = get_client()
    semantics_config = load_semantics()

    result = {"dimensions": {}, "scale_triggers": [], "assumptions": []}

    # ── Farm dimension: aggregate section-level health ──────────

    try:
        # Get all plant assets for farm-wide metrics
        all_plants = client.fetch_all_paginated("asset/plant", filters={"status": "active"})
        active_plant_count = len(all_plants)

        # Build plant_types_db for strata/succession lookups
        all_types = client.get_all_plant_types_cached()
        plant_types_db = {}
        for t in all_types:
            name = t.get("attributes", {}).get("name", "")
            desc = t.get("attributes", {}).get("description", {})
            desc_text = desc.get("value", "") if isinstance(desc, dict) else str(desc)
            from helpers import parse_plant_type_metadata
            meta = parse_plant_type_metadata(desc_text)
            plant_types_db[name] = meta

        # Sample section health across paddock sections
        sections = client.get_section_assets()
        section_scores = []
        for sec in sections[:20]:  # Sample first 20 for performance
            sec_name = sec.get("attributes", {}).get("name", "")
            sec_plants_raw = client.get_plant_assets(section_id=sec_name)
            sec_plants = [format_plant_asset(p) for p in sec_plants_raw]
            sec_logs_raw = client.get_logs(section_id=sec_name)
            sec_logs = [format_log(l) for l in sec_logs_raw]
            health = assess_section_health(
                sec_plants, sec_logs, plant_types_db, has_trees=True,
                semantics=semantics_config,
            )
            score = {
                "section": sec_name,
                "strata_score": health.get("strata", {}).get("score", 0),
                "survival_rate": None,  # Not computed at section level yet
                "status": health.get("overall_status", "unknown"),
            }
            section_scores.append(score)

        farm_data = {
            "active_plants": active_plant_count,
            "section_health_scores": section_scores,
        }
        farm_result = assess_farm_maturity(farm_data, config)
        farm_result["sampled_sections"] = len(section_scores)
        farm_result["total_sections"] = len(sections)
        result["dimensions"]["farm"] = farm_result
        result["scale_triggers"].extend(farm_result.get("scale_triggers", []))

    except Exception as e:
        result["dimensions"]["farm"] = {"error": str(e)}

    # ── System dimension: infrastructure metrics ────────────────

    try:
        # Total entities
        all_assets = client.fetch_all_paginated("asset/plant", filters={"status": "active"})
        # Approximate total from what we already have
        total_entities = active_plant_count  # plants
        # Add log estimate
        obs_logs = client.get_logs(log_type="observation", max_results=1)
        total_entities += 1200  # rough estimate from known counts

        # Plant type drift
        try:
            pt_client = get_plant_types_client()
            drift_result = pt_client.reconcile()
            drift_count = drift_result.get("mismatch_count", 0) if isinstance(drift_result, dict) else 0
        except Exception:
            drift_count = None

        # Observation backlog
        try:
            obs_client = get_observe_client()
            pending = obs_client.list_observations(status="pending")
            backlog_count = len(pending) if isinstance(pending, list) else 0
        except Exception:
            backlog_count = None

        system_data = {
            "total_entities": total_entities,
            "plant_type_drift": drift_count,
            "observation_backlog": backlog_count,
        }
        system_result = assess_system_maturity(system_data, config)
        result["dimensions"]["system"] = system_result
        result["scale_triggers"].extend(system_result.get("scale_triggers", []))

    except Exception as e:
        result["dimensions"]["system"] = {"error": str(e)}

    # ── Team dimension: usage metrics ──────────────────────────

    try:
        mem_client = get_memory_client()
        recent_activity = mem_client.read_activity(days=7)

        if isinstance(recent_activity, list):
            distinct_users = len(set(
                entry.get("user", "") for entry in recent_activity if entry.get("user")
            ))
            memory_velocity = len(recent_activity)
        else:
            distinct_users = 0
            memory_velocity = 0

        # KB count
        try:
            kb_client = get_knowledge_client()
            kb_entries = kb_client.list(summary_only=True)
            kb_count = len(kb_entries) if isinstance(kb_entries, list) else 0
        except Exception:
            kb_count = None

        team_data = {
            "active_users_weekly": distinct_users,
            "team_memory_velocity": memory_velocity,
            "kb_entry_count": kb_count,
        }
        team_result = assess_team_maturity(team_data, config)
        result["dimensions"]["team"] = team_result
        result["scale_triggers"].extend(team_result.get("scale_triggers", []))

    except Exception as e:
        result["dimensions"]["team"] = {"error": str(e)}

    # ── Overall maturity summary ───────────────────────────────

    stages = []
    for dim_name in ["farm", "system", "team"]:
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
