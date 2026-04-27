"""Tests for farmOS v3↔v4 compatibility helpers (mirrors TS api-version.test.ts)."""

import pytest

from api_version import (
    ACTIVE,
    ARCHIVED,
    asset_archive_payload,
    asset_status_filter,
    asset_status_filter_param,
    parse_api_version,
    read_asset_status,
)


class TestParseApiVersion:
    def test_defaults_to_3_when_env_is_none(self):
        assert parse_api_version(None) == "3"

    def test_accepts_3_and_4(self):
        assert parse_api_version("3") == "3"
        assert parse_api_version("4") == "4"

    def test_throws_on_unknown_value(self):
        with pytest.raises(ValueError, match="must be one of 3/4"):
            parse_api_version("5")

    def test_throws_on_v_prefix(self):
        with pytest.raises(ValueError):
            parse_api_version("v3")

    def test_throws_on_empty_string(self):
        with pytest.raises(ValueError):
            parse_api_version("")


class TestAssetStatusFilter:
    def test_v3_active(self):
        assert asset_status_filter("3", ACTIVE) == {"status": "active"}

    def test_v3_archived(self):
        assert asset_status_filter("3", ARCHIVED) == {"status": "archived"}

    def test_v4_active(self):
        assert asset_status_filter("4", ACTIVE) == {"archived": "0"}

    def test_v4_archived(self):
        assert asset_status_filter("4", ARCHIVED) == {"archived": "1"}


class TestAssetStatusFilterParam:
    def test_v3(self):
        assert asset_status_filter_param("3", ACTIVE) == "filter[status]=active"
        assert asset_status_filter_param("3", ARCHIVED) == "filter[status]=archived"

    def test_v4(self):
        assert asset_status_filter_param("4", ACTIVE) == "filter[archived]=0"
        assert asset_status_filter_param("4", ARCHIVED) == "filter[archived]=1"


class TestAssetArchivePayload:
    def test_v3(self):
        assert asset_archive_payload("3") == {"status": "archived"}

    def test_v4(self):
        assert asset_archive_payload("4") == {"archived": True}


class TestReadAssetStatus:
    def test_v4_archived_false_is_active(self):
        assert read_asset_status({"attributes": {"archived": False, "name": "X"}}) == "active"

    def test_v4_archived_true_is_archived(self):
        assert read_asset_status({"attributes": {"archived": True, "name": "X"}}) == "archived"

    def test_v3_status_active(self):
        assert read_asset_status({"attributes": {"status": "active", "name": "X"}}) == "active"

    def test_v3_status_archived(self):
        assert read_asset_status({"attributes": {"status": "archived", "name": "X"}}) == "archived"

    def test_v4_field_wins_when_both_present(self):
        # Defensive: archived field takes precedence (v4 shape).
        assert read_asset_status({"attributes": {"archived": True, "status": "active"}}) == "archived"
        assert read_asset_status({"attributes": {"archived": False, "status": "archived"}}) == "active"

    def test_defaults_to_active_on_missing_data(self):
        assert read_asset_status({}) == "active"
        assert read_asset_status({"attributes": {}}) == "active"
        assert read_asset_status(None) == "active"


class TestRoundTrip:
    """Sanity: emit a filter, simulate response in matching version's shape,
    round-trip it through read_asset_status. Both versions yield same label."""

    @pytest.mark.parametrize(
        "version,status",
        [
            ("3", ACTIVE), ("3", ARCHIVED),
            ("4", ACTIVE), ("4", ARCHIVED),
        ],
    )
    def test_filter_then_read_roundtrips(self, version, status):
        f = asset_status_filter(version, status)
        if version == "4":
            asset = {"attributes": {"archived": status == ARCHIVED, "name": "X"}}
        else:
            asset = {"attributes": {"status": status, "name": "X"}}
        assert read_asset_status(asset) == status
        assert len(f) == 1
