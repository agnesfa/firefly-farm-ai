"""
Shared test fixtures and factory functions for the farmOS MCP server test suite.

Factory functions produce realistic farmOS JSON:API objects. Each test
can customise the defaults to exercise specific edge cases.
"""

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest

AEST = timezone(timedelta(hours=10))


# ── Factory functions ──────────────────────────────────────────


def make_uuid():
    """Generate a random UUID string."""
    return str(uuid.uuid4())


def make_plant_asset(
    name="25 APR 2025 - Pigeon Pea - P2R2.0-3",
    asset_uuid=None,
    status="active",
    inventory_count=None,
    plant_type_uuid=None,
    notes="",
):
    """Build a farmOS JSON:API plant asset dict."""
    asset_uuid = asset_uuid or make_uuid()
    plant_type_uuid = plant_type_uuid or make_uuid()

    inventory = []
    if inventory_count is not None:
        inventory = [{"measure": "count", "value": str(inventory_count), "units": {"id": "2371b79e-a87b-4152-b6e4-ea6a9ed37fd0"}}]

    notes_field = {"value": notes, "format": "default"} if notes else {}

    return {
        "type": "asset--plant",
        "id": asset_uuid,
        "attributes": {
            "name": name,
            "status": status,
            "inventory": inventory,
            "notes": notes_field,
        },
        "relationships": {
            "plant_type": {
                "data": [{"type": "taxonomy_term--plant_type", "id": plant_type_uuid}],
            },
        },
    }


def make_log(
    name="Observation P2R3.14-21 — Pigeon Pea",
    log_type="observation",
    log_uuid=None,
    timestamp=None,
    notes="",
    quantities=None,
    asset_ids=None,
    location_ids=None,
    is_movement=False,
):
    """Build a farmOS JSON:API log dict."""
    log_uuid = log_uuid or make_uuid()
    timestamp = timestamp or str(int(datetime.now(tz=AEST).timestamp()))

    notes_field = {"value": notes, "format": "default"} if notes else {}

    asset_data = [{"type": "asset--plant", "id": aid} for aid in (asset_ids or [])]
    location_data = [{"type": "asset--land", "id": lid} for lid in (location_ids or [])]

    log = {
        "type": f"log--{log_type}",
        "id": log_uuid,
        "attributes": {
            "name": name,
            "timestamp": timestamp,
            "status": "done",
            "is_movement": is_movement,
            "notes": notes_field,
        },
        "relationships": {
            "asset": {"data": asset_data},
            "location": {"data": location_data},
            "quantity": {"data": []},
        },
    }

    if quantities:
        log["_quantities"] = quantities

    return log


def make_quantity(
    value=4,
    measure="count",
    inventory_adjustment="reset",
    label="plants",
    qty_uuid=None,
):
    """Build a farmOS JSON:API quantity dict (for _quantities merge)."""
    qty_uuid = qty_uuid or make_uuid()
    return {
        "type": "quantity--standard",
        "id": qty_uuid,
        "attributes": {
            "value": {"decimal": str(value)},
            "measure": measure,
            "inventory_adjustment": inventory_adjustment,
            "label": label,
        },
    }


def make_plant_type(
    name="Pigeon Pea",
    term_uuid=None,
    description="",
    maturity_days=None,
    transplant_days=None,
):
    """Build a farmOS JSON:API plant_type taxonomy term dict."""
    term_uuid = term_uuid or make_uuid()
    desc_field = {"value": description, "format": "default"} if description else {}

    attrs = {
        "name": name,
        "description": desc_field,
    }
    if maturity_days is not None:
        attrs["maturity_days"] = maturity_days
    if transplant_days is not None:
        attrs["transplant_days"] = transplant_days

    return {
        "type": "taxonomy_term--plant_type",
        "id": term_uuid,
        "attributes": attrs,
    }


def make_section_asset(name="P2R3.14-21", asset_uuid=None):
    """Build a farmOS JSON:API land asset dict (section)."""
    asset_uuid = asset_uuid or make_uuid()
    return {
        "type": "asset--land",
        "id": asset_uuid,
        "attributes": {
            "name": name,
            "status": "active",
        },
    }


def make_observation(
    species="Pigeon Pea",
    section_id="P2R3.14-21",
    observer="Claire",
    new_count=3,
    previous_count=5,
    mode="full_inventory",
    status="approved",
    submission_id=None,
    section_notes="",
    plant_notes="",
    condition="alive",
    timestamp="2026-03-09T03:15:00.000Z",
):
    """Build a Google Sheet observation row dict (as returned by the Apps Script)."""
    return {
        "submission_id": submission_id or make_uuid()[:8],
        "section_id": section_id,
        "species": species,
        "strata": "high",
        "observer": observer,
        "new_count": new_count,
        "previous_count": previous_count,
        "mode": mode,
        "status": status,
        "section_notes": section_notes,
        "plant_notes": plant_notes,
        "condition": condition,
        "timestamp": timestamp,
    }


def make_json_api_response(data=None, included=None, links=None):
    """Wrap data in a JSON:API response envelope."""
    resp = {"data": data if data is not None else []}
    if included:
        resp["included"] = included
    if links:
        resp["links"] = links
    return resp


# ── Pre-built fixtures ─────────────────────────────────────────


@pytest.fixture
def pigeon_pea_asset():
    return make_plant_asset(
        name="25 APR 2025 - Pigeon Pea - P2R2.0-3",
        inventory_count=4,
    )


@pytest.fixture
def basil_sweet_classic_asset():
    """Tricky double-dash name that tests name parsing edge case."""
    return make_plant_asset(
        name="25 APR 2025 - Basil - Sweet (Classic) - P2R3.14-21",
        inventory_count=2,
    )


@pytest.fixture
def mock_farmos_client():
    """A MagicMock with the FarmOSClient spec and sensible defaults."""
    from farmos_client import FarmOSClient
    mock = MagicMock(spec=FarmOSClient)
    mock.is_connected = True
    mock._connected = True
    mock.hostname = "https://margregen.farmos.net"
    return mock


@pytest.fixture
def mock_observe_client():
    """A MagicMock with the ObservationClient spec."""
    from observe_client import ObservationClient
    mock = MagicMock(spec=ObservationClient)
    mock.is_connected = True
    return mock


@pytest.fixture
def mock_memory_client():
    """A MagicMock with the MemoryClient spec."""
    from memory_client import MemoryClient
    mock = MagicMock(spec=MemoryClient)
    mock.is_connected = True
    return mock
