"""Tests for plantnet_verify module."""

import pytest
from unittest.mock import patch, MagicMock
from plantnet_verify import (
    build_botanical_lookup,
    _botanical_match,
    _get_expected_botanical,
    verify_species_photo,
    get_call_count,
)


# ── Botanical lookup ──────────────────────────────────────────


class TestBotanicalLookup:
    def test_loads_csv(self):
        lookup = build_botanical_lookup()
        # Should have many species
        reverse = lookup.get("__reverse__", {})
        assert len(reverse) > 50
        # Known species
        assert reverse["Pigeon Pea"] == "cajanus cajan"
        assert reverse["Comfrey"] == "symphytum officinale"

    def test_reverse_lookup(self):
        lookup = build_botanical_lookup()
        assert _get_expected_botanical("Pigeon Pea", lookup) == "cajanus cajan"
        assert _get_expected_botanical("NonexistentPlant", lookup) is None


# ── Botanical matching ────────────────────────────────────────


class TestBotanicalMatch:
    def test_exact_match(self):
        assert _botanical_match("Cajanus cajan", "cajanus cajan")

    def test_prefix_plantnet_longer(self):
        assert _botanical_match("Cajanus cajan", "cajanus")

    def test_prefix_expected_longer(self):
        assert _botanical_match("Cajanus", "cajanus cajan")

    def test_no_match(self):
        assert not _botanical_match("Solanum lycopersicum", "cajanus cajan")

    def test_case_insensitive(self):
        assert _botanical_match("CAJANUS CAJAN", "cajanus cajan")


# ── Verify species photo ─────────────────────────────────────


class TestVerifySpeciesPhoto:
    @pytest.fixture
    def lookup(self):
        return build_botanical_lookup()

    def test_no_api_key(self, lookup):
        result = verify_species_photo(b"\xff\xd8\xff", "Pigeon Pea", lookup, api_key="")
        assert result["verified"] is False
        assert result["reason"] == "no_api_key"

    def test_no_species_claim(self, lookup):
        result = verify_species_photo(b"\xff\xd8\xff", "", lookup, api_key="test-key")
        assert result["verified"] is True
        assert result["reason"] == "no_species_claim"

    def test_no_botanical_name(self, lookup):
        """Species without a botanical name in CSV → allow through."""
        result = verify_species_photo(b"\xff\xd8\xff", "UnknownPlantXYZ", lookup, api_key="test-key")
        assert result["verified"] is True
        assert result["reason"] == "no_botanical_name"

    @patch("plantnet_verify.requests.post")
    def test_match_found(self, mock_post, lookup):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "results": [
                {"species": {"scientificNameWithoutAuthor": "Cajanus cajan"}, "score": 0.72},
                {"species": {"scientificNameWithoutAuthor": "Vigna unguiculata"}, "score": 0.15},
            ]
        }
        mock_post.return_value = mock_resp

        result = verify_species_photo(b"\xff\xd8\xff", "Pigeon Pea", lookup, api_key="test-key")
        assert result["verified"] is True
        assert result["confidence"] == 0.72

    @patch("plantnet_verify.requests.post")
    def test_mismatch(self, mock_post, lookup):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "results": [
                {"species": {"scientificNameWithoutAuthor": "Solanum lycopersicum"}, "score": 0.85},
            ]
        }
        mock_post.return_value = mock_resp

        result = verify_species_photo(b"\xff\xd8\xff", "Pigeon Pea", lookup, api_key="test-key")
        assert result["verified"] is False
        assert "mismatch" in result["reason"]
        assert "Solanum lycopersicum" in result["plantnet_top"]

    @patch("plantnet_verify.requests.post")
    def test_low_confidence_rejected(self, mock_post, lookup):
        """Match found but below 30% threshold → rejected."""
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "results": [
                {"species": {"scientificNameWithoutAuthor": "Cajanus cajan"}, "score": 0.15},
            ]
        }
        mock_post.return_value = mock_resp

        result = verify_species_photo(b"\xff\xd8\xff", "Pigeon Pea", lookup, api_key="test-key")
        assert result["verified"] is False

    @patch("plantnet_verify.requests.post")
    def test_api_error_rejects(self, mock_post, lookup):
        """API failure → reject photo (safe default)."""
        mock_post.side_effect = ConnectionError("network down")

        result = verify_species_photo(b"\xff\xd8\xff", "Pigeon Pea", lookup, api_key="test-key")
        assert result["verified"] is False
        assert "api_error" in result["reason"]

    @patch("plantnet_verify.requests.post")
    def test_http_error_rejects(self, mock_post, lookup):
        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 429
        mock_resp.text = "rate limited"
        mock_post.return_value = mock_resp

        result = verify_species_photo(b"\xff\xd8\xff", "Pigeon Pea", lookup, api_key="test-key")
        assert result["verified"] is False
        assert "429" in result["reason"]

    @patch("plantnet_verify.requests.post")
    def test_no_results_rejects(self, mock_post, lookup):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"results": []}
        mock_post.return_value = mock_resp

        result = verify_species_photo(b"\xff\xd8\xff", "Pigeon Pea", lookup, api_key="test-key")
        assert result["verified"] is False
        assert result["reason"] == "no_plantnet_results"

    @patch("plantnet_verify.requests.post")
    def test_match_in_second_result(self, mock_post, lookup):
        """Species matches in result #2 (not top) → still verified."""
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "results": [
                {"species": {"scientificNameWithoutAuthor": "Vigna unguiculata"}, "score": 0.50},
                {"species": {"scientificNameWithoutAuthor": "Cajanus cajan"}, "score": 0.35},
            ]
        }
        mock_post.return_value = mock_resp

        result = verify_species_photo(b"\xff\xd8\xff", "Pigeon Pea", lookup, api_key="test-key")
        assert result["verified"] is True
        assert result["confidence"] == 0.35
