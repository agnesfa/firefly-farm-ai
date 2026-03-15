"""
Tests for the MCP server write tools: create_observation, create_activity,
create_plant, and update_inventory.

Each test monkeypatches server.get_client() to return a mock FarmOSClient,
verifying the tools produce correct JSON output and handle error/idempotency
cases properly.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import make_plant_asset, make_uuid


# ── create_observation ────────────────────────────────────────


class TestCreateObservation:
    def test_create_observation_happy_path(self, mock_farmos_client, monkeypatch):
        """Successful observation creates quantity + log and returns status=created."""
        import server

        plant = make_plant_asset(
            name="25 APR 2025 - Pigeon Pea - P2R2.0-3",
            inventory_count=4,
        )
        section_uuid = make_uuid()
        qty_id = make_uuid()
        log_id = make_uuid()

        mock_farmos_client.fetch_by_name.return_value = [plant]
        mock_farmos_client.get_section_uuid.return_value = section_uuid
        mock_farmos_client.log_exists.return_value = None
        mock_farmos_client.create_quantity.return_value = qty_id
        mock_farmos_client.create_observation_log.return_value = log_id

        monkeypatch.setattr(server, "get_client", lambda: mock_farmos_client)

        result = json.loads(server.create_observation(
            plant_name="25 APR 2025 - Pigeon Pea - P2R2.0-3",
            count=3,
            notes="lost 1 to frost",
            date="2026-03-09",
        ))

        assert result["status"] == "created"
        assert result["log_id"] == log_id
        assert result["count"] == 3
        assert result["notes"] == "lost 1 to frost"
        assert result["log_name"] == "Observation P2R2.0-3 \u2014 Pigeon Pea"

        mock_farmos_client.create_quantity.assert_called_once_with(
            plant["id"], 3, adjustment="reset",
        )
        mock_farmos_client.create_observation_log.assert_called_once()

    def test_create_observation_plant_not_found(self, mock_farmos_client, monkeypatch):
        """Returns error JSON when the plant asset does not exist."""
        import server

        mock_farmos_client.fetch_by_name.return_value = []

        monkeypatch.setattr(server, "get_client", lambda: mock_farmos_client)

        result = json.loads(server.create_observation(
            plant_name="NONEXISTENT - Fake Plant - P2R9.0-1",
            count=1,
        ))

        assert "error" in result
        assert "not found" in result["error"]
        mock_farmos_client.create_quantity.assert_not_called()
        mock_farmos_client.create_observation_log.assert_not_called()

    def test_create_observation_idempotency(self, mock_farmos_client, monkeypatch):
        """Returns status=skipped when the observation log already exists."""
        import server

        plant = make_plant_asset(name="25 APR 2025 - Pigeon Pea - P2R2.0-3")
        existing_log_id = make_uuid()

        mock_farmos_client.fetch_by_name.return_value = [plant]
        mock_farmos_client.get_section_uuid.return_value = make_uuid()
        mock_farmos_client.log_exists.return_value = existing_log_id

        monkeypatch.setattr(server, "get_client", lambda: mock_farmos_client)

        result = json.loads(server.create_observation(
            plant_name="25 APR 2025 - Pigeon Pea - P2R2.0-3",
            count=3,
        ))

        assert result["status"] == "skipped"
        assert result["existing_log_id"] == existing_log_id
        mock_farmos_client.create_quantity.assert_not_called()
        mock_farmos_client.create_observation_log.assert_not_called()


# ── create_activity ───────────────────────────────────────────


class TestCreateActivity:
    def test_create_activity_happy_path(self, mock_farmos_client, monkeypatch):
        """Successful activity log creation returns status=created."""
        import server

        section_uuid = make_uuid()
        log_id = make_uuid()

        mock_farmos_client.get_section_uuid.return_value = section_uuid
        mock_farmos_client.create_activity_log.return_value = log_id

        monkeypatch.setattr(server, "get_client", lambda: mock_farmos_client)

        result = json.loads(server.create_activity(
            section_id="P2R3.15-21",
            activity_type="watering",
            notes="Deep watering after dry spell",
            date="2026-03-10",
        ))

        assert result["status"] == "created"
        assert result["log_id"] == log_id
        assert result["log_name"] == "Watering \u2014 P2R3.15-21"
        assert result["section"] == "P2R3.15-21"
        assert result["activity_type"] == "watering"
        assert result["notes"] == "Deep watering after dry spell"

        mock_farmos_client.create_activity_log.assert_called_once()

    def test_create_activity_section_not_found(self, mock_farmos_client, monkeypatch):
        """Returns error JSON when the section does not exist."""
        import server

        mock_farmos_client.get_section_uuid.return_value = None

        monkeypatch.setattr(server, "get_client", lambda: mock_farmos_client)

        result = json.loads(server.create_activity(
            section_id="P2R9.99-100",
            activity_type="mulching",
            notes="Should fail",
        ))

        assert "error" in result
        assert "P2R9.99-100" in result["error"]
        mock_farmos_client.create_activity_log.assert_not_called()


# ── create_plant ──────────────────────────────────────────────


class TestCreatePlant:
    def test_create_plant_happy_path(self, mock_farmos_client, monkeypatch):
        """Successful plant creation returns asset details and observation log."""
        import server

        plant_type_uuid = make_uuid()
        section_uuid = make_uuid()
        plant_id = make_uuid()
        qty_id = make_uuid()
        log_id = make_uuid()

        mock_farmos_client.get_plant_type_uuid.return_value = plant_type_uuid
        mock_farmos_client.get_section_uuid.return_value = section_uuid
        mock_farmos_client.plant_asset_exists.return_value = None
        mock_farmos_client.create_plant_asset.return_value = plant_id
        mock_farmos_client.create_quantity.return_value = qty_id
        mock_farmos_client.create_observation_log.return_value = log_id

        monkeypatch.setattr(server, "get_client", lambda: mock_farmos_client)

        result = json.loads(server.create_plant(
            species="Pigeon Pea",
            section_id="P2R3.15-21",
            count=5,
            planted_date="2026-03-09",
            notes="New planting",
        ))

        assert result["status"] == "created"
        assert result["plant"]["id"] == plant_id
        assert result["plant"]["species"] == "Pigeon Pea"
        assert result["plant"]["section"] == "P2R3.15-21"
        assert result["plant"]["count"] == 5
        # Asset name follows convention: "{date_label} - {species} - {section}"
        assert "Pigeon Pea" in result["plant"]["name"]
        assert "P2R3.15-21" in result["plant"]["name"]
        assert result["observation_log"]["id"] == log_id

        mock_farmos_client.create_plant_asset.assert_called_once()
        mock_farmos_client.create_quantity.assert_called_once_with(
            plant_id, 5, adjustment="reset",
        )

    def test_create_plant_type_not_found(self, mock_farmos_client, monkeypatch):
        """Returns error JSON when the plant type taxonomy term does not exist."""
        import server

        mock_farmos_client.get_plant_type_uuid.return_value = None

        monkeypatch.setattr(server, "get_client", lambda: mock_farmos_client)

        result = json.loads(server.create_plant(
            species="Nonexistent Species",
            section_id="P2R3.15-21",
            count=1,
        ))

        assert "error" in result
        assert "Nonexistent Species" in result["error"]
        mock_farmos_client.create_plant_asset.assert_not_called()

    def test_create_plant_idempotency(self, mock_farmos_client, monkeypatch):
        """Returns status=skipped when the plant asset already exists."""
        import server

        existing_id = make_uuid()

        mock_farmos_client.get_plant_type_uuid.return_value = make_uuid()
        mock_farmos_client.get_section_uuid.return_value = make_uuid()
        mock_farmos_client.plant_asset_exists.return_value = existing_id

        monkeypatch.setattr(server, "get_client", lambda: mock_farmos_client)

        result = json.loads(server.create_plant(
            species="Pigeon Pea",
            section_id="P2R3.15-21",
            count=3,
            planted_date="2026-03-09",
        ))

        assert result["status"] == "skipped"
        assert result["existing_id"] == existing_id
        mock_farmos_client.create_plant_asset.assert_not_called()


# ── update_inventory ──────────────────────────────────────────


class TestUpdateInventory:
    def test_update_inventory_delegates_to_create_observation(
        self, mock_farmos_client, monkeypatch
    ):
        """update_inventory delegates to create_observation and returns its result."""
        import server

        plant = make_plant_asset(
            name="25 APR 2025 - Comfrey - P2R3.15-21",
            inventory_count=6,
        )
        log_id = make_uuid()

        mock_farmos_client.fetch_by_name.return_value = [plant]
        mock_farmos_client.get_section_uuid.return_value = make_uuid()
        mock_farmos_client.log_exists.return_value = None
        mock_farmos_client.create_quantity.return_value = make_uuid()
        mock_farmos_client.create_observation_log.return_value = log_id

        monkeypatch.setattr(server, "get_client", lambda: mock_farmos_client)

        result = json.loads(server.update_inventory(
            plant_name="25 APR 2025 - Comfrey - P2R3.15-21",
            new_count=4,
            notes="2 lost to frost",
        ))

        assert result["status"] == "created"
        assert result["log_id"] == log_id
        assert result["count"] == 4
        # Verify create_observation was called (quantity created via the delegation)
        mock_farmos_client.create_quantity.assert_called_once()

    def test_update_inventory_adds_notes_prefix(
        self, mock_farmos_client, monkeypatch
    ):
        """update_inventory prepends 'Inventory update: ' to the notes."""
        import server

        plant = make_plant_asset(
            name="25 APR 2025 - Sweet Potato - P2R2.0-3",
            inventory_count=10,
        )

        mock_farmos_client.fetch_by_name.return_value = [plant]
        mock_farmos_client.get_section_uuid.return_value = make_uuid()
        mock_farmos_client.log_exists.return_value = None
        mock_farmos_client.create_quantity.return_value = make_uuid()
        mock_farmos_client.create_observation_log.return_value = make_uuid()

        monkeypatch.setattr(server, "get_client", lambda: mock_farmos_client)

        result = json.loads(server.update_inventory(
            plant_name="25 APR 2025 - Sweet Potato - P2R2.0-3",
            new_count=8,
            notes="snails ate two",
        ))

        assert result["notes"] == "Inventory update: snails ate two"
