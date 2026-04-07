"""
Tests for the MCP server write tools: create_observation, create_activity,
create_plant, create_seed, and update_inventory.

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
        assert result["log_name"] == "Observation P2R2.0-3 \u2014 Pigeon Pea \u2014 2026-03-09"

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

    def test_create_observation_different_date_allowed(self, mock_farmos_client, monkeypatch):
        """A new observation on a different date is NOT blocked by an older one."""
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
        # No existing log for this date — older observation exists but with different name
        mock_farmos_client.log_exists.return_value = None
        mock_farmos_client.create_quantity.return_value = qty_id
        mock_farmos_client.create_observation_log.return_value = log_id

        monkeypatch.setattr(server, "get_client", lambda: mock_farmos_client)

        result = json.loads(server.create_observation(
            plant_name="25 APR 2025 - Pigeon Pea - P2R2.0-3",
            count=2,
            notes="updated count after new observation",
            date="2026-03-17",
        ))

        assert result["status"] == "created"
        assert result["log_name"] == "Observation P2R2.0-3 \u2014 Pigeon Pea \u2014 2026-03-17"
        mock_farmos_client.create_quantity.assert_called_once()
        mock_farmos_client.create_observation_log.assert_called_once()


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


# ── archive_plant ────────────────────────────────────────────


class TestArchivePlant:
    def test_archive_plant_happy_path(self, mock_farmos_client, monkeypatch):
        """Successful archive changes status and returns confirmation."""
        import server

        plant_name = "25 APR 2025 - Pigeon Pea - P2R2.0-3"
        plant_uuid = make_uuid()

        # archive_plant returns the updated asset dict
        mock_farmos_client.archive_plant.return_value = {
            "type": "asset--plant",
            "id": plant_uuid,
            "attributes": {
                "name": plant_name,
                "status": "archived",
                "inventory": [],
                "notes": {},
            },
            "relationships": {
                "plant_type": {"data": [{"type": "taxonomy_term--plant_type", "id": make_uuid()}]},
            },
        }

        monkeypatch.setattr(server, "get_client", lambda: mock_farmos_client)

        result = json.loads(server.archive_plant(plant_name=plant_name))

        assert result["status"] == "archived"
        assert result["plant"]["id"] == plant_uuid
        assert result["plant"]["species"] == "Pigeon Pea"
        assert result["plant"]["section"] == "P2R2.0-3"
        mock_farmos_client.archive_plant.assert_called_once_with(plant_name)
        # No activity log when no reason given
        mock_farmos_client.create_activity_log.assert_not_called()

    def test_archive_plant_not_found(self, mock_farmos_client, monkeypatch):
        """Returns error JSON when the plant asset does not exist."""
        import server

        mock_farmos_client.archive_plant.side_effect = ValueError(
            "Plant asset 'NONEXISTENT' not found in farmOS"
        )

        monkeypatch.setattr(server, "get_client", lambda: mock_farmos_client)

        result = json.loads(server.archive_plant(plant_name="NONEXISTENT"))

        assert "error" in result
        assert "not found" in result["error"]
        mock_farmos_client.create_activity_log.assert_not_called()

    def test_archive_plant_with_reason(self, mock_farmos_client, monkeypatch):
        """When reason is provided, creates an activity log explaining why."""
        import server

        plant_name = "25 APR 2025 - Comfrey - P2R3.15-21"
        plant_uuid = make_uuid()
        section_uuid = make_uuid()
        log_id = make_uuid()

        mock_farmos_client.archive_plant.return_value = {
            "type": "asset--plant",
            "id": plant_uuid,
            "attributes": {
                "name": plant_name,
                "status": "archived",
                "inventory": [],
                "notes": {},
            },
            "relationships": {
                "plant_type": {"data": [{"type": "taxonomy_term--plant_type", "id": make_uuid()}]},
            },
        }
        mock_farmos_client.get_section_uuid.return_value = section_uuid
        mock_farmos_client.create_activity_log.return_value = log_id

        monkeypatch.setattr(server, "get_client", lambda: mock_farmos_client)

        result = json.loads(server.archive_plant(
            plant_name=plant_name,
            reason="Died from frost damage",
        ))

        assert result["status"] == "archived"
        assert result["activity_log"]["id"] == log_id
        assert result["activity_log"]["reason"] == "Died from frost damage"
        assert "Comfrey" in result["activity_log"]["name"]
        assert "P2R3.15-21" in result["activity_log"]["name"]

        mock_farmos_client.create_activity_log.assert_called_once()
        call_kwargs = mock_farmos_client.create_activity_log.call_args
        assert call_kwargs.kwargs.get("notes") or call_kwargs[1].get("notes") == "Died from frost damage"


# ── create_seed ──────────────────────────────────────────────


class TestCreateSeed:
    def test_create_seed_happy_path(self, mock_farmos_client, monkeypatch):
        """Successful seed creation returns seed asset details."""
        import server

        pt_uuid = make_uuid()
        seed_id = make_uuid()
        qty_id = make_uuid()
        log_id = make_uuid()

        mock_farmos_client.fetch_by_name.side_effect = [
            [{"id": pt_uuid}],  # plant type lookup
            [],                  # seed asset existence check (not found)
        ]
        mock_farmos_client.create_seed_asset.return_value = seed_id
        mock_farmos_client.create_seed_quantity.return_value = qty_id
        mock_farmos_client.create_seed_observation_log.return_value = log_id

        monkeypatch.setattr(server, "get_client", lambda: mock_farmos_client)

        result = json.loads(server.create_seed(
            species="Pigeon Pea",
            quantity_grams=500,
            source="Greenpatch",
            source_type="commercial",
            notes="Organic certified",
            date="2026-03-13",
        ))

        assert result["status"] == "created"
        assert result["seed"]["id"] == seed_id
        assert result["seed"]["name"] == "Pigeon Pea Seeds"
        assert result["inventory"]["quantity_grams"] == 500
        assert result["inventory"]["adjustment"] == "reset"
        assert result["source_type"] == "commercial"

        mock_farmos_client.create_seed_asset.assert_called_once()
        mock_farmos_client.create_seed_quantity.assert_called_once_with(
            seed_id, 500, "grams", "reset"
        )

    def test_create_seed_restock_existing(self, mock_farmos_client, monkeypatch):
        """Restocking existing seed uses increment adjustment."""
        import server

        existing_id = make_uuid()
        qty_id = make_uuid()
        log_id = make_uuid()

        mock_farmos_client.fetch_by_name.side_effect = [
            [{"id": make_uuid()}],            # plant type found
            [{"id": existing_id}],             # seed asset exists
        ]
        mock_farmos_client.create_seed_quantity.return_value = qty_id
        mock_farmos_client.create_seed_observation_log.return_value = log_id

        monkeypatch.setattr(server, "get_client", lambda: mock_farmos_client)

        result = json.loads(server.create_seed(
            species="Pigeon Pea",
            quantity_grams=200,
            source="Farm harvest P2R3",
            source_type="harvest",
        ))

        assert result["status"] == "restocked"
        assert result["seed"]["id"] == existing_id
        assert result["inventory"]["adjustment"] == "increment"
        assert result["source_type"] == "harvest"
        mock_farmos_client.create_seed_asset.assert_not_called()

    def test_create_seed_stock_level(self, mock_farmos_client, monkeypatch):
        """Sachet seeds use stock_level quantity type."""
        import server

        seed_id = make_uuid()
        mock_farmos_client.fetch_by_name.side_effect = [
            [{"id": make_uuid()}],  # plant type
            [],                      # no existing seed
        ]
        mock_farmos_client.create_seed_asset.return_value = seed_id
        mock_farmos_client.create_seed_quantity.return_value = make_uuid()
        mock_farmos_client.create_seed_observation_log.return_value = make_uuid()

        monkeypatch.setattr(server, "get_client", lambda: mock_farmos_client)

        result = json.loads(server.create_seed(
            species="Tomato (Marmande)",
            stock_level="full",
            source="EDEN Seeds",
        ))

        assert result["status"] == "created"
        assert result["inventory"]["stock_level"] == "full"
        mock_farmos_client.create_seed_quantity.assert_called_once_with(
            seed_id, 1, "stock_level", "reset"
        )

    def test_create_seed_type_not_found(self, mock_farmos_client, monkeypatch):
        """Returns error when plant type doesn't exist."""
        import server

        mock_farmos_client.fetch_by_name.return_value = []

        monkeypatch.setattr(server, "get_client", lambda: mock_farmos_client)

        result = json.loads(server.create_seed(
            species="Nonexistent",
            quantity_grams=100,
        ))

        assert "error" in result
        assert "not found" in result["error"]
        mock_farmos_client.create_seed_asset.assert_not_called()

    def test_create_seed_no_quantity(self, mock_farmos_client, monkeypatch):
        """Returns error when neither quantity_grams nor stock_level provided."""
        import server

        monkeypatch.setattr(server, "get_client", lambda: mock_farmos_client)

        result = json.loads(server.create_seed(species="Pigeon Pea"))

        assert "error" in result
        assert "quantity_grams" in result["error"]

    def test_create_seed_exchange_source(self, mock_farmos_client, monkeypatch):
        """Exchange source type is correctly passed through."""
        import server

        mock_farmos_client.fetch_by_name.side_effect = [
            [{"id": make_uuid()}],  # plant type
            [],                      # no existing seed
        ]
        mock_farmos_client.create_seed_asset.return_value = make_uuid()
        mock_farmos_client.create_seed_quantity.return_value = make_uuid()
        mock_farmos_client.create_seed_observation_log.return_value = make_uuid()

        monkeypatch.setattr(server, "get_client", lambda: mock_farmos_client)

        result = json.loads(server.create_seed(
            species="Comfrey",
            quantity_grams=50,
            source="Minimba Farm",
            source_type="exchange",
        ))

        assert result["source_type"] == "exchange"
        assert result["source"] == "Minimba Farm"
