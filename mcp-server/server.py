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
import sys
import os
from datetime import datetime
from typing import Optional

# Add parent directory to path so we can find our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastmcp import FastMCP

from farmos_client import FarmOSClient
from helpers import (
    parse_date,
    format_planted_label,
    build_asset_name,
    format_timestamp,
    format_plant_asset,
    format_log,
    format_plant_type,
    format_section_from_assets,
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

Key concepts:
- Sections are identified like P2R3.14-21 (Paddock 2, Row 3, metres 14-21)
- Plant assets are named: "{date} - {species} - {section}"
- Strata: emergent (20m+), high (8-20m), medium (2-8m), low (0-2m)
- Succession: pioneer (0-5yr), secondary (3-15yr), climax (15+yr)
""",
)

# Global farmOS client — connects lazily on first use
_client: Optional[FarmOSClient] = None


def get_client() -> FarmOSClient:
    """Get or create the farmOS client connection."""
    global _client
    if _client is None or not _client.is_connected:
        _client = FarmOSClient()
        _client.connect()
    return _client


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
        section_id: Filter by section (e.g., "P2R3.14-21"). Optional.
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
    sections = client.get_section_assets(row_filter=row)

    # Fetch ALL plant assets once (not per-section!)
    all_plants = client.fetch_all_paginated("asset/plant", filters={"status": "active"})

    # Build section→plant count index
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
    for s in sections:
        name = s.get("attributes", {}).get("name", "")
        results.append({
            "section_id": name,
            "uuid": s.get("id"),
            "plant_count": plant_counts.get(name, 0),
        })

    # Sort by section ID
    results.sort(key=lambda x: x["section_id"])

    # Group by row
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
    max_results: int = 20,
) -> str:
    """Search logs by type, section, or species.

    Args:
        log_type: Filter by log type: observation, activity, transplanting, harvest, seeding. Optional.
        section_id: Filter by section ID in log name. Optional.
        species: Filter by species name in log name. Optional.
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
        max_results=max_results,
    )
    formatted = [format_log(l) for l in logs]
    return json.dumps({
        "count": len(formatted),
        "filters": {
            "log_type": log_type,
            "section_id": section_id,
            "species": species,
        },
        "logs": formatted,
    }, indent=2)


@mcp.tool
def get_inventory(section_id: Optional[str] = None, species: Optional[str] = None) -> str:
    """Get current inventory (plant counts) for a section or specific species.

    Args:
        section_id: Section to check inventory for (e.g., "P2R3.14-21"). Optional.
        species: Species to check across all sections (e.g., "Pigeon Pea"). Optional.
        At least one of section_id or species should be provided.

    Returns:
        Plant inventory with current counts.
    """
    client = get_client()

    if not section_id and not species:
        return json.dumps({"error": "Please provide section_id or species (or both)"})

    plants = client.get_plant_assets(section_id=section_id, species=species)
    formatted = [format_plant_asset(p) for p in plants]

    # Count summary
    total = len(formatted)

    return json.dumps({
        "query": {"section_id": section_id, "species": species},
        "total_plant_assets": total,
        "plants": formatted,
        "note": "Each plant asset represents one species in one section. "
                "Actual plant counts are tracked in the most recent observation log.",
    }, indent=2)


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

    # Build log name
    species = formatted["species"]
    log_name = f"Observation {section_id} — {species}"

    # Check if this log already exists (idempotency)
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
) -> str:
    """Log a field activity (watering, weeding, mulching, etc.) for a section.

    Args:
        section_id: Section where the activity happened (e.g., "P2R3.14-21").
        activity_type: Type of activity (e.g., "watering", "weeding", "mulching", "pruning").
        notes: Description of the activity.
        date: Activity date in ISO format. Defaults to today.

    Returns:
        Created log details or error message.
    """
    client = get_client()

    section_uuid = client.get_section_uuid(section_id)
    if not section_uuid:
        return json.dumps({"error": f"Section '{section_id}' not found in farmOS"})

    timestamp = parse_date(date) if date else parse_date(None)
    log_name = f"{activity_type.title()} — {section_id}"

    log_id = client.create_activity_log(
        section_uuid=section_uuid,
        timestamp=timestamp,
        name=log_name,
        notes=notes,
    )

    return json.dumps({
        "status": "created",
        "log_id": log_id,
        "log_name": log_name,
        "section": section_id,
        "activity_type": activity_type,
        "notes": notes,
        "timestamp": format_timestamp(timestamp),
    }, indent=2)


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
        section_id: Section to place the plant (e.g., "P2R3.14-21").
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


# ═══════════════════════════════════════════════════════════════
# PROMPTS — Conversation templates
# ═══════════════════════════════════════════════════════════════

@mcp.prompt
def log_field_observation(section_id: str) -> str:
    """Template for recording field observations in a section.

    Args:
        section_id: The section being observed (e.g., "P2R3.14-21").
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
        section_id: The section to review (e.g., "P2R3.14-21").
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
        section_id: The section to compare (e.g., "P2R3.14-21").
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
