#!/usr/bin/env python3
"""I4 cleanup — duplicate photo references on logs (ADR 0008).

When the Railway backend silently completed an import that the MCP
response reported as failed, our manual attach-retry script re-attached
every photo. Result: every photo ended up referenced twice on each
log, distinguishable by Drupal's `_0` filename suffix but identical in
content.

This script scans every observation / activity log in scope, detects
duplicate file references (exact filesize match within a log's image
relationship), and patches the relationship to keep only the earliest
upload per content-hash.

Usage
-----
    python scripts/cleanup/cleanup_i4_photo_duplicates.py --dry-run
    python scripts/cleanup/cleanup_i4_photo_duplicates.py
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "mcp-server"))
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from dotenv import load_dotenv
from farmos_client import FarmOSClient
from _paginate import paginate_all

load_dotenv(str(_REPO_ROOT / ".env"))


def fetch_land_sections(fc, scope: str) -> list[str]:
    """Offset-based pagination — see scripts/_paginate.py docstring."""
    all_assets = paginate_all(
        fc.session, fc.hostname, "asset/land",
        sort="name",
    )
    return sorted({
        a.get("attributes", {}).get("name", "")
        for a in all_assets
        if a.get("attributes", {}).get("name", "").startswith(scope)
        and "." in a.get("attributes", {}).get("name", "")
    })


def scan_log_for_dupes(fc, log_id: str, log_type: str) -> list[dict]:
    """Return dedup plan for this log: list of file refs to KEEP (drop the rest)."""
    resp = fc.session.get(
        f"{fc.hostname}/api/log/{log_type}/{log_id}",
        params={"include": "image"}, timeout=15,
    )
    if not resp.ok:
        return None
    data = resp.json()
    rels = ((data.get("data", {}).get("relationships", {}).get("image") or {}).get("data")) or []
    if isinstance(rels, dict):
        rels = [rels]
    included = data.get("included", [])
    files_by_id = {
        f["id"]: f for f in included if f.get("type") == "file--file"
    }

    # Group by filesize (duplicates have exact same size)
    by_size = defaultdict(list)
    for ref in rels:
        f = files_by_id.get(ref["id"])
        if not f:
            continue
        size = f.get("attributes", {}).get("filesize", 0)
        by_size[size].append(f)

    if not any(len(v) > 1 for v in by_size.values()):
        return None  # no dupes

    # For each size bucket, keep the earliest-created file
    kept: list[dict] = []
    for size, files in by_size.items():
        if len(files) == 1:
            kept.append(files[0])
        else:
            files_sorted = sorted(files, key=lambda f: f.get("attributes", {}).get("created", ""))
            kept.append(files_sorted[0])
            # drop the rest

    return kept


def patch_log_images(fc, log_id: str, log_type: str, kept_files: list[dict], dry_run: bool) -> bool:
    if dry_run:
        return True
    new_rels = [{"type": "file--file", "id": f["id"]} for f in kept_files]
    resp = fc.session.patch(
        f"{fc.hostname}/api/log/{log_type}/{log_id}/relationships/image",
        json={"data": new_rels},
        headers={"Content-Type": "application/vnd.api+json"},
    )
    return resp.ok


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--scope", default="P2")
    args = parser.parse_args()

    fc = FarmOSClient()
    fc.connect()

    print(f"Scanning {args.scope} sections for duplicate photo refs...", file=sys.stderr)
    sections = fetch_land_sections(fc, args.scope)
    print(f"  {len(sections)} sections", file=sys.stderr)

    patched = 0
    failures = 0
    scanned = 0
    deduped_refs_total = 0

    for sec in sections:
        logs = fc.get_logs(section_id=sec) or []
        for log_short in logs:
            log_id = log_short["id"]
            log_type = log_short.get("type", "").replace("log--", "")
            scanned += 1
            kept = scan_log_for_dupes(fc, log_id, log_type)
            if kept is None:
                continue
            # Count how many refs we're dropping
            total_refs = 0
            resp = fc.session.get(
                f"{fc.hostname}/api/log/{log_type}/{log_id}",
                timeout=15,
            )
            if resp.ok:
                rels = ((resp.json().get("data", {}).get("relationships", {}).get("image") or {}).get("data")) or []
                if isinstance(rels, dict):
                    rels = [rels]
                total_refs = len(rels)
            dropped = total_refs - len(kept)
            if dropped <= 0:
                continue
            kept_names = [f.get("attributes", {}).get("filename", "?") for f in kept]
            name = log_short.get("name", "?")
            if patch_log_images(fc, log_id, log_type, kept, args.dry_run):
                patched += 1
                deduped_refs_total += dropped
                print(f"  ✓ {sec}/{log_id[:8]} — {name}: dropped {dropped}, kept {kept_names}")
            else:
                failures += 1
                print(f"  ✗ {sec}/{log_id[:8]}: patch failed")

    print()
    print("=" * 60)
    print("Summary" + (" (DRY-RUN)" if args.dry_run else ""))
    print("=" * 60)
    print(f"  Logs scanned:           {scanned}")
    print(f"  Logs with duplicates:   {patched + failures}")
    print(f"  Successfully deduped:   {patched}")
    print(f"  Duplicate refs removed: {deduped_refs_total}")
    print(f"  Failures:               {failures}")


if __name__ == "__main__":
    raise SystemExit(main())
