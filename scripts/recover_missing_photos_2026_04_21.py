"""One-off recovery: attach photos to farmOS logs that imported without them.

Context: on 2026-04-21 evening, ~14 submissions imported to farmOS without their
photos due to two bugs (media_files-column gate + TS uploadFile list-form). Both
fixed in commits 747684e + 39ef04d and deployed. The sheet rows for those
submissions are cleaned (post-import), so the MCP import tool can't re-run them.

This script:
1. For each submission_id, queries farmOS for the log carrying "submission=<id>"
   in its notes InteractionStamp.
2. Fetches Drive media via observe_client.get_media (now JSON-filtered).
3. Uploads each photo to the log's image field via farmos_client.upload_file
   (now list-form-aware).

Safe to re-run — farmOS file uploads dedupe by content hash at the relationship
level; worst case we upload extra blob copies (harmless).
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

# Make the mcp-server module importable
MCP_SERVER_DIR = Path(__file__).resolve().parent.parent / "mcp-server"
sys.path.insert(0, str(MCP_SERVER_DIR))

from farmos_client import FarmOSClient  # noqa: E402
from observe_client import ObservationClient  # noqa: E402


# submission_id -> (log_type, date, section, [explicit_log_id])
# explicit_log_id override is for Sweet Potato → Potato reclass where the
# submission_id isn't in any farmOS log's notes (we created fresh Potato
# asset logs instead of importing the sheet row).
SUBMISSIONS = [
    # P2R4 cowpea comment submissions — imported as section activity logs
    ("2931438d-78e8-412d-80d6-858c97394b57", "activity", "2026-04-21", "P2R4.52-62", None),
    ("9f871544-091a-447a-a858-68c1f10522e1", "activity", "2026-04-21", "P2R4.62-72", None),
    ("15031bc4-25ae-429c-b51a-cf70317a7be2", "activity", "2026-04-21", "P2R4.72-77", None),
    # Sweet Potato → Potato reclass (Agnes + Kacper). Photos attach to the
    # observation log embedded inside the create_plant call
    # (name: "Inventory P2R5.0-8 — Potato" / "Inventory P2R5.38-44 — Potato").
    ("09d7a5c7-4824-421a-8eee-9ba810e3eee6", "observation", "2026-04-21", "P2R5.0-8",
     "1cefe7b7-911a-4f00-aa0b-c12ca4968c17"),  # Potato P2R5.0-8 inventory log
    ("4df82b5a-9e80-429a-8a8d-0517b965a8e7", "observation", "2026-04-21", "P2R5.38-44",
     "070dca41-dab1-4011-a130-e92507681f59"),  # Potato P2R5.38-44 inventory log
    # P2R5.0-8 Sarah's imports from chunks A + B + last
    ("d372a4cb-9a1a-4ead-965a-45cca66c29d1", "observation", "2026-04-21", "P2R5.0-8", None),
    ("bfaba875-ad57-47ed-aadd-393732b74ab8", "observation", "2026-04-21", "P2R5.0-8", None),
    ("54d84a32-ee32-4040-8265-000f13a75ec0", "observation", "2026-04-21", "P2R5.0-8", None),
    ("2b43c51c-f0ec-4f67-b20e-066bbff95166", "observation", "2026-04-21", "P2R5.0-8", None),
    ("abd1a5d9-f518-4a2d-b2cd-c8890eedbe46", "observation", "2026-04-21", "P2R5.0-8", None),
    ("c4747a05-508d-4db3-ab3f-dd9589bd7b6d", "observation", "2026-04-21", "P2R5.0-8", None),
    ("3bd1de47-70a9-4b15-8555-50abafe37132", "observation", "2026-04-21", "P2R5.0-8", None),
    ("711f55f0-5d3d-4ac1-907c-1b86f74e94e0", "observation", "2026-04-21", "P2R5.0-8", None),
    ("2469e343-565c-4e91-a85c-8f7e8b218833", "observation", "2026-04-21", "P2R5.0-8", None),
    ("6a82b5ad-89bf-4097-99d0-165854be8d96", "observation", "2026-04-21", "P2R5.0-8", None),
    ("fdb24bff-6d39-4870-9ea2-44551b463b98", "observation", "2026-04-21", "P2R5.0-8", None),
    # Radish from tonight's first post-patch test (failed with upload_returned_null)
    ("0758caf2-c714-490a-a0ab-c8c2ce30a445", "observation", "2026-04-21", "P2R5.22-29", None),
]


def find_log_by_submission(client: FarmOSClient, submission_id: str, log_type: str) -> dict | None:
    """Return the first log whose notes contain 'submission=<id>'."""
    assert client.hostname, f"client.hostname is {client.hostname!r}, session={client.session!r}, connected={client._connected}"
    path = f"/api/log/{log_type}"
    # Drupal JSON:API supports CONTAINS on text fields
    params = {
        "filter[notes.value][operator]": "CONTAINS",
        "filter[notes.value][value]": f"submission={submission_id}",
    }
    url = f"{client.hostname}{path}?" + "&".join(f"{k}={v}" for k, v in params.items())
    resp = client.session.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json().get("data", [])
    return data[0] if data else None


def recover(
    submission_id: str,
    log_type: str,
    date: str,
    section: str,
    explicit_log_id: str | None,
    client: FarmOSClient,
    obs: ObservationClient,
) -> dict:
    if explicit_log_id:
        log_id = explicit_log_id
        log_name = "(explicit log id override)"
    else:
        log = find_log_by_submission(client, submission_id, log_type)
        if not log:
            return {"submission_id": submission_id, "status": "log_not_found"}
        log_id = log["id"]
        log_name = log["attributes"].get("name", "")

    # Use get_media_by_path which doesn't need the sheet row to still exist.
    # It returns every file in the (date, section) folder; we filter by the
    # 8-char submission_id prefix client-side (same rule as handleGetMedia).
    prefix = submission_id[:8]
    media_resp = obs.get_media_by_path(date, section)
    if not media_resp.get("success"):
        return {
            "submission_id": submission_id,
            "log_id": log_id,
            "status": "media_fetch_failed",
            "error": media_resp.get("error"),
        }

    all_files = media_resp.get("files", [])
    # Apply same filters as handleGetMedia: skip .json, filter by prefix.
    files = [
        f for f in all_files
        if not f.get("filename", "").lower().endswith(".json")
        and f.get("filename", "").startswith(prefix + "_")
    ]
    uploaded: list[str] = []
    errors: list[str] = []

    for f in files:
        filename = f.get("filename", "")
        mime = f.get("mime_type", "image/jpeg")
        try:
            raw = base64.b64decode(f["data_base64"])
        except Exception as exc:
            errors.append(f"decode_failed {filename}: {exc}")
            continue
        try:
            file_id = client.upload_file(
                f"log/{log_type}", log_id, "image", filename, raw, mime,
            )
            if file_id:
                uploaded.append(file_id)
            else:
                errors.append(f"upload_returned_null {filename}")
        except Exception as exc:
            errors.append(f"upload_threw {filename}: {exc}")

    status = "ok" if uploaded and not errors else "partial" if uploaded else "failed"
    if not files:
        status = "no_photos_in_drive"

    return {
        "submission_id": submission_id,
        "log_id": log_id,
        "log_name": log_name,
        "status": status,
        "photos_recovered": len(uploaded),
        "photos_total": len(files),
        "drive_folder_total": len(all_files),
        "errors": errors,
    }


def main() -> int:
    import os
    # Find and load .env from repo root (walk up from script location)
    script_dir = Path(__file__).resolve().parent
    candidates = [
        script_dir.parent / ".env",                  # worktree root
        script_dir.parent.parent.parent.parent / ".env",  # grandparent (main repo from worktree)
        Path("/Users/agnes/Repos/FireflyCorner/.env"),
    ]
    from dotenv import load_dotenv
    for env_path in candidates:
        if env_path.exists() and load_dotenv(env_path):
            print(f"Loaded env from {env_path}")
            break
    else:
        raise RuntimeError(f"No .env found in: {candidates}")

    client = FarmOSClient()
    client.connect()
    print(f"farmOS hostname: {client.hostname}")
    obs = ObservationClient()
    obs.connect()
    print(f"Observe endpoint: {obs.endpoint}")

    results = []
    for sub_id, log_type, date, section, explicit_log_id in SUBMISSIONS:
        print(f"Recovering {sub_id} ({log_type} in {section})...", flush=True)
        try:
            result = recover(sub_id, log_type, date, section, explicit_log_id, client, obs)
        except Exception as exc:
            result = {"submission_id": sub_id, "status": "exception", "error": str(exc)}
        print(f"  -> {result.get('status')}: "
              f"{result.get('photos_recovered', 0)}/{result.get('photos_total', 0)} photos"
              + (f" errors={result['errors']}" if result.get("errors") else ""))
        results.append(result)

    total_recovered = sum(r.get("photos_recovered", 0) for r in results)
    total_ok = sum(1 for r in results if r.get("status") == "ok")
    total_partial = sum(1 for r in results if r.get("status") == "partial")
    total_failed = sum(1 for r in results if r.get("status") in ("failed", "log_not_found", "media_fetch_failed", "exception"))

    print("\n=== RECOVERY SUMMARY ===")
    print(f"Submissions processed: {len(results)}")
    print(f"  fully recovered: {total_ok}")
    print(f"  partial:         {total_partial}")
    print(f"  failed:          {total_failed}")
    print(f"Total photos recovered: {total_recovered}")

    # Write detailed json for audit
    out = Path(__file__).parent / "recover_missing_photos_2026_04_21.results.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"\nDetailed results: {out}")

    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
