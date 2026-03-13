"""
Tests for the import_observations composite tool in the MCP server.

The import_observations tool orchestrates:
  1. Fetching observations from the Google Sheet (via ObservationClient)
  2. Routing each observation to the correct farmOS action (Case A/B/C)
  3. Updating the Sheet status after import
  4. Optionally regenerating QR landing pages

We monkeypatch get_client(), get_observe_client(), and the downstream tool
functions (create_observation, create_activity, create_plant) to avoid
deep call chains into farmOS and Apps Script.
"""

import json
import os
from unittest.mock import MagicMock

import pytest

from tests.conftest import make_observation, make_plant_asset, make_uuid

# We import the tool function directly — it returns a JSON string.
import server
from server import import_observations


# ── Helpers ───────────────────────────────────────────────────


def _patch_basics(monkeypatch, mock_farmos_client, mock_observe_client):
    """Wire up the three standard monkeypatches for import tests."""
    monkeypatch.setattr(server, "get_client", lambda: mock_farmos_client)
    monkeypatch.setattr(server, "get_observe_client", lambda: mock_observe_client)
    # Prevent auto-regen from trying to find the project venv
    monkeypatch.setattr(server, "_MAIN_VENV_PYTHON", "/nonexistent/venv/bin/python3")


def _mock_tool_success(monkeypatch, tool_attr, log_id=None):
    """Replace a tool function on the server module with one that returns success JSON."""
    lid = log_id or make_uuid()

    def fake_tool(**kwargs):
        return json.dumps({"status": "created", "log_id": lid})

    monkeypatch.setattr(server, tool_attr, fake_tool)
    return lid


# ── Case routing ──────────────────────────────────────────────


class TestCaseRouting:

    def test_import_case_a_section_comment(self, monkeypatch, mock_farmos_client, mock_observe_client):
        """Observation with no species but section_notes → creates activity."""
        sub_id = "sub-001"
        obs = make_observation(
            species="",
            section_notes="Weeds growing near row edge",
            submission_id=sub_id,
            status="approved",
        )
        mock_observe_client.list_observations.return_value = {
            "success": True,
            "observations": [obs],
        }
        _patch_basics(monkeypatch, mock_farmos_client, mock_observe_client)
        log_id = _mock_tool_success(monkeypatch, "create_activity")

        result = json.loads(import_observations(submission_id=sub_id))

        assert result["total_actions"] == 1
        action = result["actions"][0]
        assert action["type"] == "activity"
        assert action["section"] == "P2R3.14-21"
        assert action["result"] == "created"

    def test_import_case_b_new_plant(self, monkeypatch, mock_farmos_client, mock_observe_client):
        """Observation with mode='new_plant' → creates plant."""
        sub_id = "sub-002"
        obs = make_observation(
            species="Macadamia",
            mode="new_plant",
            new_count=2,
            previous_count=0,
            submission_id=sub_id,
            status="approved",
        )
        mock_observe_client.list_observations.return_value = {
            "success": True,
            "observations": [obs],
        }
        _patch_basics(monkeypatch, mock_farmos_client, mock_observe_client)

        def fake_create_plant(**kwargs):
            return json.dumps({
                "status": "created",
                "plant": {"name": "09 MAR 2026 - Macadamia - P2R3.14-21"},
            })

        monkeypatch.setattr(server, "create_plant", fake_create_plant)

        result = json.loads(import_observations(submission_id=sub_id))

        assert result["total_actions"] == 1
        action = result["actions"][0]
        assert action["type"] == "create_plant"
        assert action["species"] == "Macadamia"
        assert action["count"] == 2
        assert action["result"] == "created"
        assert action["plant_name"] == "09 MAR 2026 - Macadamia - P2R3.14-21"

    def test_import_case_b_inferred(self, monkeypatch, mock_farmos_client, mock_observe_client):
        """Observation with previous_count=0, new_count=3 → inferred as new plant."""
        sub_id = "sub-003"
        obs = make_observation(
            species="Comfrey",
            mode="full_inventory",
            previous_count=0,
            new_count=3,
            submission_id=sub_id,
            status="reviewed",
        )
        mock_observe_client.list_observations.return_value = {
            "success": True,
            "observations": [obs],
        }
        _patch_basics(monkeypatch, mock_farmos_client, mock_observe_client)

        def fake_create_plant(**kwargs):
            return json.dumps({
                "status": "created",
                "plant": {"name": "09 MAR 2026 - Comfrey - P2R3.14-21"},
            })

        monkeypatch.setattr(server, "create_plant", fake_create_plant)

        result = json.loads(import_observations(submission_id=sub_id))

        assert result["total_actions"] == 1
        action = result["actions"][0]
        assert action["type"] == "create_plant"
        assert action["count"] == 3
        assert action["result"] == "created"

    def test_import_case_c_inventory_update(self, monkeypatch, mock_farmos_client, mock_observe_client):
        """Observation with species + changed count → creates observation."""
        sub_id = "sub-004"
        obs = make_observation(
            species="Pigeon Pea",
            new_count=3,
            previous_count=5,
            submission_id=sub_id,
            status="approved",
        )
        mock_observe_client.list_observations.return_value = {
            "success": True,
            "observations": [obs],
        }
        _patch_basics(monkeypatch, mock_farmos_client, mock_observe_client)

        # Case C looks up the plant asset via the client
        plant = make_plant_asset(
            name="25 APR 2025 - Pigeon Pea - P2R3.14-21",
            inventory_count=5,
        )
        mock_farmos_client.get_plant_assets.return_value = [plant]

        log_id = _mock_tool_success(monkeypatch, "create_observation")

        result = json.loads(import_observations(submission_id=sub_id))

        assert result["total_actions"] == 1
        action = result["actions"][0]
        assert action["type"] == "observation"
        assert action["plant_name"] == "25 APR 2025 - Pigeon Pea - P2R3.14-21"
        assert action["previous_count"] == 5
        assert action["new_count"] == 3
        assert action["result"] == "created"
        assert action["log_id"] == log_id


# ── Status validation ─────────────────────────────────────────


class TestStatusValidation:

    def test_import_rejects_pending_status(self, monkeypatch, mock_farmos_client, mock_observe_client):
        """Observations with status='pending' are rejected before any farmOS calls."""
        sub_id = "sub-reject"
        obs = make_observation(
            species="Pigeon Pea",
            status="pending",
            submission_id=sub_id,
        )
        mock_observe_client.list_observations.return_value = {
            "success": True,
            "observations": [obs],
        }
        _patch_basics(monkeypatch, mock_farmos_client, mock_observe_client)

        result = json.loads(import_observations(submission_id=sub_id))

        assert "error" in result
        assert "unexpected statuses" in result["error"]
        assert "pending" in result["error"]

    def test_import_accepts_approved(self, monkeypatch, mock_farmos_client, mock_observe_client):
        """Observations with status='approved' proceed normally."""
        sub_id = "sub-approved"
        obs = make_observation(
            species="",
            section_notes="All good",
            status="approved",
            submission_id=sub_id,
        )
        mock_observe_client.list_observations.return_value = {
            "success": True,
            "observations": [obs],
        }
        _patch_basics(monkeypatch, mock_farmos_client, mock_observe_client)
        _mock_tool_success(monkeypatch, "create_activity")

        result = json.loads(import_observations(submission_id=sub_id))

        assert "error" not in result
        assert result["total_actions"] == 1


# ── Sheet lifecycle ───────────────────────────────────────────


class TestSheetLifecycle:

    def test_import_updates_sheet_status(self, monkeypatch, mock_farmos_client, mock_observe_client):
        """After successful import, update_status is called with 'imported'."""
        sub_id = "sub-sheet"
        obs = make_observation(
            species="",
            section_notes="Mulch needed",
            status="approved",
            submission_id=sub_id,
        )
        mock_observe_client.list_observations.return_value = {
            "success": True,
            "observations": [obs],
        }
        _patch_basics(monkeypatch, mock_farmos_client, mock_observe_client)
        _mock_tool_success(monkeypatch, "create_activity")

        result = json.loads(import_observations(submission_id=sub_id))

        # Verify update_status was called
        mock_observe_client.update_status.assert_called_once()
        call_args = mock_observe_client.update_status.call_args[0][0]
        assert call_args[0]["submission_id"] == sub_id
        assert call_args[0]["status"] == "imported"

    def test_import_sheet_status_partial_on_error(self, monkeypatch, mock_farmos_client, mock_observe_client):
        """When update_status raises, sheet_status becomes 'partial'."""
        sub_id = "sub-partial"
        obs = make_observation(
            species="",
            section_notes="Some comment",
            status="approved",
            submission_id=sub_id,
        )
        mock_observe_client.list_observations.return_value = {
            "success": True,
            "observations": [obs],
        }
        mock_observe_client.update_status.side_effect = RuntimeError("Sheet API timeout")
        _patch_basics(monkeypatch, mock_farmos_client, mock_observe_client)
        _mock_tool_success(monkeypatch, "create_activity")

        result = json.loads(import_observations(submission_id=sub_id))

        assert result["sheet_status"] == "partial"
        assert any("Sheet status" in e for e in result["errors"])


# ── Dry run ───────────────────────────────────────────────────


class TestDryRun:

    def test_import_dry_run(self, monkeypatch, mock_farmos_client, mock_observe_client):
        """In dry_run mode: all actions get result='dry_run', no farmOS calls, no Sheet update."""
        sub_id = "sub-dry"
        obs_a = make_observation(
            species="",
            section_notes="Fence broken",
            status="approved",
            submission_id=sub_id,
        )
        obs_b = make_observation(
            species="Pigeon Pea",
            new_count=3,
            previous_count=5,
            status="approved",
            submission_id=sub_id,
        )
        mock_observe_client.list_observations.return_value = {
            "success": True,
            "observations": [obs_a, obs_b],
        }
        _patch_basics(monkeypatch, mock_farmos_client, mock_observe_client)

        # Plant lookup still needed for Case C even in dry_run
        plant = make_plant_asset(name="25 APR 2025 - Pigeon Pea - P2R3.14-21", inventory_count=5)
        mock_farmos_client.get_plant_assets.return_value = [plant]

        # Tool functions should NOT be called — set them to fail if invoked
        monkeypatch.setattr(server, "create_activity", lambda **kw: (_ for _ in ()).throw(AssertionError("should not be called")))
        monkeypatch.setattr(server, "create_observation", lambda **kw: (_ for _ in ()).throw(AssertionError("should not be called")))

        result = json.loads(import_observations(submission_id=sub_id, dry_run=True))

        assert result["dry_run"] is True
        assert result["total_actions"] == 2
        for action in result["actions"]:
            assert action["result"] == "dry_run"

        # Sheet should NOT be updated during dry run
        mock_observe_client.update_status.assert_not_called()
        mock_observe_client.delete_imported.assert_not_called()


# ── Error resilience ──────────────────────────────────────────


class TestErrorResilience:

    def test_import_empty_submission(self, monkeypatch, mock_farmos_client, mock_observe_client):
        """No observations for submission → error JSON."""
        sub_id = "sub-empty"
        mock_observe_client.list_observations.return_value = {
            "success": True,
            "observations": [],
        }
        _patch_basics(monkeypatch, mock_farmos_client, mock_observe_client)

        result = json.loads(import_observations(submission_id=sub_id))

        assert "error" in result
        assert sub_id in result["error"]

    def test_import_one_fails_others_succeed(self, monkeypatch, mock_farmos_client, mock_observe_client):
        """When one observation raises, others still process — partial results."""
        sub_id = "sub-mixed"
        obs_ok = make_observation(
            species="",
            section_notes="All fine here",
            status="approved",
            submission_id=sub_id,
        )
        obs_fail = make_observation(
            species="Macadamia",
            mode="new_plant",
            new_count=1,
            previous_count=0,
            status="approved",
            submission_id=sub_id,
        )
        mock_observe_client.list_observations.return_value = {
            "success": True,
            "observations": [obs_ok, obs_fail],
        }
        _patch_basics(monkeypatch, mock_farmos_client, mock_observe_client)

        # create_activity succeeds
        _mock_tool_success(monkeypatch, "create_activity")

        # create_plant raises an error
        def failing_create_plant(**kwargs):
            raise RuntimeError("farmOS connection reset")

        monkeypatch.setattr(server, "create_plant", failing_create_plant)

        result = json.loads(import_observations(submission_id=sub_id))

        assert result["total_actions"] == 2
        # First action succeeded
        assert result["actions"][0]["result"] == "created"
        # Second action has error
        assert result["actions"][1]["result"] == "error"
        assert result["errors"] is not None
        assert any("Macadamia" in e for e in result["errors"])


# ── Auto-regeneration ─────────────────────────────────────────


class TestAutoRegen:

    def test_import_no_regen_when_venv_missing(self, monkeypatch, mock_farmos_client, mock_observe_client):
        """When _MAIN_VENV_PYTHON does not exist → pages_regenerated contains hint message."""
        sub_id = "sub-noregen"
        obs = make_observation(
            species="",
            section_notes="Quick note",
            status="approved",
            submission_id=sub_id,
        )
        mock_observe_client.list_observations.return_value = {
            "success": True,
            "observations": [obs],
        }
        _patch_basics(monkeypatch, mock_farmos_client, mock_observe_client)
        _mock_tool_success(monkeypatch, "create_activity")

        # Ensure os.path.isfile returns False for the venv python
        original_isfile = os.path.isfile
        monkeypatch.setattr(
            os.path, "isfile",
            lambda p: False if p == "/nonexistent/venv/bin/python3" else original_isfile(p),
        )

        result = json.loads(import_observations(submission_id=sub_id))

        assert result["pages_regenerated"] is not None
        assert "regenerate_pages" in result["pages_regenerated"] or "Pages need regeneration" in result["pages_regenerated"]
