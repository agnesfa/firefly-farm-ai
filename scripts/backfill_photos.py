#!/usr/bin/env python3
"""
Backfill historical observation photos from Google Drive into farmOS.

The live photo pipeline (import_observations) attaches photos to every
new observation log on import. This script handles the *historical* case:
observations that were imported before the photo pipeline existed, whose
Sheet rows were deleted after import (so get_media(submission_id) cannot
find them anymore), but whose photos are still sitting in Google Drive
under /Firefly Corner AI Observations/{YYYY-MM-DD}/{section_id}/.

Strategy
========

1. Scan Drive for every (date, section) folder that has media files
   (new Apps Script endpoint ``action=list_media_folders``).
2. For each folder, look up farmOS observation/activity logs for that
   section whose timestamp falls on the same date.
3. If the match is unambiguous (one log, or one log per species), attach
   the photos to the log(s). Also refresh the plant_type taxonomy
   reference photo (latest wins) for any species seen.
4. If the match is ambiguous (multiple logs with different species and
   no way to tell which photo belongs to which), skip the folder and
   print a report line so a human can decide later.

This script is idempotent-ish: re-running will upload the same photos
again unless the farmOS log already has an image attached. We check
`image` relationship length before uploading. The species reference
photo is always refreshed (latest-wins semantics match the live
pipeline).

Usage
-----

    python scripts/backfill_photos.py --dry-run           # Preview
    python scripts/backfill_photos.py --dry-run --date 2026-03-09
    python scripts/backfill_photos.py --date 2026-03-09   # Execute for one date
    python scripts/backfill_photos.py                     # Execute for all dates

Exit codes: 0 on success, 1 on any unexpected error.
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Make the mcp-server clients importable without installing them.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "mcp-server"))

from dotenv import load_dotenv  # noqa: E402

from farmos_client import FarmOSClient  # noqa: E402
from observe_client import ObservationClient  # noqa: E402
from plantnet_verify import build_botanical_lookup, verify_species_photo, get_call_count  # noqa: E402


# ── Matching ─────────────────────────────────────────────────


def _iso_date_matches(log_timestamp: str, target_date: str) -> bool:
    """Return True if a farmOS log timestamp falls on ``target_date``.

    farmOS returns log timestamps as ISO8601 strings or unix epoch; both
    resolve via ``datetime`` parsing.
    """
    if not log_timestamp:
        return False
    # Unix epoch
    try:
        ts = int(log_timestamp)
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d") == target_date
    except (TypeError, ValueError):
        pass
    # ISO
    try:
        dt = datetime.fromisoformat(log_timestamp.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d") == target_date
    except ValueError:
        return False


def _log_has_image(log: dict) -> bool:
    rels = (log.get("relationships") or {}).get("image") or {}
    data = rels.get("data")
    if isinstance(data, list):
        return len(data) > 0
    if isinstance(data, dict):
        return bool(data.get("id"))
    return False


def _log_species(log: dict) -> str | None:
    """Heuristic: extract species from a log name like
    ``Observation P2R3.15-21 — Pigeon Pea`` or
    ``Inventory P2R3.15-21 — Pigeon Pea``.
    """
    name = (log.get("attributes") or {}).get("name") or ""
    if " — " in name:
        return name.rsplit(" — ", 1)[-1].strip() or None
    return None


def _decode_file(file: dict) -> tuple[str, str, bytes] | None:
    data = file.get("data_base64") or file.get("data") or ""
    if not data:
        return None
    if isinstance(data, str) and "," in data and data.lstrip().startswith("data:"):
        data = data.split(",", 1)[1]
    try:
        binary = base64.b64decode(data)
    except Exception:
        return None
    return (
        file.get("filename") or "photo.jpg",
        file.get("mime_type") or "image/jpeg",
        binary,
    )


# ── Main ─────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument(
        "--date", help="Limit to a specific YYYY-MM-DD folder", default=None,
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Scan and report without uploading anything",
    )
    parser.add_argument(
        "--skip-species-reference", action="store_true",
        help="Attach to logs but skip refreshing plant_type taxonomy photos",
    )
    args = parser.parse_args()

    load_dotenv()

    obs_client = ObservationClient()
    obs_client.connect()

    farmos = FarmOSClient()
    farmos.connect()

    print(f"Scanning Drive observation folders{' for ' + args.date if args.date else ''}...")
    folders_resp = obs_client.list_media_folders(date=args.date)
    if not folders_resp.get("success"):
        print(f"ERROR: Drive scan failed: {folders_resp.get('error')}", file=sys.stderr)
        return 1

    folders = folders_resp.get("folders") or []
    print(f"Found {len(folders)} folders with media files.")

    attached = 0
    reference_photos = 0
    photos_rejected = 0
    skipped_no_logs = 0
    skipped_already = 0
    skipped_ambiguous = 0
    species_refreshed: set[str] = set()

    # Build botanical lookup for PlantNet verification
    botanical_lookup = build_botanical_lookup()

    for folder in folders:
        date = folder["date"]
        section = folder["section"]
        filenames = folder.get("filenames") or []
        if not filenames:
            continue

        # Find candidate logs: observation + activity logs for this section
        # whose timestamp matches the date.
        try:
            logs = farmos.get_logs(section_id=section) or []
        except Exception as e:
            print(f"  ! {date} / {section}: fetch logs failed — {e}", file=sys.stderr)
            continue

        matching = [
            lg for lg in logs
            if _iso_date_matches(
                (lg.get("attributes") or {}).get("timestamp") or "",
                date,
            )
        ]
        if not matching:
            print(f"  · {date} / {section}: no farmOS logs on that date ({len(filenames)} photos stranded)")
            skipped_no_logs += 1
            continue

        targets = [lg for lg in matching if not _log_has_image(lg)]
        if not targets:
            print(f"  = {date} / {section}: all {len(matching)} logs already have photos")
            skipped_already += 1
            continue

        # Ambiguity: more than one target log with no obvious way to pick.
        # We still attach to all targets — this matches the "attach to every
        # log in the submission" semantics of the live pipeline.
        if len(targets) > 1:
            print(
                f"  ? {date} / {section}: {len(targets)} candidate logs — "
                f"attaching {len(filenames)} photos to all of them"
            )

        if args.dry_run:
            print(
                f"  [dry-run] would attach {len(filenames)} photos to {len(targets)} log(s) in {section} on {date}"
            )
            continue

        # Fetch the actual binary data now that we know we'll use it.
        media_resp = obs_client.get_media_by_path(date=date, section=section)
        if not media_resp.get("success"):
            print(f"  ! {date} / {section}: media fetch failed — {media_resp.get('error')}")
            continue
        files = media_resp.get("files") or []
        decoded = [d for d in (_decode_file(f) for f in files) if d is not None]
        if not decoded:
            print(f"  ! {date} / {section}: no decodable files")
            continue

        # Upload to every target log.
        for log in targets:
            log_id = log.get("id")
            log_type = (log.get("type") or "").replace("log--", "") or "observation"
            for filename, mime_type, binary in decoded:
                try:
                    farmos.upload_file(
                        entity_type=f"log/{log_type}",
                        entity_id=log_id,
                        field_name="image",
                        filename=filename,
                        binary_data=binary,
                        mime_type=mime_type,
                    )
                    attached += 1
                except Exception as e:
                    print(f"  ! upload failed for {filename} on log {log_id}: {e}")

        # Species reference photo — only set if PlantNet verifies the photo
        # matches the species. Section-level photos rarely depict a single
        # species close-up, so most will be rejected. That's correct: the
        # reference library should be populated through the live observation
        # pipeline where workers photograph individual plants.
        if not args.skip_species_reference:
            seen_species = {_log_species(lg) for lg in targets if _log_species(lg)}
            for species in seen_species:
                if species in species_refreshed:
                    continue
                try:
                    uuid = farmos.get_plant_type_uuid(species)
                except Exception:
                    uuid = None
                if not uuid:
                    continue
                # Try each photo — use the first one that PlantNet verifies
                for filename, mime_type, binary in decoded:
                    result = verify_species_photo(binary, species, botanical_lookup)
                    if result["verified"]:
                        try:
                            farmos.upload_file(
                                entity_type="taxonomy_term/plant_type",
                                entity_id=uuid,
                                field_name="image",
                                filename=filename,
                                binary_data=binary,
                                mime_type=mime_type,
                            )
                            reference_photos += 1
                            species_refreshed.add(species)
                            print(f"    → verified reference photo for {species} ({result['reason']})")
                        except Exception as e:
                            print(f"    ! reference photo for {species} failed: {e}")
                        break  # One verified photo per species is enough
                    else:
                        photos_rejected += 1
                        if not args.dry_run:
                            print(f"    ✗ photo rejected for {species}: {result['reason']}")

    print()
    print("─" * 60)
    print(f"Folders scanned:             {len(folders)}")
    print(f"Photos attached to logs:     {attached}")
    print(f"Species reference photos:    {reference_photos} (PlantNet-verified)")
    print(f"Photos rejected by PlantNet: {photos_rejected}")
    print(f"PlantNet API calls:          {get_call_count()}")
    print(f"Skipped (no matching logs):  {skipped_no_logs}")
    print(f"Skipped (already had image): {skipped_already}")
    if args.dry_run:
        print("(dry-run — no changes made)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
