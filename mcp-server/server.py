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
Use observation tools to review and import field observations from the Sheet.

Key concepts:
- Sections are identified like P2R3.14-21 (Paddock 2, Row 3, metres 14-21)
- Plant assets are named: "{date} - {species} - {section}"
- Strata: emergent (20m+), high (8-20m), medium (2-8m), low (0-2m)
- Succession: pioneer (0-5yr), secondary (3-15yr), climax (15+yr)
""",
)

# Global clients — connect lazily on first use
_client: Optional[FarmOSClient] = None
_observe_client: Optional[ObservationClient] = None


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
        "query": {"section_id": section_id, "species": species},
        "summary": {
            "total_species_entries": len(inventory_items),
            "total_plant_count": total_plant_count,
        },
        "plants": inventory_items,
    }

    if unknown_count > 0:
        result["summary"]["entries_without_count"] = unknown_count

    # Add section breakdown when querying by species across sections
    if species and not section_id and len(section_totals) > 1:
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
        section: Filter by section ID (e.g., "P2R3.14-21"). Optional.
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
                        notes=f"Field note: {section_notes}",
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
                        notes=plant_notes or f"Added via field observation",
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

            # Build notes
            parts = []
            if condition and condition != "alive":
                parts.append(f"Condition: {condition}")
            if plant_notes:
                parts.append(plant_notes)
            combined_notes = ". ".join(parts) if parts else ""

            # Only update if count changed or there are meaningful notes
            count_val = int(new_count) if new_count is not None else None
            prev_val = int(previous_count) if previous_count is not None else None
            count_changed = count_val is not None and count_val != prev_val

            if count_changed or combined_notes:
                action = {
                    "type": "observation",
                    "plant_name": plant_name,
                    "species": species,
                    "section": obs_section,
                    "previous_count": prev_val,
                    "new_count": count_val,
                    "notes": combined_notes,
                }
                if not dry_run and count_val is not None:
                    try:
                        result_json = json.loads(create_observation(
                            plant_name=plant_name,
                            count=count_val,
                            notes=combined_notes,
                            date=obs_date or None,
                        ))
                        action["result"] = result_json.get("status", "unknown")
                        action["log_id"] = result_json.get("log_id")
                    except Exception as e:
                        action["result"] = "error"
                        errors.append(f"Observation for {species} in {obs_section}: {e}")
                elif not dry_run and count_val is None:
                    # Notes-only observation — create activity instead
                    try:
                        result_json = json.loads(create_activity(
                            section_id=obs_section,
                            activity_type="observation",
                            notes=f"{species}: {combined_notes}",
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

    # Update Sheet status to imported (unless dry_run or all failed)
    imported_count = sum(1 for a in actions if a.get("result") == "created")
    if not dry_run and (imported_count > 0 or not errors):
        try:
            obs_client.update_status([{
                "submission_id": submission_id,
                "status": "imported",
                "reviewer": reviewer,
                "notes": f"{imported_count} actions imported to farmOS",
            }])
        except Exception as e:
            errors.append(f"Failed to update Sheet status: {e}")

    return json.dumps({
        "submission_id": submission_id,
        "section_id": section_id,
        "dry_run": dry_run,
        "total_actions": len(actions),
        "actions": actions,
        "errors": errors if errors else None,
        "sheet_status": "imported" if not dry_run and not errors else ("dry_run" if dry_run else "partial"),
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
