"""
InteractionStamp — ontology-linked provenance metadata.

Every MCP write tool must produce a stamp. Without a stamp, a change
is untraceable and untrusted. The stamp feeds system_health metrics:
  - provenance_coverage: count(logs with stamp) / count(all recent logs)
  - source_conflict_count: count(stamps with outcome=conflict)
  - entity_touch_rate: avg(related_entities.length) per stamp
  - mcp_reliability: success / total attempts

Dual-actor design: most interactions have a human initiator (who has
intent and trust) and a system executor (which has a channel chain
and an outcome). Both are captured.

See: knowledge/farm_ontology.yaml — InteractionStamp entity
"""

from datetime import datetime, timezone
from typing import Optional

# ── Stamp prefix — links to ontology definition ──────────────

STAMP_PREFIX = "[ontology:InteractionStamp]"

# ── Valid values (linked to ontology) ─────────────────────────

CHANNELS = {"claude_code", "claude_desktop", "claude_session", "qr_page", "farmos_ui", "automated"}
EXECUTORS = {"farmos_api", "apps_script", "mcp_tool", "plantnet_api", "wikimedia_api"}
ACTIONS = {"created", "updated", "archived", "verified", "rejected", "attempted"}
TARGETS = {"plant", "observation", "activity", "knowledge", "seed", "plant_type", "session_summary"}
OUTCOMES = {"success", "failed", "partial", "timeout", "conflict"}
ROLES = {"manager", "farmhand", "visitor", "system"}


def build_stamp(
    initiator: str,
    role: str,
    channel: str,
    executor: str,
    action: str,
    target: str,
    outcome: str = "success",
    error_detail: Optional[str] = None,
    related_entities: Optional[list[str]] = None,
    session_id: Optional[str] = None,
    source_submission: Optional[str] = None,
    confidence: Optional[float] = None,
) -> str:
    """Build a stamp string from structured fields.

    Format: [ontology:InteractionStamp] key=value | key=value | ...
    """
    parts = [
        f"initiator={initiator}",
        f"role={role}",
        f"channel={channel}",
        f"executor={executor}",
        f"action={action}",
        f"target={target}",
        f"outcome={outcome}",
        f"ts={datetime.now(timezone.utc).isoformat()}",
    ]

    if error_detail:
        parts.append(f"error={error_detail}")
    if related_entities:
        parts.append(f"related={','.join(related_entities)}")
    if session_id:
        parts.append(f"session={session_id}")
    if source_submission:
        parts.append(f"submission={source_submission}")
    if confidence is not None:
        parts.append(f"confidence={confidence:.2f}")

    return f"{STAMP_PREFIX} {' | '.join(parts)}"


def append_stamp(notes: Optional[str], stamp: str) -> str:
    """Append a stamp to existing notes."""
    existing = (notes or "").strip()
    if not existing:
        return stamp
    return f"{existing}\n{stamp}"


def has_stamp(notes: Optional[str]) -> bool:
    """Check whether notes contain a valid InteractionStamp."""
    return STAMP_PREFIX in (notes or "")


def parse_stamp(notes: Optional[str]) -> Optional[dict]:
    """Parse a stamp from notes. Returns the first stamp found, or None."""
    text = notes or ""
    idx = text.find(STAMP_PREFIX)
    if idx == -1:
        return None

    line_start = idx + len(STAMP_PREFIX)
    line_end = text.find("\n", line_start)
    line = (text[line_start:line_end] if line_end != -1 else text[line_start:]).strip()

    pairs = [s.strip() for s in line.split("|")]
    kv = {}
    for pair in pairs:
        eq = pair.find("=")
        if eq > 0:
            kv[pair[:eq].strip()] = pair[eq + 1:].strip()

    initiator = kv.get("initiator")
    action = kv.get("action")
    target = kv.get("target")
    if not initiator or not action or not target:
        return None

    result = {
        "initiator": initiator,
        "role": kv.get("role", "system"),
        "channel": kv.get("channel", "automated"),
        "executor": kv.get("executor", "mcp_tool"),
        "action": action,
        "target": target,
    }

    if "outcome" in kv:
        result["outcome"] = kv["outcome"]
    if "error" in kv:
        result["error_detail"] = kv["error"]
    if "related" in kv:
        result["related_entities"] = kv["related"].split(",")
    if "session" in kv:
        result["session_id"] = kv["session"]
    if "submission" in kv:
        result["source_submission"] = kv["submission"]
    if "confidence" in kv:
        result["confidence"] = float(kv["confidence"])

    return result


def count_stamps_in_logs(logs: list) -> dict:
    """Count stamps in a list of logs (for provenance_coverage metric).

    Each log should have a 'notes' field (string or dict with 'value').
    """
    stamped = 0
    total = len(logs)
    for log in logs:
        notes = log.get("notes", "")
        if isinstance(notes, dict):
            notes = notes.get("value", "")
        if has_stamp(str(notes)):
            stamped += 1
    coverage = stamped / total if total > 0 else 0
    return {"stamped": stamped, "total": total, "coverage": coverage}


def build_mcp_stamp(
    action: str,
    target: str,
    initiator: Optional[str] = None,
    role: str = "manager",
    executor: str = "farmos_api",
    related_entities: Optional[list[str]] = None,
    source_submission: Optional[str] = None,
    confidence: Optional[float] = None,
) -> str:
    """Build a default stamp for an MCP tool invocation.

    Uses 'Claude_user' as initiator when the human identity is unknown.
    """
    return build_stamp(
        initiator=initiator or "Claude_user",
        role=role,
        channel="claude_session",
        executor=executor,
        action=action,
        target=target,
        related_entities=related_entities,
        source_submission=source_submission,
        confidence=confidence,
    )
