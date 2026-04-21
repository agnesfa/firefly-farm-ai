"""Tests for the batch observation tools.

Mirrors mcp-server-ts/plugins/farm-plugin/src/__tests__/batch-observations.test.ts.

The batch tools exist to collapse N single-submission tool calls into
one call for multi-submission flows. Trigger: Leah's April 14 walk,
which required ~45 tool calls through the single-submission tools.
"""

import json
from unittest.mock import MagicMock

import pytest

from server import import_observations_batch, update_observation_status_batch


# ── update_observation_status_batch ─────────────────────────────


class TestUpdateObservationStatusBatch:
    def test_single_updatestatus_call_with_n_entries(
        self, monkeypatch, mock_observe_client,
    ):
        mock_observe_client.update_status = MagicMock(
            return_value={"success": True, "updated": 3}
        )
        monkeypatch.setattr("server.get_observe_client", lambda: mock_observe_client)

        result = json.loads(update_observation_status_batch(
            submission_ids=["sub-a", "sub-b", "sub-c"],
            new_status="approved",
            reviewer="Claude",
            notes="batch",
        ))

        assert mock_observe_client.update_status.call_count == 1
        entries = mock_observe_client.update_status.call_args[0][0]
        assert len(entries) == 3
        assert entries[0] == {
            "submission_id": "sub-a",
            "status": "approved",
            "reviewer": "Claude",
            "notes": "batch",
        }
        assert result["status"] == "updated"
        assert result["submission_count"] == 3
        assert result["submission_ids"] == ["sub-a", "sub-b", "sub-c"]

    def test_deduplicates_submission_ids(
        self, monkeypatch, mock_observe_client,
    ):
        mock_observe_client.update_status = MagicMock(
            return_value={"success": True, "updated": 2}
        )
        monkeypatch.setattr("server.get_observe_client", lambda: mock_observe_client)

        update_observation_status_batch(
            submission_ids=["sub-a", "sub-a", "sub-b", "sub-a"],
            new_status="approved",
            reviewer="Claude",
        )

        entries = mock_observe_client.update_status.call_args[0][0]
        assert len(entries) == 2

    def test_rejects_invalid_status(self, mock_observe_client):
        result = json.loads(update_observation_status_batch(
            submission_ids=["sub-a"],
            new_status="wibble",
            reviewer="Claude",
        ))
        assert "Invalid status" in result["error"]

    def test_rejects_empty_list(self):
        result = json.loads(update_observation_status_batch(
            submission_ids=[],
            new_status="approved",
            reviewer="Claude",
        ))
        assert "at least one" in result["error"]

    def test_surfaces_update_status_errors(
        self, monkeypatch, mock_observe_client,
    ):
        mock_observe_client.update_status = MagicMock(
            return_value={"success": False, "error": "sheet locked"}
        )
        monkeypatch.setattr("server.get_observe_client", lambda: mock_observe_client)

        result = json.loads(update_observation_status_batch(
            submission_ids=["sub-a", "sub-b"],
            new_status="approved",
            reviewer="Claude",
        ))
        assert "sheet locked" in result["error"]
        assert result["submission_ids"] == ["sub-a", "sub-b"]


# ── import_observations_batch ──────────────────────────────────


class TestImportObservationsBatch:
    def test_processes_each_submission_and_aggregates(self, monkeypatch):
        """Verify the batch tool dispatches to import_observations per-id
        and aggregates the results into a single response."""
        responses = {
            "sub-1": json.dumps({
                "submission_id": "sub-1",
                "section_id": "P2R3.0-2",
                "total_actions": 2,
                "sheet_status": "imported",
                "photos_uploaded": 1,
                "species_reference_photos_updated": 0,
                "errors": None,
                "photo_pipeline": {
                    "media_files_fetched": 1,
                    "decode_failures": 0,
                    "photos_uploaded": 1,
                    "upload_errors": [],
                    "species_reference_photos_updated": 0,
                    "verification": {
                        "plantnet_key_present": True,
                        "botanical_lookup_size": 10,
                        "plantnet_api_calls": 1,
                        "photos_verified": 1,
                        "photos_rejected": 0,
                        "degraded": False,
                        "degraded_reason": "",
                    },
                },
            }),
            "sub-2": json.dumps({
                "submission_id": "sub-2",
                "section_id": "P2R3.2-9",
                "total_actions": 3,
                "sheet_status": "imported",
                "photos_uploaded": 2,
                "species_reference_photos_updated": 1,
                "errors": None,
                "photo_pipeline": {
                    "media_files_fetched": 2,
                    "decode_failures": 0,
                    "photos_uploaded": 2,
                    "upload_errors": [],
                    "species_reference_photos_updated": 1,
                    "verification": {
                        "plantnet_key_present": True,
                        "botanical_lookup_size": 10,
                        "plantnet_api_calls": 1,
                        "photos_verified": 1,
                        "photos_rejected": 0,
                        "degraded": False,
                        "degraded_reason": "",
                    },
                },
            }),
        }

        def fake_import(submission_id, reviewer="Claude", dry_run=False):
            return responses[submission_id]

        monkeypatch.setattr("server.import_observations", fake_import)

        result = json.loads(import_observations_batch(
            submission_ids=["sub-1", "sub-2"],
            reviewer="Claude",
            dry_run=False,
            continue_on_error=True,
        ))

        assert result["status"] == "ok"
        assert result["submitted"] == 2
        assert result["processed"] == 2
        assert result["succeeded"] == 2
        assert result["total_actions"] == 5
        assert len(result["submissions"]) == 2
        # Aggregated photo pipeline
        assert result["photo_pipeline"]["media_files_fetched"] == 3
        assert result["photo_pipeline"]["photos_uploaded"] == 3
        assert result["photo_pipeline"]["species_reference_photos_updated"] == 1
        assert result["photo_pipeline"]["verification"]["photos_verified"] == 2
        assert result["photo_pipeline"]["verification"]["plantnet_key_present"] is True

    def test_continues_past_failed_submission(self, monkeypatch):
        call_count = {"n": 0}

        def fake_import(submission_id, reviewer="Claude", dry_run=False):
            call_count["n"] += 1
            if call_count["n"] == 2:
                return json.dumps({"error": "not found"})
            return json.dumps({
                "submission_id": submission_id,
                "total_actions": 1,
                "photos_uploaded": 0,
                "species_reference_photos_updated": 0,
                "photo_pipeline": {"verification": {}},
            })

        monkeypatch.setattr("server.import_observations", fake_import)

        result = json.loads(import_observations_batch(
            submission_ids=["sub-1", "sub-2", "sub-3"],
            continue_on_error=True,
        ))

        assert result["processed"] == 3
        assert result["succeeded"] == 2
        assert result["status"] == "partial"
        assert result["errors"] is not None
        assert any("sub-2" in e for e in result["errors"])

    def test_aborts_on_error_when_continue_on_error_false(self, monkeypatch):
        call_count = {"n": 0}

        def fake_import(submission_id, reviewer="Claude", dry_run=False):
            call_count["n"] += 1
            if call_count["n"] == 2:
                return json.dumps({"error": "not found"})
            return json.dumps({
                "submission_id": submission_id,
                "total_actions": 1,
                "photo_pipeline": {"verification": {}},
            })

        monkeypatch.setattr("server.import_observations", fake_import)

        result = json.loads(import_observations_batch(
            submission_ids=["sub-1", "sub-2", "sub-3"],
            continue_on_error=False,
        ))

        # Stopped at the second submission
        assert result["processed"] == 2
        assert result["succeeded"] == 1
        assert call_count["n"] == 2  # didn't reach sub-3

    def test_rejects_empty_list(self):
        result = json.loads(import_observations_batch(submission_ids=[]))
        assert "at least one" in result["error"]

    def test_deduplicates_submission_ids(self, monkeypatch):
        seen = []

        def fake_import(submission_id, reviewer="Claude", dry_run=False):
            seen.append(submission_id)
            return json.dumps({
                "submission_id": submission_id,
                "total_actions": 1,
                "photo_pipeline": {"verification": {}},
            })

        monkeypatch.setattr("server.import_observations", fake_import)

        import_observations_batch(submission_ids=["a", "a", "b", "a", "b"])

        assert seen == ["a", "b"]

    # ── ADR 0007 Fix 6 — batch-size cap ─────────────────────────

    def test_fix6_refuses_batch_larger_than_5(self, monkeypatch):
        called = []
        monkeypatch.setattr(
            "server.import_observations",
            lambda submission_id, reviewer="Claude", dry_run=False: called.append(submission_id) or "{}",
        )

        result = json.loads(import_observations_batch(
            submission_ids=["s1", "s2", "s3", "s4", "s5", "s6"],
        ))

        assert "Batch size 6 exceeds limit 5" in result["error"]
        assert "60s MCP timeout" in result["reason"]
        assert result["submitted_count"] == 6
        assert result["limit"] == 5
        assert called == []  # importer never invoked

    def test_fix6_accepts_batch_of_exactly_5(self, monkeypatch):
        monkeypatch.setattr(
            "server.import_observations",
            lambda submission_id, reviewer="Claude", dry_run=False: json.dumps({
                "submission_id": submission_id,
                "total_actions": 1,
                "photo_pipeline": {"verification": {}},
            }),
        )

        result = json.loads(import_observations_batch(
            submission_ids=["s1", "s2", "s3", "s4", "s5"],
            dry_run=True,
        ))

        assert "error" not in result
        assert result["submitted"] == 5

    def test_fix6_dedup_runs_before_size_check(self, monkeypatch):
        monkeypatch.setattr(
            "server.import_observations",
            lambda submission_id, reviewer="Claude", dry_run=False: json.dumps({
                "submission_id": submission_id,
                "total_actions": 1,
                "photo_pipeline": {"verification": {}},
            }),
        )

        # 6 entries, only 3 unique → passes
        result = json.loads(import_observations_batch(
            submission_ids=["a", "b", "c", "a", "b", "c"],
            dry_run=True,
        ))

        assert "error" not in result
        assert result["submitted"] == 3
