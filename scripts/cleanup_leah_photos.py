#!/usr/bin/env python3
"""
cleanup_leah_photos.py — Remove misattributed photos from Leah's April 14
observation logs in farmOS.

Bug context (ADR 0005): Observations.gs `handleGetMedia` returned every
file in the date+section Drive folder, not just the submission's files.
When 15 Leah observations were imported on April 15, each log received the
combined photo pile from its section folder — ~12 photos per log, most of
which depict plants from OTHER observations. The photos are real field data
but are attached to the wrong logs. This script detaches them.

Strategy (Option B from ADR 0005):
  1. Walk each of Leah's 15 observation logs (known by the Leah
     InteractionStamp + April 14 date in P2R5.*)
  2. For each log, identify all attached file--file entities via the
     `image` relationship
  3. PATCH the log to clear its `image` relationship (detach)
  4. DELETE each orphaned file entity (the file IDs are specific to
     these re-uploaded copies, not shared references)

Usage:
    source .env
    python scripts/cleanup_leah_photos.py          # execute
    python scripts/cleanup_leah_photos.py --dry-run # preview only
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import requests
from dotenv import load_dotenv


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_dotenv()
    base_url = os.environ["FARMOS_URL"].rstrip("/")
    client_id = os.environ.get("FARMOS_CLIENT_ID", "farm")
    username = os.environ["FARMOS_USERNAME"]
    password = os.environ["FARMOS_PASSWORD"]
    scope = os.environ.get("FARMOS_SCOPE", "farm_manager")

    # Authenticate
    session = requests.Session()
    token_resp = session.post(f"{base_url}/oauth/token", data={
        "grant_type": "password",
        "client_id": client_id,
        "username": username,
        "password": password,
        "scope": scope,
    })
    token_resp.raise_for_status()
    token = token_resp.json()["access_token"]
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/vnd.api+json",
        "Accept": "application/vnd.api+json",
    })

    # Leah's sections from the April 14 walk (confirmed by earlier investigation)
    leah_sections = ["P2R5.0-8", "P2R5.29-38", "P2R5.44-53"]

    total_logs = 0
    total_files_detached = 0
    total_files_deleted = 0

    for section in leah_sections:
        print(f"\n── {section} ──")

        # Fetch observation logs for this section that include "Leah" in notes
        path = (
            f"/api/log/observation"
            f"?filter[name-contains][condition][path]=name"
            f"&filter[name-contains][condition][operator]=CONTAINS"
            f"&filter[name-contains][condition][value]={section}"
            f"&include=image"
            f"&page[limit]=50"
        )
        resp = session.get(f"{base_url}{path}")
        resp.raise_for_status()
        data = resp.json()

        # Index included file entities
        files_by_id: dict[str, str] = {}
        for inc in data.get("included") or []:
            if inc.get("type") == "file--file":
                files_by_id[inc["id"]] = inc.get("attributes", {}).get("filename", "?")

        for log in data.get("data") or []:
            log_id = log["id"]
            log_name = log.get("attributes", {}).get("name", "")
            notes = ""
            notes_raw = log.get("attributes", {}).get("notes", {})
            if isinstance(notes_raw, dict):
                notes = notes_raw.get("value", "")
            elif isinstance(notes_raw, str):
                notes = notes_raw

            # Only touch Leah's logs
            if "initiator=Leah" not in notes and "Reporter: Leah" not in notes:
                continue

            # Get attached images
            image_rel = (log.get("relationships") or {}).get("image", {})
            rel_data = image_rel.get("data") or []
            if isinstance(rel_data, dict):
                rel_data = [rel_data]
            if not rel_data:
                continue

            file_ids = [e["id"] for e in rel_data if isinstance(e, dict) and "id" in e]
            total_logs += 1

            print(f"  {log_name}")
            print(f"    {len(file_ids)} files attached")

            if args.dry_run:
                print(f"    [dry-run] would detach + delete {len(file_ids)} files")
                total_files_detached += len(file_ids)
                total_files_deleted += len(file_ids)
                continue

            # Step 1: Detach — PATCH the log to clear the image relationship
            patch_payload = {
                "data": {
                    "type": "log--observation",
                    "id": log_id,
                    "relationships": {
                        "image": {
                            "data": [],  # Clear all image attachments
                        }
                    }
                }
            }
            patch_resp = session.patch(
                f"{base_url}/api/log/observation/{log_id}",
                json=patch_payload,
            )
            if patch_resp.ok:
                print(f"    ✓ detached {len(file_ids)} files")
                total_files_detached += len(file_ids)
            else:
                print(f"    ✗ detach failed: HTTP {patch_resp.status_code}")
                continue

            # Step 2: Delete each orphaned file entity
            deleted = 0
            for fid in file_ids:
                del_resp = session.delete(f"{base_url}/api/file/file/{fid}")
                if del_resp.ok or del_resp.status_code == 204:
                    deleted += 1
                else:
                    print(f"    ✗ delete file {fid[:8]}… failed: HTTP {del_resp.status_code}")
            total_files_deleted += deleted
            print(f"    ✓ deleted {deleted}/{len(file_ids)} files")

    print(f"\n{'='*50}")
    print(f"Cleanup complete {'(DRY RUN)' if args.dry_run else ''}")
    print(f"  Logs processed:   {total_logs}")
    print(f"  Files detached:   {total_files_detached}")
    print(f"  Files deleted:    {total_files_deleted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
