"""ADR 0008 I11 — deterministic log-type classifier tests."""

import pytest
from classifier import classify_observation, apply_classifier_to_notes


class TestTypeClassification:
    def test_seeding_verb(self):
        assert classify_observation("Seeded pigeon pea in row 3")["type"] == "seeding"
        assert classify_observation("Sowed tomato seeds")["type"] == "seeding"

    def test_transplanting_verb(self):
        assert classify_observation("Transplanted 5 papayas")["type"] == "transplanting"
        assert classify_observation("Planted new citrus in P2R3")["type"] == "transplanting"
        assert classify_observation("Moved the basil from nursery")["type"] == "transplanting"

    def test_harvest_verb(self):
        assert classify_observation("Harvested 3kg of mangoes")["type"] == "harvest"
        assert classify_observation("Picked the ripe tomatoes")["type"] == "harvest"

    def test_activity_verb(self):
        assert classify_observation("Chopped and dropped pigeon pea")["type"] == "activity"
        assert classify_observation("Cut back the banana leaves")["type"] == "activity"
        assert classify_observation("Mulched the bed heavily")["type"] == "activity"

    def test_observation_default(self):
        # Past-tense narrative of observed state with no action verb
        r = classify_observation("Two flowers observed; plant looks healthy")
        assert r["type"] == "observation"

    def test_precedence_seeding_over_transplanting(self):
        # "seeded and planted" — seeding wins (first rule)
        r = classify_observation("Seeded and planted more rows")
        assert r["type"] == "seeding"


class TestStatusClassification:
    def test_pending_marker(self):
        assert classify_observation("Needs watering soon")["status"] == "pending"
        assert classify_observation("Should prune next week")["status"] == "pending"
        assert classify_observation("To do: transplant Okra")["status"] == "pending"
        assert classify_observation("Urgent: pest attack on basil")["status"] == "pending"

    def test_done_default(self):
        assert classify_observation("Harvested 5kg")["status"] == "done"
        assert classify_observation("Pruned pigeon pea")["status"] == "done"

    def test_pending_compounds_with_type(self):
        r = classify_observation("Needs pruning of pigeon pea branches")
        assert r["type"] == "activity"
        assert r["status"] == "pending"

    def test_pending_with_transplanting(self):
        r = classify_observation("Should transplant tomorrow")
        assert r["type"] == "transplanting"
        assert r["status"] == "pending"


class TestAmbiguityHandling:
    def test_empty_notes_is_ambiguous(self):
        r = classify_observation("")
        assert r["ambiguous"] is True
        assert r["type"] == "observation"
        assert r["status"] == "pending"
        assert r["confidence"] == 0.0

    def test_no_signal_is_ambiguous(self):
        r = classify_observation("hello world xyzzy")
        assert r["ambiguous"] is True
        assert r["confidence"] <= 0.4

    def test_multi_verb_match_is_ambiguous(self):
        # "harvested" + "planted" — two competing verbs
        r = classify_observation("Harvested mangoes and planted new citrus")
        assert r["ambiguous"] is True
        assert "multi_verb_match" in r["reason"]

    def test_pending_only_is_not_ambiguous(self):
        # "needs attention" → observation + pending is a clear signal
        r = classify_observation("Plant needs attention")
        # 'plant' matches TRANSPLANTING verb, so it's actually not ambiguous
        assert r["status"] == "pending"

    def test_clear_activity_is_not_ambiguous(self):
        r = classify_observation("Pruned the pigeon pea heavily")
        assert r["ambiguous"] is False
        assert r["confidence"] >= 0.5


class TestApplyClassifierToNotes:
    def test_flags_ambiguous_notes(self):
        notes, result = apply_classifier_to_notes("xyzzy hello")
        assert result["ambiguous"] is True
        assert "[FLAG classifier-ambiguous:" in notes

    def test_passes_clear_notes_unchanged(self):
        notes, result = apply_classifier_to_notes("Pruned the pigeon pea")
        assert result["ambiguous"] is False
        assert "[FLAG" not in notes
        assert notes == "Pruned the pigeon pea"

    def test_handles_none_input(self):
        notes, result = apply_classifier_to_notes(None)
        assert result["type"] == "observation"
        assert result["status"] == "pending"
