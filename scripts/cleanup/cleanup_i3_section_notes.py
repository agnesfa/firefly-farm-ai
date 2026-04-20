#!/usr/bin/env python3
"""I3 cleanup — section-notes fan-out pollution (ADR 0008).

For every plant-attached observation log that carries a "Section notes: …"
line in its notes field (a violation of I3 — notes hygiene), this script:

  1. Parses the leaked "Section notes:" text.
  2. Strips that line from the plant-log's notes.
  3. Groups violations by (section, submission_id, text) so that for each
     unique (section, date, submission) tuple, we create ONE section-level
     log carrying just the section_notes content, attached to the section
     asset (location_ids only, no asset_ids).

Net effect: plant logs carry only per-plant content; section-scoped
commentary lives on a single section log. Matches the ADR 0008 I2/I3
invariants.

Usage
-----
    python scripts/cleanup/cleanup_i3_section_notes.py --dry-run
    python scripts/cleanup/cleanup_i3_section_notes.py
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "mcp-server"))
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from dotenv import load_dotenv
from farmos_client import FarmOSClient
from _paginate import paginate_all

load_dotenv(str(_REPO_ROOT / ".env"))


SECTION_NOTE_RE = re.compile(r"^Section notes?:\s*(.+?)\s*$", re.M | re.I)
SUBMISSION_RE = re.compile(r"submission=([0-9a-f-]{36})")
REPORTER_RE = re.compile(r"Reporter:\s*(\S+)")
SUBMITTED_RE = re.compile(r"Submitted:\s*([\dT:\-]+)")


@dataclass
class Violation:
    log_id: str
    log_type: str  # always "observation" in our current data
    log_name: str
    section: str
    section_note_text: str
    submission_id: str    # may be "" if not found
    reporter: str         # "" if not found
    submitted: str        # "" if not found
    timestamp: str        # ISO date
    original_notes: str


def fetch_land_assets(fc, scope: str) -> list[dict]:
    """Offset-based pagination — see scripts/_paginate.py docstring."""
    all_assets = paginate_all(
        fc.session, fc.hostname, "asset/land",
        sort="name",
    )
    return [
        a for a in all_assets
        if a.get("attributes", {}).get("name", "").startswith(scope)
    ]


def section_uuid_lookup(section_assets: list[dict]) -> dict[str, str]:
    return {
        a.get("attributes", {}).get("name", ""): a["id"]
        for a in section_assets
    }


def scan_section_for_violations(fc, section_name: str, section_uuid: str) -> list[Violation]:
    violations = []
    # Use get_logs which paginates
    logs = fc.get_logs(section_id=section_name) or []
    for log_short in logs:
        log_id = log_short["id"]
        log_type = log_short.get("type", "").replace("log--", "")
        # Fetch full record for notes
        resp = fc.session.get(
            f"{fc.hostname}/api/log/{log_type}/{log_id}", timeout=15,
        )
        if not resp.ok:
            continue
        data = resp.json().get("data", {})
        attrs = data.get("attributes", {})
        notes_obj = attrs.get("notes", {}) or {}
        notes_text = notes_obj.get("value", "") if isinstance(notes_obj, dict) else ""
        if not notes_text:
            continue
        m = SECTION_NOTE_RE.search(notes_text)
        if not m:
            continue
        sn_text = m.group(1).strip()
        # Only flag plant-attached logs (those that shouldn't carry section-level text)
        asset_refs = (data.get("relationships", {}).get("asset", {}) or {}).get("data") or []
        if not asset_refs:
            # No plant attachment — already section-level, ignore
            continue
        sub_m = SUBMISSION_RE.search(notes_text)
        rep_m = REPORTER_RE.search(notes_text)
        sub2_m = SUBMITTED_RE.search(notes_text)
        violations.append(Violation(
            log_id=log_id,
            log_type=log_type,
            log_name=attrs.get("name", "?"),
            section=section_name,
            section_note_text=sn_text,
            submission_id=sub_m.group(1) if sub_m else "",
            reporter=rep_m.group(1) if rep_m else "",
            submitted=sub2_m.group(1) if sub2_m else "",
            timestamp=attrs.get("timestamp", "")[:10],
            original_notes=notes_text,
        ))
    return violations


def strip_section_note(notes_text: str) -> str:
    """Remove the 'Section notes: …' line from notes text."""
    lines = notes_text.split("\n")
    kept = [ln for ln in lines if not SECTION_NOTE_RE.match(ln)]
    return "\n".join(kept)


def patch_log_notes(fc, log_id: str, log_type: str, new_notes: str, dry_run: bool) -> bool:
    if dry_run:
        return True
    payload = {
        "data": {
            "type": f"log--{log_type}",
            "id": log_id,
            "attributes": {
                "notes": {"value": new_notes, "format": "default"},
            },
        },
    }
    resp = fc.session.patch(
        f"{fc.hostname}/api/log/{log_type}/{log_id}",
        json=payload,
        headers={"Content-Type": "application/vnd.api+json"},
    )
    return resp.ok


def create_section_observation(fc, section_uuid: str, section_name: str,
                                note_text: str, reporter: str, submitted: str,
                                submission_id: str, timestamp: str,
                                dry_run: bool) -> str | None:
    """Create a section-level observation log (no asset_ids, just location).

    Returns the new log id, or None on failure / dry-run.
    """
    if dry_run:
        return "DRY-RUN-NEW-LOG"
    from datetime import datetime, timezone
    ts_iso = datetime.now(timezone.utc).isoformat()
    name = f"Section observation — {section_name} — {timestamp}"
    body_lines = [
        f"Reporter: {reporter or 'unknown'}",
        f"Submitted: {submitted or timestamp}",
        f"Mode: section_observation",
        f"Section notes: {note_text}",
        "",
        f"[ontology:InteractionStamp] initiator={reporter or 'unknown'} | "
        f"role=farmhand | channel=cleanup_script | executor=farmos_api | "
        f"action=created | target=section_observation | outcome=success | "
        f"ts={ts_iso} | related={section_name}"
        + (f" | submission={submission_id}" if submission_id else "")
        + " | origin=adr_0008_i3_backfill",
    ]
    notes_value = "\n".join(body_lines)

    payload = {
        "data": {
            "type": "log--observation",
            "attributes": {
                "name": name,
                "timestamp": timestamp + "T00:00:00+00:00",
                "status": "done",
                "notes": {"value": notes_value, "format": "default"},
            },
            "relationships": {
                "location": {
                    "data": [{"type": "asset--land", "id": section_uuid}]
                },
            },
        },
    }
    resp = fc.session.post(
        f"{fc.hostname}/api/log/observation",
        json=payload,
        headers={"Content-Type": "application/vnd.api+json"},
    )
    if not resp.ok:
        print(f"    ! create section log failed: {resp.status_code} {resp.text[:200]}",
              file=sys.stderr)
        return None
    return resp.json().get("data", {}).get("id")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--scope", default="P2")
    args = parser.parse_args()

    fc = FarmOSClient()
    fc.connect()

    print(f"Fetching land assets in scope {args.scope}...", file=sys.stderr)
    assets = fetch_land_assets(fc, args.scope)
    sec_uuid = section_uuid_lookup(assets)
    sections = [a.get("attributes", {}).get("name", "") for a in assets
                if "." in a.get("attributes", {}).get("name", "")]
    sections = sorted(set(sections))
    print(f"  {len(sections)} sections to scan", file=sys.stderr)

    all_violations: list[Violation] = []
    for sec in sections:
        vs = scan_section_for_violations(fc, sec, sec_uuid.get(sec, ""))
        if vs:
            print(f"  {sec}: {len(vs)} polluted log(s)", file=sys.stderr)
        all_violations.extend(vs)

    print(f"\nTotal I3 violations found: {len(all_violations)}", file=sys.stderr)

    # Group by (section, submission_id, section_note_text) to create one
    # section-level log per unique (submission, note) tuple.
    groups: dict[tuple, list[Violation]] = defaultdict(list)
    for v in all_violations:
        # Fallback grouping key: if no submission_id, use the timestamp + text hash
        key = (v.section, v.submission_id or f"nosub-{v.timestamp}", v.section_note_text)
        groups[key].append(v)

    print(f"Unique section-note events: {len(groups)}", file=sys.stderr)

    # Execute: create section logs and strip plant-log section_note lines
    stripped = 0
    created = 0
    failures = 0

    for (section, sub_id, text), vs in sorted(groups.items()):
        suuid = sec_uuid.get(section)
        if not suuid:
            print(f"  ! no section UUID for {section}, skipping group", file=sys.stderr)
            continue
        # Pick one violation as representative for reporter/submitted/timestamp
        rep = next((v for v in vs if v.reporter), vs[0])
        new_id = create_section_observation(
            fc, suuid, section, text,
            reporter=rep.reporter, submitted=rep.submitted,
            submission_id=sub_id if not sub_id.startswith("nosub-") else "",
            timestamp=rep.timestamp,
            dry_run=args.dry_run,
        )
        if not new_id:
            failures += 1
            print(f"  ✗ create section log failed: {section} / {text[:60]}")
            continue
        created += 1
        short_id = new_id[:8] if new_id else "?"
        print(f"  + [{section}] section log {short_id} — \"{text[:60]}\" (from {len(vs)} plant log(s))")

        # Strip section-note line from each plant log in the group
        for v in vs:
            clean_notes = strip_section_note(v.original_notes)
            ok = patch_log_notes(fc, v.log_id, v.log_type, clean_notes, args.dry_run)
            if ok:
                stripped += 1
            else:
                failures += 1

    print()
    print("=" * 60)
    print("Summary" + (" (DRY-RUN)" if args.dry_run else ""))
    print("=" * 60)
    print(f"  plant-logs with section_notes stripped: {stripped}")
    print(f"  section-level logs created:             {created}")
    print(f"  failures:                               {failures}")


if __name__ == "__main__":
    raise SystemExit(main())
