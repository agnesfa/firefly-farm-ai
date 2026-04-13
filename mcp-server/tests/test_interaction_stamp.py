"""Tests for InteractionStamp — ontology-linked provenance metadata.

Pure function tests — no I/O, no mocking needed.
"""

import unittest
from interaction_stamp import (
    build_stamp,
    append_stamp,
    has_stamp,
    parse_stamp,
    count_stamps_in_logs,
    build_mcp_stamp,
    STAMP_PREFIX,
)


class TestBuildStamp(unittest.TestCase):
    def _base(self, **overrides):
        defaults = {
            "initiator": "Agnes",
            "role": "manager",
            "channel": "claude_code",
            "executor": "farmos_api",
            "action": "created",
            "target": "plant",
        }
        defaults.update(overrides)
        return build_stamp(**defaults)

    def test_prefix(self):
        stamp = self._base()
        self.assertIn("[ontology:InteractionStamp]", stamp)

    def test_required_fields(self):
        stamp = self._base()
        self.assertIn("initiator=Agnes", stamp)
        self.assertIn("role=manager", stamp)
        self.assertIn("channel=claude_code", stamp)
        self.assertIn("executor=farmos_api", stamp)
        self.assertIn("action=created", stamp)
        self.assertIn("target=plant", stamp)
        self.assertIn("outcome=success", stamp)
        self.assertRegex(stamp, r"ts=\d{4}-\d{2}-\d{2}T")

    def test_default_outcome_success(self):
        stamp = self._base()
        self.assertIn("outcome=success", stamp)

    def test_optional_fields(self):
        stamp = self._base(
            outcome="timeout",
            error_detail="MCP server timeout after 30s",
            related_entities=["Pigeon Pea", "P2R5.29-38"],
            session_id="sess-123",
            source_submission="sub-456",
            confidence=0.85,
        )
        self.assertIn("outcome=timeout", stamp)
        self.assertIn("error=MCP server timeout after 30s", stamp)
        self.assertIn("related=Pigeon Pea,P2R5.29-38", stamp)
        self.assertIn("session=sess-123", stamp)
        self.assertIn("submission=sub-456", stamp)
        self.assertIn("confidence=0.85", stamp)

    def test_omits_optional_when_not_provided(self):
        stamp = self._base()
        self.assertNotIn("error=", stamp)
        self.assertNotIn("related=", stamp)
        self.assertNotIn("session=", stamp)
        self.assertNotIn("submission=", stamp)
        self.assertNotIn("confidence=", stamp)


class TestAppendStamp(unittest.TestCase):
    def test_empty_notes(self):
        stamp = build_stamp("Agnes", "manager", "claude_code", "farmos_api", "created", "plant")
        self.assertEqual(append_stamp("", stamp), stamp)
        self.assertEqual(append_stamp(None, stamp), stamp)

    def test_appends_with_newline(self):
        stamp = build_stamp("Agnes", "manager", "claude_code", "farmos_api", "created", "plant")
        result = append_stamp("Existing notes", stamp)
        self.assertIn("Existing notes\n", result)
        self.assertIn(STAMP_PREFIX, result)


class TestHasStamp(unittest.TestCase):
    def test_detects_stamp(self):
        stamp = build_stamp("Agnes", "manager", "claude_code", "farmos_api", "created", "plant")
        self.assertTrue(has_stamp(stamp))
        self.assertTrue(has_stamp(f"Notes\n{stamp}"))

    def test_false_without_stamp(self):
        self.assertFalse(has_stamp("Regular notes"))
        self.assertFalse(has_stamp(""))
        self.assertFalse(has_stamp(None))

    def test_no_false_positive(self):
        self.assertFalse(has_stamp("[ontology:Interaction] something"))


class TestParseStamp(unittest.TestCase):
    def _stamp(self, **kw):
        defaults = {
            "initiator": "Agnes", "role": "manager", "channel": "claude_code",
            "executor": "farmos_api", "action": "created", "target": "plant",
        }
        defaults.update(kw)
        return build_stamp(**defaults)

    def test_parses_required_fields(self):
        parsed = parse_stamp(self._stamp())
        self.assertEqual(parsed["initiator"], "Agnes")
        self.assertEqual(parsed["role"], "manager")
        self.assertEqual(parsed["channel"], "claude_code")
        self.assertEqual(parsed["executor"], "farmos_api")
        self.assertEqual(parsed["action"], "created")
        self.assertEqual(parsed["target"], "plant")

    def test_parses_optional_fields(self):
        stamp = self._stamp(
            outcome="failed",
            error_detail="timeout",
            related_entities=["Okra", "P2R5.22-29"],
            confidence=0.42,
        )
        parsed = parse_stamp(stamp)
        self.assertEqual(parsed["outcome"], "failed")
        self.assertEqual(parsed["error_detail"], "timeout")
        self.assertEqual(parsed["related_entities"], ["Okra", "P2R5.22-29"])
        self.assertAlmostEqual(parsed["confidence"], 0.42, places=2)

    def test_returns_none_without_stamp(self):
        self.assertIsNone(parse_stamp("Just notes"))
        self.assertIsNone(parse_stamp(None))

    def test_parses_embedded_stamp(self):
        stamp = self._stamp()
        notes = f"Created plant.\n{stamp}\nMore notes."
        parsed = parse_stamp(notes)
        self.assertEqual(parsed["initiator"], "Agnes")
        self.assertEqual(parsed["target"], "plant")


class TestCountStampsInLogs(unittest.TestCase):
    def _stamp(self):
        return build_stamp("Agnes", "manager", "claude_code", "farmos_api", "created", "plant")

    def test_counts(self):
        stamp = self._stamp()
        logs = [
            {"notes": stamp},
            {"notes": "no stamp"},
            {"notes": f"notes\n{stamp}"},
        ]
        result = count_stamps_in_logs(logs)
        self.assertEqual(result["stamped"], 2)
        self.assertEqual(result["total"], 3)
        self.assertAlmostEqual(result["coverage"], 0.667, places=2)

    def test_dict_notes(self):
        stamp = self._stamp()
        logs = [{"notes": {"value": stamp}}]
        result = count_stamps_in_logs(logs)
        self.assertEqual(result["stamped"], 1)

    def test_empty_list(self):
        result = count_stamps_in_logs([])
        self.assertEqual(result["coverage"], 0)


class TestBuildMcpStamp(unittest.TestCase):
    def test_defaults(self):
        stamp = build_mcp_stamp("created", "observation")
        self.assertIn("initiator=Claude_user", stamp)
        self.assertIn("role=manager", stamp)
        self.assertIn("channel=claude_session", stamp)
        self.assertIn("executor=farmos_api", stamp)

    def test_custom_initiator(self):
        stamp = build_mcp_stamp("created", "knowledge", initiator="Claire", executor="apps_script")
        self.assertIn("initiator=Claire", stamp)
        self.assertIn("executor=apps_script", stamp)

    def test_related_entities(self):
        stamp = build_mcp_stamp("created", "plant", related_entities=["Pigeon Pea", "P2R3.15-21"])
        self.assertIn("related=Pigeon Pea,P2R3.15-21", stamp)


if __name__ == "__main__":
    unittest.main()
