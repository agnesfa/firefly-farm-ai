"""ADR 0008 I8 — asset notes hygiene utilities (standalone, no fastmcp dep).

This module intentionally has NO external deps so it can be imported
from the main repo venv (pydantic v1) and from scripts/cleanup/*.py.
`server.py` re-exports the function at its original name.

Design (clarified 2026-04-20 after Agnes's review):

  * `[ontology:InteractionStamp]` lines  → dropped (belong on the log)
  * `submission=<uuid>` lines            → dropped
  * Pure-metadata headers (`Reporter:/Submitted:/Mode:/Count:`)
                                           → dropped (timestamps + mode,
                                             no narrative)
  * `Plant notes: <narrative>`           → `Plant notes:` PREFIX stripped;
                                           narrative after it is KEPT
  * Boilerplate ("New plant added via field observation") → dropped
  * Anything else                        → kept (stable planting context)

The result: asset notes retain a short human-readable one-liner from the
original submission (useful context on the QR card) while all metadata
stays on the observation log where it belongs.
"""
from __future__ import annotations

import re

_STAMP_MARKER = "[ontology:InteractionStamp]"

# Pure-metadata headers: line starting with these has no narrative
# content and is dropped entirely.
_METADATA_PREFIXES = (
    "reporter:",
    "submitted:",
    "mode:",
    "count:",
)

# Narrative-carrying prefix: strip just the prefix, keep the rest of
# the line.
_NARRATIVE_PREFIX_RE = re.compile(r"^plant notes:\s*", re.IGNORECASE)

_BOILERPLATE_PHRASES = (
    "New plant added via field observation",
)


def sanitise_asset_notes(notes: str) -> str:
    """Return text safe for a plant asset's `notes` field per ADR 0008 I8.

    Drops the InteractionStamp, submission= fragment, and import-payload
    metadata headers. Keeps the submitter's narrative (the text after
    `Plant notes:`) as stable planting context.
    """
    if not notes:
        return ""
    kept: list = []
    for ln in str(notes).splitlines():
        if _STAMP_MARKER in ln:
            continue
        low = ln.strip().lower()
        if low.startswith("submission="):
            continue
        if any(low.startswith(p) for p in _METADATA_PREFIXES):
            continue
        # "Plant notes: <narrative>" — strip only the prefix, keep text.
        ln_stripped = _NARRATIVE_PREFIX_RE.sub("", ln, count=1)
        kept.append(ln_stripped.rstrip())
    out = "\n".join(kept).strip()
    for phrase in _BOILERPLATE_PHRASES:
        out = out.replace(phrase, "").strip()
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out
