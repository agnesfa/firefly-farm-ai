"""ADR 0008 I8 — asset notes sanitiser tests."""

from server import _sanitise_asset_notes


class TestSanitiseAssetNotes:
    def test_empty_input_returns_empty(self):
        assert _sanitise_asset_notes("") == ""
        assert _sanitise_asset_notes(None) == ""

    def test_stable_note_passes_through(self):
        note = "Rootstock: Anna, grafted April 2026"
        assert _sanitise_asset_notes(note) == note

    def test_short_single_line_passes_through(self):
        assert _sanitise_asset_notes("Claire's decision: nitrogen fixers") == \
            "Claire's decision: nitrogen fixers"

    def test_strips_interaction_stamp_line(self):
        notes = "Rootstock: Anna\n[ontology:InteractionStamp] initiator=X | ts=2026"
        assert _sanitise_asset_notes(notes) == "Rootstock: Anna"

    def test_strips_submission_line(self):
        notes = "Rootstock: Anna\nsubmission=abc-123-def"
        assert _sanitise_asset_notes(notes) == "Rootstock: Anna"

    def test_strips_reporter_header(self):
        assert _sanitise_asset_notes("Reporter: Leah") == ""

    def test_strips_metadata_headers_keeps_plant_notes_narrative(self):
        """Reporter/Submitted/Mode/Count are pure metadata (dropped).

        'Plant notes: <narrative>' keeps the narrative (strip prefix only).
        """
        dump = (
            "Reporter: Leah\n"
            "Submitted: 2026-04-14T06:46:00\n"
            "Mode: new_plant\n"
            "Plant notes: two flowers observed\n"
            "Count: 0 -> 1\n"
        )
        assert _sanitise_asset_notes(dump) == "two flowers observed"

    def test_strips_boilerplate_phrase(self):
        notes = "Rootstock: Anna\nNew plant added via field observation"
        assert _sanitise_asset_notes(notes) == "Rootstock: Anna"

    def test_full_leah_dump_reduces_to_narrative_only(self):
        """Full import payload collapses to just the Plant notes narrative."""
        dump = (
            "Reporter: Leah\n"
            "Submitted: 2026-04-14T06:46:00\n"
            "Mode: new_plant\n"
            "Plant notes: Leah transcript 14 Apr 2026.  two flowers observed\n"
            "Count: 0 -> 1\n"
            "New plant added via field observation\n"
            "[ontology:InteractionStamp] initiator=Leah | submission=479332c9"
        )
        assert _sanitise_asset_notes(dump) == (
            "Leah transcript 14 Apr 2026.  two flowers observed"
        )

    def test_plant_notes_prefix_case_insensitive(self):
        assert _sanitise_asset_notes("PLANT NOTES: urgent chop needed") == (
            "urgent chop needed"
        )
        assert _sanitise_asset_notes("plant notes:     spaces before") == (
            "spaces before"
        )

    def test_stamp_only_reduces_to_empty(self):
        assert _sanitise_asset_notes(
            "[ontology:InteractionStamp] initiator=x | submission=abc"
        ) == ""

    def test_preserves_user_narrative_mixed_with_stamp(self):
        notes = "Grafted April 2026, rootstock Anna\n[ontology:InteractionStamp] initiator=X"
        assert _sanitise_asset_notes(notes) == "Grafted April 2026, rootstock Anna"

    def test_case_insensitive_header_matching(self):
        assert _sanitise_asset_notes("REPORTER: Leah") == ""
        assert _sanitise_asset_notes("reporter: Leah") == ""
