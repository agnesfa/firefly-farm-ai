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
        assert action["section"] == "P2R3.15-21"
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
                "plant": {"name": "09 MAR 2026 - Macadamia - P2R3.15-21"},
            })

        monkeypatch.setattr(server, "create_plant", fake_create_plant)

        result = json.loads(import_observations(submission_id=sub_id))

        assert result["total_actions"] == 1
        action = result["actions"][0]
        assert action["type"] == "create_plant"
        assert action["species"] == "Macadamia"
        assert action["count"] == 2
        assert action["result"] == "created"
        assert action["plant_name"] == "09 MAR 2026 - Macadamia - P2R3.15-21"

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
                "plant": {"name": "09 MAR 2026 - Comfrey - P2R3.15-21"},
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
            name="25 APR 2025 - Pigeon Pea - P2R3.15-21",
            inventory_count=5,
        )
        mock_farmos_client.get_plant_assets.return_value = [plant]

        log_id = _mock_tool_success(monkeypatch, "create_observation")

        result = json.loads(import_observations(submission_id=sub_id))

        assert result["total_actions"] == 1
        action = result["actions"][0]
        assert action["type"] == "observation"
        assert action["plant_name"] == "25 APR 2025 - Pigeon Pea - P2R3.15-21"
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
        plant = make_plant_asset(name="25 APR 2025 - Pigeon Pea - P2R3.15-21", inventory_count=5)
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


# ── Photo pipeline (Step 1 + 2 from photo-pipeline-and-plant-id-design.md) ──


import base64


# A 1×1 transparent PNG, just enough to exercise the decode path.
_TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _media_file(filename="photo.jpg", b64=None):
    return {
        "filename": filename,
        "mime_type": "image/jpeg",
        "data_base64": b64 or _TINY_PNG_B64,
    }


class TestPhotoPipeline:
    """Regression tests for the photo pipeline wiring in import_observations.

    See ``claude-docs/photo-pipeline-and-plant-id-design.md`` — Steps 1 + 2.
    These tests lock in:
      * photos are fetched once per submission
      * decoded from base64 and uploaded to every farmOS log created
      * the latest photo per species lands on the plant_type taxonomy term
      * photo failures never block observation import
      * submissions without media files never touch get_media
    """

    def _setup_media(self, monkeypatch, mock_farmos_client, mock_observe_client):
        """Install a get_media mock, upload_file recorder, and PlantNet bypass."""
        mock_observe_client.get_media = MagicMock(return_value={
            "success": True,
            "files": [_media_file("first.jpg"), _media_file("second.jpg")],
        })
        uploaded = []

        def fake_upload(entity_type, entity_id, field_name, filename, binary_data, mime_type="image/jpeg"):
            uploaded.append({
                "entity_type": entity_type,
                "entity_id": entity_id,
                "field_name": field_name,
                "filename": filename,
                "bytes_len": len(binary_data),
                "mime_type": mime_type,
            })
            return f"file-uuid-{len(uploaded)}"

        mock_farmos_client.upload_file = fake_upload
        mock_farmos_client.get_plant_type_uuid = MagicMock(return_value="pt-uuid-pigeonpea")

        # Bypass PlantNet verification in tests — always approve photos.
        # PlantNet verification is tested separately in test_plantnet_verify.py.
        import plantnet_verify
        monkeypatch.setattr(
            plantnet_verify, "verify_species_photo",
            lambda *args, **kwargs: {"verified": True, "plantnet_top": "", "confidence": 1.0, "reason": "test_bypass"},
        )
        return uploaded

    def test_photos_uploaded_to_activity_log_case_a(
        self, monkeypatch, mock_farmos_client, mock_observe_client,
    ):
        """Case A (section comment) with media_files → upload to activity log."""
        sub_id = "sub-photo-a"
        obs = make_observation(
            species="",
            section_notes="Weeds growing near row edge",
            submission_id=sub_id,
            status="approved",
            media_files="first.jpg,second.jpg",
        )
        mock_observe_client.list_observations.return_value = {
            "success": True,
            "observations": [obs],
        }
        _patch_basics(monkeypatch, mock_farmos_client, mock_observe_client)
        uploaded = self._setup_media(monkeypatch, mock_farmos_client, mock_observe_client)
        activity_log_id = _mock_tool_success(monkeypatch, "create_activity")

        result = json.loads(import_observations(submission_id=sub_id))

        assert result["photos_uploaded"] == 2
        assert result["submission_media_fetched"] == 2
        assert result["species_reference_photos_updated"] == 0  # No species
        assert result["actions"][0]["photos_uploaded"] == 2
        # Both files landed on the activity log
        assert [u["entity_type"] for u in uploaded] == [
            "log/activity", "log/activity",
        ]
        assert all(u["entity_id"] == activity_log_id for u in uploaded)
        assert all(u["field_name"] == "image" for u in uploaded)
        assert [u["filename"] for u in uploaded] == ["first.jpg", "second.jpg"]
        # Each upload decoded to >0 bytes (the tiny PNG)
        assert all(u["bytes_len"] > 0 for u in uploaded)

    def test_photos_uploaded_and_species_reference_case_c(
        self, monkeypatch, mock_farmos_client, mock_observe_client,
    ):
        """Case C (inventory update) attaches photos to observation log AND
        refreshes the plant_type taxonomy reference photo."""
        sub_id = "sub-photo-c"
        obs = make_observation(
            species="Pigeon Pea",
            new_count=4,
            previous_count=3,
            submission_id=sub_id,
            status="approved",
            media_files="first.jpg,second.jpg",
        )
        mock_observe_client.list_observations.return_value = {
            "success": True,
            "observations": [obs],
        }
        _patch_basics(monkeypatch, mock_farmos_client, mock_observe_client)
        uploaded = self._setup_media(monkeypatch, mock_farmos_client, mock_observe_client)

        plant = make_plant_asset(
            name="25 APR 2025 - Pigeon Pea - P2R3.15-21",
        )
        mock_farmos_client.get_plant_assets.return_value = [plant]
        obs_log_id = _mock_tool_success(monkeypatch, "create_observation")

        result = json.loads(import_observations(submission_id=sub_id))

        assert result["photos_uploaded"] == 2
        assert result["species_reference_photos_updated"] == 1
        # 2 photos to observation log + 1 photo to taxonomy term
        log_uploads = [u for u in uploaded if u["entity_type"] == "log/observation"]
        taxo_uploads = [u for u in uploaded if u["entity_type"] == "taxonomy_term/plant_type"]
        assert len(log_uploads) == 2
        assert all(u["entity_id"] == obs_log_id for u in log_uploads)
        assert len(taxo_uploads) == 1
        assert taxo_uploads[0]["entity_id"] == "pt-uuid-pigeonpea"

    def test_no_media_files_skips_drive_fetch(
        self, monkeypatch, mock_farmos_client, mock_observe_client,
    ):
        """Observations without media_files → get_media is never called."""
        sub_id = "sub-no-media"
        obs = make_observation(
            species="",
            section_notes="No photo here",
            submission_id=sub_id,
            status="approved",
            media_files="",
        )
        mock_observe_client.list_observations.return_value = {
            "success": True,
            "observations": [obs],
        }
        _patch_basics(monkeypatch, mock_farmos_client, mock_observe_client)
        mock_observe_client.get_media = MagicMock(return_value={"success": True, "files": []})
        _mock_tool_success(monkeypatch, "create_activity")

        result = json.loads(import_observations(submission_id=sub_id))

        mock_observe_client.get_media.assert_not_called()
        assert result["photos_uploaded"] == 0
        assert result["submission_media_fetched"] == 0

    def test_upload_failure_does_not_block_import(
        self, monkeypatch, mock_farmos_client, mock_observe_client,
    ):
        """upload_file raising must not abort the observation import."""
        sub_id = "sub-photo-fail"
        obs = make_observation(
            species="",
            section_notes="Photo upload will fail",
            submission_id=sub_id,
            status="approved",
            media_files="photo.jpg",
        )
        mock_observe_client.list_observations.return_value = {
            "success": True,
            "observations": [obs],
        }
        _patch_basics(monkeypatch, mock_farmos_client, mock_observe_client)
        mock_observe_client.get_media = MagicMock(return_value={
            "success": True,
            "files": [_media_file("photo.jpg")],
        })
        mock_farmos_client.upload_file = MagicMock(side_effect=RuntimeError("farmOS down"))
        _mock_tool_success(monkeypatch, "create_activity")

        result = json.loads(import_observations(submission_id=sub_id))

        assert result["total_actions"] == 1
        assert result["actions"][0]["result"] == "created"
        assert result["photos_uploaded"] == 0  # upload failed but import succeeded
        assert result["errors"] is None  # photo failures don't surface as errors

    def test_undecodable_media_is_skipped(
        self, monkeypatch, mock_farmos_client, mock_observe_client,
    ):
        """Corrupt base64 payload is skipped without crashing the import."""
        sub_id = "sub-photo-corrupt"
        obs = make_observation(
            species="",
            section_notes="Corrupt photo",
            submission_id=sub_id,
            status="approved",
            media_files="broken.jpg",
        )
        mock_observe_client.list_observations.return_value = {
            "success": True,
            "observations": [obs],
        }
        _patch_basics(monkeypatch, mock_farmos_client, mock_observe_client)
        mock_observe_client.get_media = MagicMock(return_value={
            "success": True,
            "files": [{"filename": "broken.jpg", "mime_type": "image/jpeg", "data_base64": "@@not-base64@@"}],
        })
        uploaded = []

        def fake_upload(*args, **kwargs):
            uploaded.append(True)
            return "file-uuid"

        mock_farmos_client.upload_file = fake_upload
        _mock_tool_success(monkeypatch, "create_activity")

        result = json.loads(import_observations(submission_id=sub_id))

        assert uploaded == []  # decoder skipped the corrupt file
        assert result["total_actions"] == 1
        assert result["actions"][0]["result"] == "created"

    def test_data_url_prefix_is_stripped(
        self, monkeypatch, mock_farmos_client, mock_observe_client,
    ):
        """Legacy ``data:image/jpeg;base64,XXX`` payloads are decoded correctly."""
        from server import _decode_media_file

        raw = _decode_media_file({
            "filename": "legacy.jpg",
            "mime_type": "image/jpeg",
            "data_base64": f"data:image/jpeg;base64,{_TINY_PNG_B64}",
        })
        assert raw is not None
        filename, mime_type, binary = raw
        assert filename == "legacy.jpg"
        assert mime_type == "image/jpeg"
        assert len(binary) > 0
