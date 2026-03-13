"""
Comprehensive tests for the pure functions in helpers.py.

Covers: parse_date, format_planted_label, build_asset_name,
format_plant_asset (name parsing + inventory), build_plant_type_description /
parse_plant_type_metadata roundtrip, format_timestamp, and _build_import_notes
from server.py.
"""

import time
from datetime import datetime, timezone, timedelta

import pytest

from helpers import (
    AEST,
    parse_date,
    format_planted_label,
    build_asset_name,
    format_plant_asset,
    format_timestamp,
    build_plant_type_description,
    parse_plant_type_metadata,
)
from server import _build_import_notes

from tests.conftest import make_plant_asset, make_observation


# ── parse_date ────────────────────────────────────────────────


class TestParseDate:
    def test_iso_date(self):
        """ISO '2025-10-09' produces the correct AEST midnight timestamp."""
        ts = parse_date("2025-10-09")
        dt = datetime.fromtimestamp(ts, tz=AEST)
        assert dt.year == 2025
        assert dt.month == 10
        assert dt.day == 9
        assert dt.hour == 0
        assert dt.minute == 0

    def test_iso_with_utc_z_suffix(self):
        """ISO+time with Z suffix is handled as UTC."""
        ts = parse_date("2026-03-09T03:15:00.000Z")
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        assert dt.year == 2026
        assert dt.month == 3
        assert dt.day == 9
        assert dt.hour == 3
        assert dt.minute == 15

    def test_text_year_month_day(self):
        """Text '2025-MARCH-20 to 24TH' extracts year=2025, month=3, day=20."""
        ts = parse_date("2025-MARCH-20 to 24TH")
        dt = datetime.fromtimestamp(ts, tz=AEST)
        assert dt.year == 2025
        assert dt.month == 3
        assert dt.day == 20

    def test_text_year_month_only(self):
        """Text '2025-MARCH' without day defaults to day=1."""
        ts = parse_date("2025-MARCH")
        dt = datetime.fromtimestamp(ts, tz=AEST)
        assert dt.year == 2025
        assert dt.month == 3
        assert dt.day == 1

    def test_empty_string_returns_approximately_now(self):
        """Empty string returns a timestamp within a few seconds of now."""
        before = int(datetime.now(tz=AEST).timestamp())
        ts = parse_date("")
        after = int(datetime.now(tz=AEST).timestamp())
        assert before <= ts <= after + 1

    def test_none_returns_approximately_now(self):
        """None returns a timestamp within a few seconds of now."""
        before = int(datetime.now(tz=AEST).timestamp())
        ts = parse_date(None)
        after = int(datetime.now(tz=AEST).timestamp())
        assert before <= ts <= after + 1

    def test_garbage_returns_approximately_now(self):
        """Unrecognised garbage falls back to approximately now."""
        before = int(datetime.now(tz=AEST).timestamp())
        ts = parse_date("not-a-date-at-all!!!")
        after = int(datetime.now(tz=AEST).timestamp())
        assert before <= ts <= after + 1


# ── format_planted_label ──────────────────────────────────────


class TestFormatPlantedLabel:
    def test_iso_date(self):
        assert format_planted_label("2025-04-25") == "25 APR 2025"

    def test_text_month_year(self):
        assert format_planted_label("April 2025") == "APR 2025"

    def test_empty_string(self):
        assert format_planted_label("") == "SPRING 2025"

    def test_unrecognised_returned_uppercased(self):
        assert format_planted_label("late winter") == "LATE WINTER"


# ── build_asset_name ──────────────────────────────────────────


class TestBuildAssetName:
    def test_standard_case(self):
        result = build_asset_name("2025-04-25", "Pigeon Pea", "P2R2.0-3")
        assert result == "25 APR 2025 - Pigeon Pea - P2R2.0-3"

    def test_empty_date(self):
        result = build_asset_name("", "Comfrey", "P2R1.3-9")
        assert result == "SPRING 2025 - Comfrey - P2R1.3-9"


# ── format_plant_asset — name parsing ─────────────────────────


class TestFormatPlantAssetNameParsing:
    def test_three_part_simple(self):
        """Standard 3-part name: date - species - section."""
        asset = make_plant_asset(name="25 APR 2025 - Pigeon Pea - P2R2.0-3")
        result = format_plant_asset(asset)
        assert result["species"] == "Pigeon Pea"
        assert result["section"] == "P2R2.0-3"
        assert result["planted_date"] == "25 APR 2025"

    def test_species_with_dash(self):
        """Species containing a dash: 'Basil - Sweet'."""
        asset = make_plant_asset(name="25 APR 2025 - Basil - Sweet - P2R3.14-21")
        result = format_plant_asset(asset)
        assert result["species"] == "Basil - Sweet"
        assert result["section"] == "P2R3.14-21"

    def test_species_with_dash_and_variety(self):
        """Species with dash and variety: 'Basil - Sweet (Classic)'."""
        asset = make_plant_asset(
            name="25 APR 2025 - Basil - Sweet (Classic) - P2R3.14-21"
        )
        result = format_plant_asset(asset)
        assert result["species"] == "Basil - Sweet (Classic)"
        assert result["section"] == "P2R3.14-21"

    def test_two_part_name_no_section(self):
        """2-part name (no section) sets section to empty string."""
        asset = make_plant_asset(name="25 APR 2025 - Pigeon Pea")
        result = format_plant_asset(asset)
        assert result["planted_date"] == "25 APR 2025"
        assert result["species"] == "Pigeon Pea"
        assert result["section"] == ""

    def test_one_part_name(self):
        """1-part name: species is the full name."""
        asset = make_plant_asset(name="Pigeon Pea")
        result = format_plant_asset(asset)
        assert result["species"] == "Pigeon Pea"
        assert result["planted_date"] == ""
        assert result["section"] == ""


class TestFormatPlantAssetInventory:
    def test_inventory_integer(self):
        """Inventory count extracted from measure='count' entry."""
        asset = make_plant_asset(
            name="25 APR 2025 - Pigeon Pea - P2R2.0-3",
            inventory_count=4,
        )
        result = format_plant_asset(asset)
        assert result["inventory_count"] == 4

    def test_inventory_float_truncated(self):
        """Float value '3.0' is truncated to integer 3."""
        asset = make_plant_asset(name="25 APR 2025 - Pigeon Pea - P2R2.0-3")
        # Manually set a float string value
        asset["attributes"]["inventory"] = [
            {"measure": "count", "value": "3.0"}
        ]
        result = format_plant_asset(asset)
        assert result["inventory_count"] == 3

    def test_no_inventory(self):
        """No inventory data means 'inventory_count' key is absent."""
        asset = make_plant_asset(
            name="25 APR 2025 - Pigeon Pea - P2R2.0-3",
            inventory_count=None,
        )
        result = format_plant_asset(asset)
        assert "inventory_count" not in result


# ── build_plant_type_description / parse_plant_type_metadata roundtrip ──


class TestPlantTypeMetadataRoundtrip:
    def test_full_metadata_roundtrip(self):
        """Build a description with all fields, then parse it back."""
        fields = {
            "description": "A fast-growing nitrogen fixer.",
            "botanical_name": "Cajanus cajan",
            "lifecycle_years": "3-5",
            "strata": "high",
            "succession_stage": "pioneer",
            "plant_functions": "nitrogen_fixer,biomass_producer",
            "crop_family": "Fabaceae",
            "lifespan_years": "3-5",
            "source": "FFC",
        }
        desc = build_plant_type_description(fields)
        parsed = parse_plant_type_metadata(desc)

        assert parsed["botanical_name"] == "Cajanus cajan"
        assert parsed["strata"] == "high"
        assert parsed["succession_stage"] == "pioneer"
        assert parsed["crop_family"] == "Fabaceae"
        assert parsed["lifespan_years"] == "3-5"
        assert parsed["lifecycle_years"] == "3-5"
        assert parsed["source"] == "FFC"
        # Functions go through title case then back to underscores
        assert parsed["plant_functions"] == "nitrogen_fixer,biomass_producer"

    def test_functions_with_underscores_roundtrip(self):
        """Functions with underscores survive the title-case round-trip."""
        fields = {
            "plant_functions": "nitrogen_fixer,biomass_producer,edible_fruit",
        }
        desc = build_plant_type_description(fields)
        parsed = parse_plant_type_metadata(desc)
        assert parsed["plant_functions"] == "nitrogen_fixer,biomass_producer,edible_fruit"

    def test_empty_description_returns_empty_dict(self):
        """Empty description string returns empty metadata dict."""
        parsed = parse_plant_type_metadata("")
        assert parsed == {}


# ── _build_import_notes ───────────────────────────────────────


class TestBuildImportNotes:
    def test_full_observation(self):
        """Full observation includes reporter, timestamp, mode, notes, count."""
        obs = make_observation(
            observer="Claire",
            timestamp="2026-03-09T03:15:00.000Z",
            mode="full_inventory",
            plant_notes="Healthy growth",
            previous_count=5,
            new_count=3,
        )
        notes = _build_import_notes(obs)
        assert "Reporter: Claire" in notes
        assert "Submitted: 2026-03-09T03:15" in notes
        assert "Mode: full_inventory" in notes
        assert "Plant notes: Healthy growth" in notes
        assert "Count: 5" in notes and "3" in notes

    def test_condition_alive_skipped(self):
        """Condition 'alive' is not included in notes."""
        obs = make_observation(condition="alive")
        notes = _build_import_notes(obs)
        assert "Condition" not in notes

    def test_extra_parameter_appended(self):
        """Extra string is appended to the notes."""
        obs = make_observation(observer="Claire")
        notes = _build_import_notes(obs, extra="Created new plant asset")
        assert notes.endswith("Created new plant asset")


# ── format_timestamp ──────────────────────────────────────────


class TestFormatTimestamp:
    def test_unix_timestamp(self):
        """Unix timestamp is formatted to AEST date string."""
        # 2025-04-25 00:00:00 AEST
        dt = datetime(2025, 4, 25, 0, 0, tzinfo=AEST)
        ts = int(dt.timestamp())
        result = format_timestamp(ts)
        assert result == "2025-04-25 00:00"

    def test_iso_string(self):
        """ISO string is parsed and formatted to AEST."""
        result = format_timestamp("2026-03-09T03:15:00Z")
        # 03:15 UTC = 13:15 AEST
        assert result == "2026-03-09 13:15"
