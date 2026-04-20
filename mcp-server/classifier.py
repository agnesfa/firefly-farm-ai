"""ADR 0008 I11 — deterministic log-type classifier.

Given a notes text, classify:
  - log type: observation / activity / transplanting / seeding / harvest
  - status:   done / pending (pending == TODO)

Rules are matched against the lowercased notes in precedence order.
Ambiguity (no rule hit, or competing signals) returns type=observation,
status=pending with a reason string so the importer can flag the log
for human review.

Upgrade path (Step 9, post-FASF ADR 0006): swap this deterministic
function for an agent-skill implementation with confidence scoring and
few-shot learning from correction records. The I11 contract is stable
across both implementations.
"""
from __future__ import annotations

import re
from typing import Optional


# ── Verb lists per I11 §Classification rules ──────────────────

_SEEDING = r"\b(seeded|sowed|sowing|germinated|seeding)\b"
# Note: bare "plant" is deliberately excluded because it's a noun in most
# field contexts ("plant looks healthy"). "Planting/planted/replanted/
# transplant/transplanted" are unambiguous action forms.
_TRANSPLANTING = (
    r"\b(transplanted|transplants|transplanting|transplant|"
    r"planted|planting|replanted|replanting|relocated|relocating|"
    r"moved(?!\s+in))\b"
)
_HARVEST = (
    r"\b(harvested|harvesting|harvest|picked|picking|collected|"
    r"collecting|yielded|yielding|gathered|gathering)\b"
)
_ACTIVITY = (
    r"\b(chopped|chopping|chop|dropped|dropping|"
    r"pruned|pruning|prune|"
    r"mulched|mulching|mulch|"
    r"weeded|weeding|weed|"
    r"watered|watering|"
    r"sprayed|spraying|applied|applying|"
    r"inoculated|inoculating|"
    r"fertilised|fertilising|fertilized|fertilizing|"
    r"composted|composting|dug|digging|tilled|tilling)\b|cut back|chop and drop"
)
_PENDING = (
    r"\b(needs|need|should|to do|todo|urgent|action required|action needed|"
    r"please|must|tbd|pending)\b"
)


def classify_observation(notes: str) -> dict:
    """Classify a log's type and status from its notes text.

    Returns:
        {
            "type": "observation" | "activity" | "transplanting" | "seeding" | "harvest",
            "status": "done" | "pending",
            "confidence": float in [0.0, 1.0],
            "reason": str,
            "ambiguous": bool,
        }
    """
    if not notes:
        return {
            "type": "observation",
            "status": "pending",
            "confidence": 0.0,
            "reason": "empty_notes",
            "ambiguous": True,
        }

    text = str(notes).lower()

    # First handle type (precedence order matters):
    # seeding > transplanting > harvest > activity > observation
    type_match: Optional[str] = None
    type_reason = ""
    confidence = 0.5

    if re.search(_SEEDING, text):
        type_match = "seeding"
        type_reason = "verb_seeding"
        confidence = 0.85
    elif re.search(_TRANSPLANTING, text):
        type_match = "transplanting"
        type_reason = "verb_transplanting"
        confidence = 0.85
    elif re.search(_HARVEST, text):
        type_match = "harvest"
        type_reason = "verb_harvest"
        confidence = 0.85
    elif re.search(_ACTIVITY, text):
        type_match = "activity"
        type_reason = "verb_activity"
        confidence = 0.85
    else:
        # No action verb — fall back to observation
        type_match = "observation"
        type_reason = "no_action_verb"
        confidence = 0.6

    # Status: pending signal overrides done. Pending can apply to any
    # type ("needs pruning" → activity+pending; "plant tomorrow" →
    # transplanting+pending).
    status: str = "done"
    status_reason = ""
    if re.search(_PENDING, text):
        status = "pending"
        status_reason = "verb_pending"

    # Low-confidence classification: notes with no signal at all OR
    # text that matches multiple competing type verbs. Flag ambiguous.
    type_matches = sum(1 for pat in (_SEEDING, _TRANSPLANTING, _HARVEST, _ACTIVITY)
                       if re.search(pat, text))
    ambiguous = type_matches >= 2 or (type_matches == 0 and not re.search(_PENDING, text))
    if ambiguous:
        confidence = min(confidence, 0.4)

    reason_parts = [type_reason]
    if status_reason:
        reason_parts.append(status_reason)
    if type_matches >= 2:
        reason_parts.append("multi_verb_match")

    return {
        "type": type_match,
        "status": status,
        "confidence": confidence,
        "reason": ",".join(reason_parts),
        "ambiguous": ambiguous,
    }


def apply_classifier_to_notes(notes: str) -> tuple[str, dict]:
    """Run the classifier and return (possibly-flagged notes, classification).

    If the classification is ambiguous, prepends a
    `[FLAG classifier-ambiguous: <reason>]` marker to the notes so the
    log surfaces for human review per I11 §Ambiguity handling.
    """
    result = classify_observation(notes or "")
    if result["ambiguous"]:
        flag = f"[FLAG classifier-ambiguous: {result['reason']}]"
        marked_notes = f"{flag}\n{notes or ''}".strip()
        return marked_notes, result
    return (notes or ""), result
