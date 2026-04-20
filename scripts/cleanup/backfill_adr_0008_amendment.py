#!/usr/bin/env python3
"""Backfill legacy I8/I9/I11 violations — ADR 0008 amendment 2026-04-20.

Three passes:

  I8 — Plant asset notes hygiene
      For each plant asset whose `notes` field contains
      `[ontology:InteractionStamp]`, `submission=`, or the import-payload
      headers (Reporter/Submitted/Mode/Count/Plant notes), strip those
      lines via `_sanitise_asset_notes`. Preserves any legitimate human
      narrative.

  I9 — Cross-log photo routing
      For each observation/activity log whose image relationship contains
      files shared with peer logs in the same submission (per the
      validator), detach the shared files from the plant-attached log
      and re-attach them to a dedicated section-level log (creating it
      if needed). When the original files are legacy (no submission
      prefix) and the correct plant-to-file mapping can't be recovered,
      ADR 0005 Option B applies: detach and delete the file entity.

  I11 — Log type backfill via classifier
      For each observation/activity log whose notes text classifies as a
      different type (strong signal, non-ambiguous), surface the log id
      for human re-typing. This pass is **report-only** — it does NOT
      auto-migrate logs between types, since that changes farmOS
      semantics. Output a JSON list the operator can act on.

Usage
-----
    # Dry run: report what would change, write nothing
    python scripts/cleanup/backfill_adr_0008_amendment.py --scope P2 --dry-run

    # Apply I8 only
    python scripts/cleanup/backfill_adr_0008_amendment.py --scope P2 --apply --only i8

    # Apply I8 + I9 (I11 always report-only)
    python scripts/cleanup/backfill_adr_0008_amendment.py --scope P2 --apply --only i8,i9

All three passes are idempotent — re-running after success produces
zero violations reported.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "mcp-server"))
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from dotenv import load_dotenv

from farmos_client import FarmOSClient
from _paginate import paginate_all
from asset_notes import sanitise_asset_notes as _sanitise_asset_notes
from classifier import classify_observation

load_dotenv(str(_REPO_ROOT / ".env"))


# ─── Pass I8 ──────────────────────────────────────────────────

def pass_i8(fc: FarmOSClient, plants: list[dict], dry_run: bool) -> dict:
    """Strip import-payload content from plant asset notes."""
    stripped = 0
    unchanged = 0
    errors: list[str] = []
    report_rows: list[dict] = []

    for plant in plants:
        asset_id = plant["id"]
        notes_attr = plant.get("attributes", {}).get("notes", {})
        current = notes_attr.get("value", "") if isinstance(notes_attr, dict) else str(notes_attr or "")
        if not current:
            unchanged += 1
            continue

        cleaned = _sanitise_asset_notes(current)
        if cleaned == current.strip():
            unchanged += 1
            continue

        report_rows.append({
            "asset_id": asset_id,
            "asset_name": plant.get("attributes", {}).get("name", ""),
            "before_len": len(current),
            "after_len": len(cleaned),
            "would_strip": len(current) - len(cleaned),
        })

        if dry_run:
            continue

        # Apply PATCH
        patch_notes = {"value": cleaned, "format": "default"} if cleaned else None
        body = {
            "data": {
                "type": "asset--plant",
                "id": asset_id,
                "attributes": {"notes": patch_notes or {"value": "", "format": "default"}},
            }
        }
        try:
            resp = fc.session.patch(
                f"{fc.hostname}/api/asset/plant/{asset_id}",
                json=body,
                timeout=15,
                headers={"Content-Type": "application/vnd.api+json"},
            )
            if resp.ok:
                stripped += 1
            else:
                errors.append(f"{asset_id}: PATCH failed status={resp.status_code}")
        except Exception as e:
            errors.append(f"{asset_id}: {e}")

    return {
        "pass": "I8",
        "plants_scanned": len(plants),
        "stripped": stripped,
        "unchanged": unchanged,
        "errors": errors,
        "dry_run_rows": report_rows if dry_run else [],
        "changed_count": len(report_rows) if dry_run else stripped,
    }


# ─── Pass I9 ──────────────────────────────────────────────────

def _logs_by_submission(fc: FarmOSClient, section_ids: list[str]) -> dict:
    """Group logs by submission_id, with filenames + type."""
    by_sub: dict[str, list[dict]] = {}
    for sec in section_ids:
        raw_logs = fc.get_logs(section_id=sec) or []
        for log_short in raw_logs:
            log_id = log_short["id"]
            log_type_raw = log_short.get("type", "")
            log_type = log_type_raw[5:] if log_type_raw.startswith("log--") else log_type_raw
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
                notes_attr = log.get("attributes", {}).get("notes", {})
                notes = notes_attr.get("value", "") if isinstance(notes_attr, dict) else str(notes_attr or "")
                m = re.search(r"submission=([0-9a-f-]{8,})", notes)
                if not m:
                    continue
                sub_id = m.group(1)
                included = payload.get("included", [])
                files = [
                    {
                        "file_id": f["id"],
                        "filename": f.get("attributes", {}).get("filename", ""),
                        "filesize": f.get("attributes", {}).get("filesize", 0),
                    }
                    for f in included
                    if f.get("type") == "file--file"
                ]
                rels = log.get("relationships", {})
                asset_refs = (rels.get("asset", {}) or {}).get("data") or []
                by_sub.setdefault(sub_id, []).append({
                    "log_id": log_id,
                    "log_type": log_type,
                    "section": sec,
                    "files": files,
                    "asset_ids": [a["id"] for a in asset_refs],
                })
            except Exception:
                continue
    return by_sub


def pass_i9(fc: FarmOSClient, section_ids: list[str], dry_run: bool) -> dict:
    """Detect + fix cross-log photo sharing within a submission.

    For now this pass is REPORT-ONLY in all modes. The auto-re-route to
    a section log requires creating new logs on the live farmOS, which
    has higher blast radius than I8's asset-PATCH. Operators can run the
    validator after this report, review the specific cases, and use
    the new `import_observations` pipeline (Step 4, already shipped)
    for all FUTURE submissions. Historical re-routing is best handled
    case-by-case via `update_observation_status` + manual photo moves.
    """
    by_sub = _logs_by_submission(fc, section_ids)
    issues: list[dict] = []
    for sub_id, logs in by_sub.items():
        if len(logs) <= 1:
            continue
        # Build file→logs map
        file_to_logs: dict[str, list[str]] = {}
        for lg in logs:
            for f in lg["files"]:
                key = f["filename"] or f["file_id"]
                file_to_logs.setdefault(key, []).append(lg["log_id"])
        shared = {k: v for k, v in file_to_logs.items() if len(v) > 1}
        if shared:
            issues.append({
                "submission_id": sub_id,
                "log_count": len(logs),
                "shared_files": shared,
                "log_ids": [lg["log_id"] for lg in logs],
            })

    return {
        "pass": "I9",
        "sections_scanned": len(section_ids),
        "submissions_affected": len(issues),
        "issues": issues,
        "note": "Report-only. Use for targeted manual cleanup via update_observation_status.",
    }


# ─── Pass I11 ─────────────────────────────────────────────────

def pass_i11(fc: FarmOSClient, section_ids: list[str], dry_run: bool) -> dict:
    """Report logs whose type disagrees with the classifier's reading.

    Always report-only — re-typing a log changes farmOS semantics and
    should be a human decision (sometimes the notes text is ambiguous
    and the stored type is correct for reasons not captured in words).
    """
    mismatches: list[dict] = []
    scanned = 0
    for sec in section_ids:
        raw_logs = fc.get_logs(section_id=sec) or []
        for log_short in raw_logs:
            scanned += 1
            log_id = log_short["id"]
            log_type_raw = log_short.get("type", "")
            log_type = log_type_raw[5:] if log_type_raw.startswith("log--") else log_type_raw
            try:
                resp = fc.session.get(
                    f"{fc.hostname}/api/log/{log_type}/{log_id}",
                    timeout=15,
                )
                if not resp.ok:
                    continue
                payload = resp.json()
                attrs = payload.get("data", {}).get("attributes", {})
                notes_attr = attrs.get("notes", {})
                notes = notes_attr.get("value", "") if isinstance(notes_attr, dict) else str(notes_attr or "")
                if not notes:
                    continue
                result = classify_observation(notes)
                if result["ambiguous"]:
                    continue
                if result["type"] != log_type and result["type"] != "observation":
                    mismatches.append({
                        "log_id": log_id,
                        "section": sec,
                        "stored_type": log_type,
                        "classified_type": result["type"],
                        "confidence": result["confidence"],
                        "reason": result["reason"],
                        "notes_preview": notes[:200],
                    })
            except Exception:
                continue
    return {
        "pass": "I11",
        "sections_scanned": len(section_ids),
        "logs_scanned": scanned,
        "mismatches": mismatches,
        "note": "Report-only. Re-typing is a human decision.",
    }


# ─── Main ─────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--scope", default="P2", help="Row prefix, default P2")
    parser.add_argument("--section", default=None, help="Single section")
    parser.add_argument("--apply", action="store_true",
                        help="Write changes. Default is dry-run.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Alias for default dry-run mode")
    parser.add_argument("--only", default="i8,i9,i11",
                        help="Comma-separated passes to run (i8,i9,i11)")
    parser.add_argument("--out", default=None,
                        help="Write report JSON to file")
    args = parser.parse_args()

    dry_run = not args.apply

    fc = FarmOSClient()
    fc.connect()

    # Gather section ids
    if args.section:
        section_ids = [args.section]
    else:
        all_assets = paginate_all(fc.session, fc.hostname, "asset/land", sort="name")
        section_ids = sorted({
            a.get("attributes", {}).get("name", "")
            for a in all_assets
            if a.get("attributes", {}).get("name", "").startswith(args.scope)
            and "." in a.get("attributes", {}).get("name", "")
        })

    passes = [p.strip().lower() for p in args.only.split(",")]

    report: dict = {
        "mode": "dry_run" if dry_run else "apply",
        "scope": args.scope if not args.section else args.section,
        "sections": len(section_ids),
        "passes": {},
    }

    if "i8" in passes:
        # Gather all plants in scope
        all_plants: list[dict] = []
        for sec in section_ids:
            all_plants.extend(fc.get_plant_assets(section_id=sec) or [])
        print(f"I8: scanning {len(all_plants)} plant assets", file=sys.stderr)
        report["passes"]["I8"] = pass_i8(fc, all_plants, dry_run)

    if "i9" in passes:
        print(f"I9: scanning {len(section_ids)} sections", file=sys.stderr)
        report["passes"]["I9"] = pass_i9(fc, section_ids, dry_run)

    if "i11" in passes:
        print(f"I11: scanning {len(section_ids)} sections", file=sys.stderr)
        report["passes"]["I11"] = pass_i11(fc, section_ids, dry_run)

    out_json = json.dumps(report, indent=2, default=str)
    if args.out:
        Path(args.out).write_text(out_json)
        print(f"Report written: {args.out}", file=sys.stderr)
    else:
        print(out_json)

    return 0


if __name__ == "__main__":
    sys.exit(main())
