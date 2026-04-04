"""
Tests for the Farm Semantic Layer (Layer 3).

Tests pure metric computation functions — no I/O, no mocking needed.
Each test provides data and verifies the governed interpretation.
"""

import os
import sys
from datetime import datetime, timezone, timedelta

import pytest

# Ensure mcp-server is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from semantics import (
    assess_strata_coverage,
    assess_activity_recency,
    assess_succession_balance,
    assess_section_health,
    find_transplant_ready,
    detect_knowledge_gaps,
    detect_decision_gaps,
    detect_logging_gaps,
    clear_caches,
    load_semantics,
    _classify,
    _classify_recency,
)

AEST = timezone(timedelta(hours=10))

# ── Test fixtures ─────────────────────────────────────────────────

# Minimal semantics dict (mirrors farm_semantics.yaml structure)
SEMANTICS = {
    "section_health": {
        "strata_coverage": {
            "expected_strata": {"tree_section": 4, "open_section": 2},
            "thresholds": {"good": 0.75, "fair": 0.50, "poor": 0.25},
        },
        "activity_recency": {
            "thresholds": {"active": 14, "needs_attention": 30, "neglected": 60},
        },
    },
}

PLANT_TYPES_DB = {
    "Pigeon Pea": {"strata": "high", "succession_stage": "pioneer", "transplant_days": 60},
    "Macadamia": {"strata": "high", "succession_stage": "climax", "transplant_days": 365},
    "Ice Cream Bean": {"strata": "emergent", "succession_stage": "pioneer"},
    "Comfrey": {"strata": "low", "succession_stage": "secondary", "transplant_days": 45},
    "Tomato (Marmande)": {"strata": "medium", "succession_stage": "pioneer", "transplant_days": 60},
    "Forest Red Gum": {"strata": "emergent", "succession_stage": "climax"},
    "Sweet Potato": {"strata": "low", "succession_stage": "pioneer"},
    "Apple": {"strata": "high", "succession_stage": "secondary"},
}


def _plant(species, count=1, strata=None):
    """Helper to build a plant dict."""
    d = {"species": species, "count": count}
    if strata:
        d["strata"] = strata
    return d


# ── Strata Coverage ───────────────────────────────────────────────


class TestStrataCoverage:
    def test_full_tree_section_all_strata(self):
        """Tree section with all 4 strata → score 1.0, good."""
        plants = [
            _plant("Ice Cream Bean", 2),      # emergent
            _plant("Pigeon Pea", 4),           # high
            _plant("Tomato (Marmande)", 3),    # medium
            _plant("Comfrey", 5),              # low
        ]
        result = assess_strata_coverage(plants, PLANT_TYPES_DB, has_trees=True, semantics=SEMANTICS)
        assert result["score"] == 1.0
        assert result["status"] == "good"
        assert result["filled_strata"] == 4
        assert result["expected_strata"] == 4
        assert result["emergent"] == 2
        assert result["high"] == 4

    def test_open_section_two_strata(self):
        """Open section with medium + low → score 1.0, good."""
        plants = [
            _plant("Tomato (Marmande)", 6),    # medium
            _plant("Comfrey", 3),              # low
        ]
        result = assess_strata_coverage(plants, PLANT_TYPES_DB, has_trees=False, semantics=SEMANTICS)
        assert result["score"] == 1.0
        assert result["status"] == "good"
        assert result["expected_strata"] == 2

    def test_tree_section_missing_emergent(self):
        """3 of 4 strata → score 0.75, good."""
        plants = [
            _plant("Pigeon Pea", 4),           # high
            _plant("Tomato (Marmande)", 3),    # medium
            _plant("Sweet Potato", 2),         # low
        ]
        result = assess_strata_coverage(plants, PLANT_TYPES_DB, has_trees=True, semantics=SEMANTICS)
        assert result["score"] == 0.75
        assert result["status"] == "good"

    def test_tree_section_half_strata(self):
        """2 of 4 strata → score 0.5, fair."""
        plants = [
            _plant("Pigeon Pea", 4),           # high
            _plant("Comfrey", 2),              # low
        ]
        result = assess_strata_coverage(plants, PLANT_TYPES_DB, has_trees=True, semantics=SEMANTICS)
        assert result["score"] == 0.5
        assert result["status"] == "fair"

    def test_tree_section_one_stratum(self):
        """1 of 4 strata → score 0.25, poor."""
        plants = [_plant("Pigeon Pea", 4)]     # high only
        result = assess_strata_coverage(plants, PLANT_TYPES_DB, has_trees=True, semantics=SEMANTICS)
        assert result["score"] == 0.25
        assert result["status"] == "poor"

    def test_empty_section(self):
        """No plants → score 0.0, poor."""
        result = assess_strata_coverage([], PLANT_TYPES_DB, has_trees=True, semantics=SEMANTICS)
        assert result["score"] == 0.0
        assert result["status"] == "poor"

    def test_dead_plants_not_counted(self):
        """Plants with count=0 should not fill strata."""
        plants = [
            _plant("Ice Cream Bean", 0),       # dead emergent
            _plant("Pigeon Pea", 4),           # living high
            _plant("Comfrey", 2),              # living low
        ]
        result = assess_strata_coverage(plants, PLANT_TYPES_DB, has_trees=True, semantics=SEMANTICS)
        assert result["emergent"] == 0
        assert result["filled_strata"] == 2

    def test_unknown_species_uses_plant_strata(self):
        """If species not in DB, fall back to plant dict strata field."""
        plants = [_plant("Unknown Tree", 3, strata="emergent")]
        result = assess_strata_coverage(plants, PLANT_TYPES_DB, has_trees=True, semantics=SEMANTICS)
        assert result["emergent"] == 3


# ── Activity Recency ──────────────────────────────────────────────


class TestActivityRecency:
    def test_recent_activity(self):
        """Log from 5 days ago → active."""
        now = datetime(2026, 4, 4, 10, 0, tzinfo=AEST)
        logs = [{"timestamp": "2026-03-30T10:00:00+10:00"}]
        result = assess_activity_recency(logs, SEMANTICS, now=now)
        assert result["days_since_last"] == 5
        assert result["status"] == "active"

    def test_needs_attention(self):
        """Log from 20 days ago → needs_attention."""
        now = datetime(2026, 4, 4, 10, 0, tzinfo=AEST)
        logs = [{"timestamp": "2026-03-15T10:00:00+10:00"}]
        result = assess_activity_recency(logs, SEMANTICS, now=now)
        assert result["days_since_last"] == 20
        assert result["status"] == "needs_attention"

    def test_neglected(self):
        """Log from 90 days ago → neglected."""
        now = datetime(2026, 4, 4, 10, 0, tzinfo=AEST)
        logs = [{"timestamp": "2026-01-04T10:00:00+10:00"}]
        result = assess_activity_recency(logs, SEMANTICS, now=now)
        assert result["status"] == "neglected"

    def test_no_logs(self):
        """No logs → neglected with 9999 days."""
        result = assess_activity_recency([], SEMANTICS)
        assert result["days_since_last"] == 9999
        assert result["status"] == "neglected"

    def test_uses_most_recent_log(self):
        """Multiple logs → uses the most recent one."""
        now = datetime(2026, 4, 4, 10, 0, tzinfo=AEST)
        logs = [
            {"timestamp": "2026-01-01T10:00:00+10:00"},  # old
            {"timestamp": "2026-04-01T10:00:00+10:00"},  # recent
            {"timestamp": "2026-02-15T10:00:00+10:00"},  # middle
        ]
        result = assess_activity_recency(logs, SEMANTICS, now=now)
        assert result["days_since_last"] == 3
        assert result["status"] == "active"

    def test_unix_timestamp(self):
        """Handles Unix timestamp format."""
        now = datetime(2026, 4, 4, 10, 0, tzinfo=AEST)
        # Unix timestamp for 2026-04-01 00:00:00 UTC
        ts = str(int(datetime(2026, 4, 1, tzinfo=timezone.utc).timestamp()))
        logs = [{"timestamp": ts}]
        result = assess_activity_recency(logs, SEMANTICS, now=now)
        assert result["status"] == "active"


# ── Succession Balance ────────────────────────────────────────────


class TestSuccessionBalance:
    def test_pioneer_heavy(self):
        """Mostly pioneers → pioneer-heavy note."""
        plants = [
            _plant("Pigeon Pea", 5),           # pioneer
            _plant("Sweet Potato", 3),         # pioneer
            _plant("Comfrey", 2),              # secondary
        ]
        result = assess_succession_balance(plants, PLANT_TYPES_DB)
        assert result["pioneer"] == 8
        assert result["secondary"] == 2
        assert result["climax"] == 0
        assert result["percentages"]["pioneer"] == 80
        assert "pioneer" in result["note"].lower()

    def test_balanced_mix(self):
        """Even mix → balanced note."""
        plants = [
            _plant("Pigeon Pea", 3),           # pioneer
            _plant("Apple", 3),                # secondary
            _plant("Macadamia", 3),            # climax
        ]
        result = assess_succession_balance(plants, PLANT_TYPES_DB)
        assert result["note"] == "Balanced mix across succession stages"

    def test_climax_dominant(self):
        """Climax > 40% → mature."""
        plants = [
            _plant("Macadamia", 5),            # climax
            _plant("Forest Red Gum", 3),       # climax
            _plant("Pigeon Pea", 2),           # pioneer
        ]
        result = assess_succession_balance(plants, PLANT_TYPES_DB)
        assert result["percentages"]["climax"] == 80
        assert "climax" in result["note"].lower()

    def test_empty_plants(self):
        """No plants → appropriate note."""
        result = assess_succession_balance([], PLANT_TYPES_DB)
        assert result["total"] == 0
        assert "No plants" in result["note"]


# ── Section Health (Combined) ─────────────────────────────────────


class TestSectionHealth:
    def test_healthy_section(self):
        """Full strata + recent activity → overall good/active."""
        now = datetime(2026, 4, 4, 10, 0, tzinfo=AEST)
        plants = [
            _plant("Ice Cream Bean", 2),
            _plant("Pigeon Pea", 4),
            _plant("Tomato (Marmande)", 3),
            _plant("Comfrey", 5),
        ]
        logs = [{"timestamp": "2026-04-01T10:00:00+10:00"}]

        result = assess_section_health(plants, logs, PLANT_TYPES_DB, has_trees=True, semantics=SEMANTICS, now=now)
        assert result["strata_coverage"]["status"] == "good"
        assert result["activity_recency"]["status"] == "active"
        assert result["overall_status"] in ("good", "active")

    def test_neglected_section(self):
        """Good strata but neglected → overall neglected (worst wins)."""
        now = datetime(2026, 4, 4, 10, 0, tzinfo=AEST)
        plants = [
            _plant("Ice Cream Bean", 2),
            _plant("Pigeon Pea", 4),
            _plant("Tomato (Marmande)", 3),
            _plant("Comfrey", 5),
        ]
        logs = [{"timestamp": "2025-12-01T10:00:00+10:00"}]  # 4+ months ago

        result = assess_section_health(plants, logs, PLANT_TYPES_DB, has_trees=True, semantics=SEMANTICS, now=now)
        assert result["strata_coverage"]["status"] == "good"
        assert result["activity_recency"]["status"] == "neglected"
        assert result["overall_status"] == "neglected"


# ── Transplant Readiness ──────────────────────────────────────────


class TestTransplantReady:
    def test_ready_plant(self):
        """Plant older than transplant_days → ready."""
        now = datetime(2026, 4, 4, 10, 0, tzinfo=AEST)
        plants = [
            {"species": "Comfrey", "planted_date": "2026-01-01T00:00:00+10:00",
             "name": "01 JAN 2026 - Comfrey - NURS.SH1-2", "count": 3, "section": "NURS.SH1-2"},
        ]
        result = find_transplant_ready(plants, PLANT_TYPES_DB, now=now)
        assert len(result) == 1
        assert result[0]["species"] == "Comfrey"
        assert result[0]["days_overdue"] > 0

    def test_not_ready_plant(self):
        """Plant younger than transplant_days → not ready."""
        now = datetime(2026, 4, 4, 10, 0, tzinfo=AEST)
        plants = [
            {"species": "Macadamia", "planted_date": "2026-03-01T00:00:00+10:00",
             "name": "01 MAR 2026 - Macadamia - NURS.SH2-1", "count": 1, "section": "NURS.SH2-1"},
        ]
        result = find_transplant_ready(plants, PLANT_TYPES_DB, now=now)
        assert len(result) == 0  # 34 days < 365 transplant_days

    def test_no_transplant_days_skipped(self):
        """Species without transplant_days → skipped (not assessed)."""
        now = datetime(2026, 4, 4, 10, 0, tzinfo=AEST)
        plants = [
            {"species": "Forest Red Gum", "planted_date": "2025-01-01T00:00:00+10:00",
             "name": "test", "count": 1},
        ]
        result = find_transplant_ready(plants, PLANT_TYPES_DB, now=now)
        assert len(result) == 0  # no transplant_days for Forest Red Gum

    def test_sorted_by_most_overdue(self):
        """Results sorted by days_overdue descending."""
        now = datetime(2026, 4, 4, 10, 0, tzinfo=AEST)
        plants = [
            {"species": "Comfrey", "planted_date": "2026-02-01T00:00:00+10:00",
             "name": "a", "count": 2, "section": "NURS.SH1-1"},
            {"species": "Pigeon Pea", "planted_date": "2025-06-01T00:00:00+10:00",
             "name": "b", "count": 5, "section": "NURS.GR"},
        ]
        result = find_transplant_ready(plants, PLANT_TYPES_DB, now=now)
        assert len(result) == 2
        assert result[0]["species"] == "Pigeon Pea"  # most overdue


# ── Knowledge Gaps ────────────────────────────────────────────────


class TestKnowledgeGaps:
    def test_full_coverage(self):
        """All species covered → ratio 1.0."""
        species = ["Pigeon Pea", "Comfrey"]
        kb = [{"related_plants": "Pigeon Pea, Comfrey"}]
        result = detect_knowledge_gaps(species, kb)
        assert result["coverage_ratio"] == 1.0
        assert len(result["uncovered_species"]) == 0

    def test_partial_coverage(self):
        """Some species uncovered."""
        species = ["Pigeon Pea", "Comfrey", "Macadamia"]
        kb = [{"related_plants": "Pigeon Pea"}]
        result = detect_knowledge_gaps(species, kb)
        assert "Comfrey" in result["uncovered_species"]
        assert "Macadamia" in result["uncovered_species"]
        assert result["coverage_ratio"] == round(1/3, 2)

    def test_no_kb_entries(self):
        """No KB entries → all uncovered."""
        species = ["Pigeon Pea", "Comfrey"]
        result = detect_knowledge_gaps(species, [])
        assert result["coverage_ratio"] == 0.0
        assert len(result["uncovered_species"]) == 2

    def test_empty_field(self):
        """No species in field → ratio 0.0 (no divide by zero)."""
        result = detect_knowledge_gaps([], [{"related_plants": "Pigeon Pea"}])
        assert result["coverage_ratio"] == 0.0


# ── Decision Gaps ─────────────────────────────────────────────────


class TestDecisionGaps:
    def test_observations_without_tasks(self):
        """Observations exist but no pending tasks → gap detected."""
        observations = [{"name": "obs1"}]
        tasks = []
        gaps = detect_decision_gaps(tasks, observations)
        assert any("not be acted on" in g for g in gaps)

    def test_no_gaps(self):
        """Both tasks and observations exist → no gap about missing actions."""
        observations = [{"name": "obs1"}]
        tasks = [{"name": "task1", "status": "pending", "timestamp": ""}]
        gaps = detect_decision_gaps(tasks, observations)
        assert not any("not be acted on" in g for g in gaps)


# ── Classify helpers ──────────────────────────────────────────────


class TestClassify:
    def test_good(self):
        assert _classify(0.80, {"good": 0.75, "fair": 0.50, "poor": 0.25}) == "good"

    def test_fair(self):
        assert _classify(0.60, {"good": 0.75, "fair": 0.50, "poor": 0.25}) == "fair"

    def test_poor(self):
        assert _classify(0.20, {"good": 0.75, "fair": 0.50, "poor": 0.25}) == "poor"

    def test_recency_active(self):
        assert _classify_recency(10, {"active": 14, "needs_attention": 30}) == "active"

    def test_recency_needs_attention(self):
        assert _classify_recency(20, {"active": 14, "needs_attention": 30}) == "needs_attention"

    def test_recency_neglected(self):
        assert _classify_recency(45, {"active": 14, "needs_attention": 30}) == "neglected"


# ── Logging Gaps (Team Memory cross-reference) ───────────────────


class TestLoggingGaps:
    """Tests for detect_logging_gaps — Layer 4→5 validation."""

    def test_claimed_change_found_by_id(self):
        """Change with matching farmOS log ID → no gap."""
        sessions = [{
            "summary_id": "84",
            "user": "James",
            "timestamp": "2026-03-22T07:45:00Z",
            "farmos_changes": '[{"type":"activity","id":"057a6f34","details":"Seeding — P2R3.50-62"}]',
        }]
        logs = [{"id": "057a6f34-02e3-4ec5-b96a-9e269ba13354", "name": "Seeding — P2R3.50-62", "type": "activity"}]

        gaps = detect_logging_gaps(sessions, logs)
        assert len(gaps) == 0

    def test_claimed_change_missing(self):
        """Change claimed in team memory but not in farmOS → gap detected."""
        sessions = [{
            "summary_id": "89",
            "user": "James",
            "timestamp": "2026-03-25T23:04:00Z",
            "farmos_changes": '[{"type":"create_plant","details":"Lavender x5 — P2R4.6-14"}]',
        }]
        logs = []  # No matching logs

        gaps = detect_logging_gaps(sessions, logs)
        assert len(gaps) == 1
        assert gaps[0]["type"] == "claimed_not_found"
        assert gaps[0]["user"] == "James"
        assert gaps[0]["session_id"] == "89"
        assert "Lavender" in gaps[0]["claimed_change"]["details"]

    def test_empty_farmos_changes_skipped(self):
        """Sessions with no farmos_changes → no gaps reported."""
        sessions = [{
            "summary_id": "90",
            "user": "James",
            "timestamp": "2026-03-25T23:04:00Z",
            "farmos_changes": "",
        }]
        gaps = detect_logging_gaps(sessions, [])
        assert len(gaps) == 0

    def test_plain_text_farmos_changes_skipped(self):
        """Non-JSON farmos_changes (plain text) → gracefully skipped."""
        sessions = [{
            "summary_id": "91",
            "user": "James",
            "timestamp": "2026-03-25T23:46:00Z",
            "farmos_changes": "Updated some plants",
        }]
        gaps = detect_logging_gaps(sessions, [])
        assert len(gaps) == 0

    def test_section_filter(self):
        """Section filter limits analysis to matching changes."""
        sessions = [{
            "summary_id": "84",
            "user": "James",
            "timestamp": "2026-03-22T07:45:00Z",
            "farmos_changes": '[{"type":"activity","details":"Seeding — P2R3.50-62"},{"type":"create_plant","details":"Lavender x5 — P2R4.6-14"}]',
        }]
        logs = []

        # Filter to P2R4.6-14 only
        gaps = detect_logging_gaps(sessions, logs, section_filter="P2R4.6-14")
        assert len(gaps) == 1
        assert "P2R4.6-14" in gaps[0]["claimed_change"]["details"]

    def test_multiple_sessions_multiple_gaps(self):
        """Multiple sessions with missing changes → multiple gaps."""
        sessions = [
            {
                "summary_id": "84",
                "user": "James",
                "timestamp": "2026-03-22T00:00:00Z",
                "farmos_changes": '[{"type":"create_plant","details":"Lavender x5 — P2R4.6-14"}]',
            },
            {
                "summary_id": "86",
                "user": "James",
                "timestamp": "2026-03-22T08:00:00Z",
                "farmos_changes": '[{"type":"create_plant","details":"Geranium x2 — P2R4.6-14"}]',
            },
        ]
        logs = []

        gaps = detect_logging_gaps(sessions, logs)
        assert len(gaps) == 2

    def test_found_by_name_match(self):
        """Change without ID but matching log name → no gap."""
        sessions = [{
            "summary_id": "82",
            "user": "James",
            "timestamp": "2026-03-21T00:00:00Z",
            "farmos_changes": '[{"type":"activity","details":"Seeding — P2R3.50-62"}]',
        }]
        logs = [{"id": "abc123", "name": "Seeding — P2R3.50-62", "type": "activity"}]

        gaps = detect_logging_gaps(sessions, logs)
        assert len(gaps) == 0
