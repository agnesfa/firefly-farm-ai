#!/usr/bin/env python3
"""Observation Record Invariant validator + audit tool (ADR 0008).

Checks every observation log against the seven invariants defined in
``claude-docs/adr/0008-observation-record-invariant.md`` and produces a
structured violation backlog.

Phase 1 of the cycle-breaker: run it, read the report, fix by class.

Usage
-----
    # Audit all P2 sections + plant_type references
    python scripts/validate_observations.py --scope P2

    # Audit a single section
    python scripts/validate_observations.py --section P2R2.0-3

    # Audit logs since a date
    python scripts/validate_observations.py --since 2026-04-01

    # Produce JSON for further processing
    python scripts/validate_observations.py --scope P2 --json > backlog.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "mcp-server"))
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from dotenv import load_dotenv

from farmos_client import FarmOSClient
from _paginate import paginate_all

load_dotenv(str(_REPO_ROOT / ".env"))


# ─── Violation model ─────────────────────────────────────────


@dataclass
class Violation:
    log_id: str
    log_name: str
    section: str
    invariant: str   # I1, I2, I3, I4, I5, I6
    severity: str    # "error", "warning", "info"
    detail: str
    remediation: str = ""


# ─── Helpers ─────────────────────────────────────────────────


STOCK_PHOTO_PATTERNS = [
    # URL-encoded scientific names (%C3, %C2, etc.)
    re.compile(r"%[0-9A-F]{2}"),
    # Wikipedia dump common markers
    re.compile(r"wikipedia", re.I),
    re.compile(r"wikimedia", re.I),
    # Köhler's Medicinal Plants illustrations
    re.compile(r"köhler", re.I),
    re.compile(r"K%C3%B6hler", re.I),
    re.compile(r"medizinal", re.I),
    # Scientific-name-only filenames (genus_species format)
    re.compile(r"^[A-Z][a-z]+_[a-z]+(_[0-9]+)?\.(jpg|jpeg|png)$", re.I),
]


FIELD_PHOTO_PATTERNS = [
    # Submission_id prefix: 8 hex chars + underscore
    re.compile(r"^[0-9a-f]{8}_"),
    # Section_id prefix: P#R# or NURS etc.
    re.compile(r"^(P\d+R\d+|NURS|COMP|SPIR)"),
]


def is_stock_photo(filename: str) -> bool:
    if not filename:
        return False
    for p in STOCK_PHOTO_PATTERNS:
        if p.search(filename):
            return True
    return False


def is_field_photo(filename: str) -> bool:
    if not filename:
        return False
    for p in FIELD_PHOTO_PATTERNS:
        if p.match(filename):
            return True
    return False


def _notes_text(log: dict) -> str:
    notes = log.get("attributes", {}).get("notes", {})
    if isinstance(notes, dict):
        return notes.get("value") or ""
    return str(notes or "")


def _log_type(log: dict) -> str:
    t = log.get("type", "")
    if t.startswith("log--"):
        return t[5:]
    return t


# ─── Invariant checkers ──────────────────────────────────────


VALID_LOG_TYPES = {
    "observation", "activity", "transplanting", "seeding", "harvest",
    "input", "maintenance", "medical", "purchase", "sale", "birth", "lab_test",
}


def check_I1_log_type(log: dict, section: str) -> list[Violation]:
    log_id = log["id"]
    name = log.get("attributes", {}).get("name", "?")
    lt = _log_type(log)
    notes = _notes_text(log).lower()

    violations = []

    if lt not in VALID_LOG_TYPES:
        violations.append(Violation(
            log_id=log_id, log_name=name, section=section,
            invariant="I1", severity="error",
            detail=f"Log type '{lt}' is not in the valid set",
            remediation="Change log type to one of observation/activity/transplanting/seeding/harvest",
        ))

    # Heuristic: activity-language in an observation log
    activity_phrases = [
        "chop and drop", "chop-and-drop", "mulching", "mulched",
        "seeded", "sowed", "weeding", "weeded", "pruned", "fertilised",
        "harvested", "transplanted",
    ]
    if lt == "observation":
        for phrase in activity_phrases:
            if phrase in notes:
                violations.append(Violation(
                    log_id=log_id, log_name=name, section=section,
                    invariant="I1", severity="warning",
                    detail=f"Observation log contains activity language '{phrase}' — should likely be an activity log",
                    remediation="Re-classify as activity log or split content",
                ))
                break  # one warning per log is enough

    return violations


def check_I2_asset_attachment(log: dict, section: str) -> list[Violation]:
    log_id = log["id"]
    name = log.get("attributes", {}).get("name", "?")
    rels = log.get("relationships", {})
    asset_refs = (rels.get("asset", {}) or {}).get("data") or []
    loc_refs = (rels.get("location", {}) or {}).get("data") or []
    lt = _log_type(log)

    # Accept any log that has some attachment; only flag "no attachment at all"
    if lt not in ("input", "lab_test") and not asset_refs and not loc_refs:
        return [Violation(
            log_id=log_id, log_name=name, section=section,
            invariant="I2", severity="error",
            detail="Log has no asset and no location attachment",
            remediation="Attach to plant asset(s) + section location, OR to section location alone",
        )]

    return []


SECTION_NOTES_MARKERS = [
    re.compile(r"Section notes?:\s*\S", re.I),
]


def check_I3_notes_hygiene(log: dict, section: str) -> list[Violation]:
    log_id = log["id"]
    name = log.get("attributes", {}).get("name", "?")
    notes = _notes_text(log)
    rels = log.get("relationships", {})
    asset_refs = (rels.get("asset", {}) or {}).get("data") or []

    violations = []

    # I3a — plant-attached log carrying a "Section notes: X" line is the
    # classic fan-out bug (Issue 3 today). Always a violation.
    has_section_note_line = any(p.search(notes) for p in SECTION_NOTES_MARKERS)
    if asset_refs and has_section_note_line:
        # Extract the actual section note text
        m = re.search(r"Section notes?:\s*(.+?)(?:\n|$)", notes, re.I)
        sn_text = m.group(1).strip() if m else "?"
        violations.append(Violation(
            log_id=log_id, log_name=name, section=section,
            invariant="I3", severity="error",
            detail=f"Plant-attached log carries section-level text: 'Section notes: {sn_text}'",
            remediation="Strip 'Section notes: …' line from this log; create/attach a section-level log instead",
        ))

    return violations


def check_I4_photo_uniqueness(log: dict, image_files: list[dict], section: str) -> list[Violation]:
    log_id = log["id"]
    name = log.get("attributes", {}).get("name", "?")

    if not image_files:
        return []

    # Group by filesize — exact duplicates are same content re-uploaded
    by_size: dict[int, list[dict]] = defaultdict(list)
    for f in image_files:
        sz = f.get("attributes", {}).get("filesize", 0)
        by_size[sz].append(f)

    violations = []
    for sz, files in by_size.items():
        if len(files) > 1:
            names = [f.get("attributes", {}).get("filename", "?") for f in files]
            violations.append(Violation(
                log_id=log_id, log_name=name, section=section,
                invariant="I4", severity="error",
                detail=f"{len(files)} photo references with identical filesize {sz} bytes: {names}",
                remediation="Remove duplicate file refs; keep earliest upload only",
            ))

    # Also check for Drupal-rename suffix pattern (filename_0.jpg = same content)
    base_names: dict[str, list[dict]] = defaultdict(list)
    for f in image_files:
        fn = f.get("attributes", {}).get("filename", "?")
        # Strip _N suffix before extension
        base = re.sub(r"_\d+(\.\w+)$", r"\1", fn)
        base_names[base].append(f)
    for base, files in base_names.items():
        if len(files) > 1:
            fns = [f.get("attributes", {}).get("filename", "?") for f in files]
            # Only flag if not already caught by size check
            sizes = set(f.get("attributes", {}).get("filesize", 0) for f in files)
            if len(sizes) > 1:
                # different sizes but Drupal-rename pattern — still suspicious
                violations.append(Violation(
                    log_id=log_id, log_name=name, section=section,
                    invariant="I4", severity="warning",
                    detail=f"Filename base '{base}' appears {len(files)} times: {fns}",
                    remediation="Review — likely duplicate upload with Drupal rename",
                ))

    return violations


def check_I6_attribution(log: dict, section: str) -> list[Violation]:
    log_id = log["id"]
    name = log.get("attributes", {}).get("name", "?")
    status = log.get("attributes", {}).get("status")
    notes = _notes_text(log)

    violations = []

    if not status:
        violations.append(Violation(
            log_id=log_id, log_name=name, section=section,
            invariant="I6", severity="error",
            detail="Log status is null/empty",
            remediation="Set status to 'done' or 'pending' per ADR 0008 I6",
        ))

    # Check for InteractionStamp presence
    if "[ontology:InteractionStamp]" not in notes:
        # Downgrade to warning for legacy logs (before InteractionStamp
        # enforcement) — hard error for post-2026-04-01 logs
        ts = log.get("attributes", {}).get("timestamp", "")
        severity = "error" if ts >= "2026-04-01" else "info"
        violations.append(Violation(
            log_id=log_id, log_name=name, section=section,
            invariant="I6", severity=severity,
            detail="Missing [ontology:InteractionStamp] in notes",
            remediation="Back-fill InteractionStamp line (legacy) or enforce at write (new)",
        ))

    return violations


# ─── Plant_type reference photo audit (I5) ──────────────────


def audit_plant_type_references(fc: FarmOSClient,
                                 plant_types: list[dict],
                                 photo_files_by_id: dict) -> list[Violation]:
    violations = []
    for pt in plant_types:
        species = pt.get("attributes", {}).get("name", "?")
        uuid = pt["id"]

        # Fetch the plant_type with image relationship included
        resp = fc.session.get(
            f"{fc.hostname}/api/taxonomy_term/plant_type/{uuid}",
            params={"include": "image"},
            timeout=15,
        )
        if not resp.ok:
            continue
        data = resp.json()
        rels = (data.get("data", {}).get("relationships", {}).get("image", {}) or {}).get("data")

        if not rels:
            # No photo at all — not a violation, just informational
            continue

        # Multi-valued image field = violation
        if isinstance(rels, list) and len(rels) > 1:
            included = data.get("included", [])
            files = [f for f in included if f.get("type") == "file--file"]
            filenames = [f.get("attributes", {}).get("filename", "?") for f in files]
            violations.append(Violation(
                log_id=uuid, log_name=species, section="[plant_type]",
                invariant="I5", severity="error",
                detail=f"plant_type.image has {len(rels)} files (should be 1): {filenames}",
                remediation="Patch to keep only the best per ranking rules (field > stock, higher score > lower, newer > older)",
            ))
            # Continue — also check if the primary is stock
            files.sort(key=lambda f: f.get("attributes", {}).get("created", ""), reverse=True)
            primary = files[0]
        else:
            ref_id = rels[0]["id"] if isinstance(rels, list) else rels["id"]
            # Fetch the file
            included = data.get("included", [])
            matching = [f for f in included if f.get("id") == ref_id]
            if not matching:
                continue
            primary = matching[0]

        primary_name = primary.get("attributes", {}).get("filename", "?")

        if is_stock_photo(primary_name):
            violations.append(Violation(
                log_id=uuid, log_name=species, section="[plant_type]",
                invariant="I5", severity="warning",
                detail=f"plant_type reference is a stock photo: {primary_name}",
                remediation="If a field photo exists for this species, promote it",
            ))

    return violations


# ─── Audit runner ────────────────────────────────────────────


def audit_section(fc: FarmOSClient, section_id: str) -> list[Violation]:
    violations: list[Violation] = []
    try:
        raw_logs = fc.get_logs(section_id=section_id) or []
    except Exception as e:
        return [Violation(
            log_id="", log_name="", section=section_id,
            invariant="SYSTEM", severity="error",
            detail=f"get_logs failed: {e}", remediation="",
        )]

    for log_short in raw_logs:
        log_id = log_short["id"]
        log_type = _log_type(log_short)
        # Fetch full record with image relationship
        try:
            resp = fc.session.get(
                f"{fc.hostname}/api/log/{log_type}/{log_id}",
                params={"include": "image"},
                timeout=15,
            )
            if not resp.ok:
                continue
            payload = resp.json()
            log = payload.get("data", {})
            log["id"] = log_id  # make sure id is set
            log["type"] = f"log--{log_type}"
            included = payload.get("included", [])
            image_files = [f for f in included if f.get("type") == "file--file"]
        except Exception:
            continue

        violations += check_I1_log_type(log, section_id)
        violations += check_I2_asset_attachment(log, section_id)
        violations += check_I3_notes_hygiene(log, section_id)
        violations += check_I4_photo_uniqueness(log, image_files, section_id)
        violations += check_I6_attribution(log, section_id)

    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--scope", default="P2",
                        help="Row prefix to audit (e.g. P2, P2R2). Default P2.")
    parser.add_argument("--section", default=None,
                        help="Single section to audit (overrides --scope)")
    parser.add_argument("--plant-types", action="store_true", default=True,
                        help="Also audit plant_type reference photos (I5)")
    parser.add_argument("--no-plant-types", dest="plant_types", action="store_false")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON for further processing")
    parser.add_argument("--out", default=None,
                        help="Write report to file instead of stdout")
    args = parser.parse_args()

    fc = FarmOSClient()
    fc.connect()

    # Gather sections via offset-based pagination (scripts/_paginate.py).
    # Filter client-side for names matching the scope prefix AND containing
    # a dot (actual sections, not row-level parents like "P2R2").
    if args.section:
        sections = [args.section]
    else:
        all_assets = paginate_all(fc.session, fc.hostname, "asset/land", sort="name")
        print(f"  (fetched {len(all_assets)} land assets)", file=sys.stderr)
        sections = sorted({
            a.get("attributes", {}).get("name", "")
            for a in all_assets
            if a.get("attributes", {}).get("name", "").startswith(args.scope)
            and "." in a.get("attributes", {}).get("name", "")
        })
        sections = [s for s in sections if s]

    print(f"Auditing {len(sections)} section(s): {', '.join(sections[:5])}{'...' if len(sections) > 5 else ''}",
          file=sys.stderr)

    all_violations: list[Violation] = []
    for sec in sections:
        vs = audit_section(fc, sec)
        all_violations.extend(vs)
        print(f"  {sec}: {len(vs)} violation(s)", file=sys.stderr)

    # Plant_type reference photo audit (only relevant species — those with
    # active plants in the audited sections)
    if args.plant_types:
        print("Auditing plant_type reference photos…", file=sys.stderr)
        # Gather unique plant_type UUIDs from plants in these sections
        unique_types: dict[str, dict] = {}
        for sec in sections:
            plants = fc.get_plant_assets(section_id=sec) or []
            for p in plants:
                type_refs = (p.get("relationships", {}).get("plant_type", {}) or {}).get("data") or []
                for tr in type_refs:
                    tr_id = tr.get("id")
                    if tr_id and tr_id not in unique_types:
                        # Minimal plant_type dict
                        unique_types[tr_id] = {
                            "id": tr_id,
                            "attributes": {"name": p.get("attributes", {}).get("name", "?").split(" - ")[-2]
                                           if " - " in p.get("attributes", {}).get("name", "") else "?"},
                        }
        vs = audit_plant_type_references(fc, list(unique_types.values()), {})
        print(f"  {len(unique_types)} plant_types audited: {len(vs)} violation(s)", file=sys.stderr)
        all_violations.extend(vs)

    # Output
    if args.json:
        output = {
            "scope": args.scope,
            "sections_audited": sections,
            "violations_total": len(all_violations),
            "violations": [asdict(v) for v in all_violations],
        }
        text = json.dumps(output, indent=2)
    else:
        text = _render_markdown(sections, all_violations)

    if args.out:
        Path(args.out).write_text(text)
        print(f"\nWritten: {args.out}", file=sys.stderr)
    else:
        print(text)

    # Exit code: 0 if no errors, 1 if any error-severity violations
    errors = [v for v in all_violations if v.severity == "error"]
    return 1 if errors else 0


def _render_markdown(sections: list[str], violations: list[Violation]) -> str:
    by_invariant = defaultdict(list)
    by_section = defaultdict(list)
    for v in violations:
        by_invariant[v.invariant].append(v)
        by_section[v.section].append(v)

    sev_count = defaultdict(int)
    for v in violations:
        sev_count[v.severity] += 1

    lines = []
    lines.append(f"# Observation Record Invariant — Audit Report")
    lines.append(f"")
    lines.append(f"- **Sections audited:** {len(sections)}")
    lines.append(f"- **Total violations:** {len(violations)}")
    lines.append(f"- **Errors:** {sev_count['error']}  |  **Warnings:** {sev_count['warning']}  |  **Info:** {sev_count['info']}")
    lines.append(f"")

    lines.append(f"## By invariant")
    lines.append(f"")
    for inv in sorted(by_invariant.keys()):
        lines.append(f"### {inv} — {len(by_invariant[inv])} violation(s)")
        # Group by severity within invariant
        by_sev = defaultdict(list)
        for v in by_invariant[inv]:
            by_sev[v.severity].append(v)
        for sev in ("error", "warning", "info"):
            if not by_sev[sev]:
                continue
            lines.append(f"")
            lines.append(f"**{sev.upper()} ({len(by_sev[sev])}):**")
            for v in by_sev[sev][:50]:  # cap per invariant/severity
                lines.append(f"- `{v.section}` / `{v.log_id[:8]}`  — {v.log_name}: {v.detail}")
            if len(by_sev[sev]) > 50:
                lines.append(f"- …and {len(by_sev[sev]) - 50} more")
        lines.append(f"")

    lines.append(f"## By section")
    lines.append(f"")
    for sec in sorted(by_section.keys()):
        lines.append(f"- **{sec}**: {len(by_section[sec])} violation(s) "
                     f"({sum(1 for v in by_section[sec] if v.severity == 'error')} errors, "
                     f"{sum(1 for v in by_section[sec] if v.severity == 'warning')} warnings)")

    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
