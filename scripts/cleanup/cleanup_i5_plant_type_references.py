#!/usr/bin/env python3
"""I5 cleanup — plant_type reference photos (ADR 0008).

For each plant_type with active plants in P2, enforce invariant I5:
  * single-valued image relationship
  * prefer a field photo over a stock photo
  * on ties, prefer the newest upload

Resolution rules (applied in order):

  1. Scan the plant_type's current image files.
  2. If any of them is a field photo (submission_id or section_id prefix),
     pick the newest field photo → patch relationship to that single file.
  3. If all current files are stock, scan the observation logs of active
     plants of that species for a field photo. Pick the newest → patch
     the plant_type relationship to add-then-keep-only that file.
  4. If no field photo anywhere, leave as-is (pick newest stock if
     multi-valued so we at least collapse to single-valued).

Usage
-----
    python scripts/cleanup/cleanup_i5_plant_type_references.py --dry-run
    python scripts/cleanup/cleanup_i5_plant_type_references.py
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "mcp-server"))

from dotenv import load_dotenv
from farmos_client import FarmOSClient

load_dotenv(str(_REPO_ROOT / ".env"))


STOCK_PATTERNS = [
    re.compile(r"%[0-9A-F]{2}"),
    re.compile(r"wikipedia|wikimedia|köhler|medizinal", re.I),
    re.compile(r"^[A-Z][a-z]+_[a-z]+(_[0-9]+)?\.(jpg|jpeg|png)$", re.I),
]
FIELD_PATTERNS = [
    re.compile(r"^[0-9a-f]{8}_"),
    re.compile(r"^(P\d+R\d+|NURS|COMP|SPIR)"),
]


def is_stock(fn: str) -> bool:
    return any(p.search(fn or "") for p in STOCK_PATTERNS)


def is_field(fn: str) -> bool:
    return any(p.match(fn or "") for p in FIELD_PATTERNS)


def file_record(f):
    return {
        "id": f["id"],
        "filename": f.get("attributes", {}).get("filename", ""),
        "filesize": f.get("attributes", {}).get("filesize", 0),
        "created": f.get("attributes", {}).get("created", ""),
        "is_field": is_field(f.get("attributes", {}).get("filename", "")),
        "is_stock": is_stock(f.get("attributes", {}).get("filename", "")),
    }


def get_plant_type_files(fc, uuid):
    resp = fc.session.get(
        f"{fc.hostname}/api/taxonomy_term/plant_type/{uuid}",
        params={"include": "image"},
        timeout=15,
    )
    if not resp.ok:
        return None, []
    data = resp.json()
    rels = (data.get("data", {}).get("relationships", {}).get("image", {}) or {}).get("data") or []
    if isinstance(rels, dict):
        rels = [rels]
    included = data.get("included", [])
    files = [file_record(f) for f in included if f.get("type") == "file--file"]
    return data["data"], files


def get_active_plants_of_type(fc, plant_type_uuid, limit=50):
    """All active plant assets matching this plant_type (paginated)."""
    all_plants = []
    url = (f"{fc.hostname}/api/asset/plant"
           f"?filter[plant_type.id]={plant_type_uuid}"
           f"&filter[status]=active&page[limit]=50")
    guard = 0
    while url and guard < 10:
        resp = fc.session.get(url, timeout=30)
        if not resp.ok:
            break
        body = resp.json()
        all_plants.extend(body.get("data", []))
        nxt = body.get("links", {}).get("next", {})
        url = nxt.get("href") if isinstance(nxt, dict) else nxt
        guard += 1
    return all_plants


def get_field_photos_from_plant_logs(fc, plant_asset_ids, cache):
    """Collect all field-photo file records across logs on these plants."""
    candidates = []
    # Approach: query observation logs filtered by asset ID
    for pid in plant_asset_ids[:20]:  # cap to avoid huge scans
        if pid in cache:
            candidates.extend(cache[pid])
            continue
        per_plant = []
        url = (f"{fc.hostname}/api/log/observation"
               f"?filter[asset.id]={pid}"
               f"&include=image&page[limit]=50")
        guard = 0
        while url and guard < 5:
            resp = fc.session.get(url, timeout=30)
            if not resp.ok:
                break
            body = resp.json()
            files_by_id = {
                f["id"]: f
                for f in body.get("included", [])
                if f.get("type") == "file--file"
            }
            for lg in body.get("data", []):
                img_refs = ((lg.get("relationships", {}).get("image") or {}).get("data")) or []
                if isinstance(img_refs, dict):
                    img_refs = [img_refs]
                for ref in img_refs:
                    f = files_by_id.get(ref.get("id"))
                    if not f:
                        continue
                    rec = file_record(f)
                    if rec["is_field"]:
                        per_plant.append(rec)
            nxt = body.get("links", {}).get("next", {})
            url = nxt.get("href") if isinstance(nxt, dict) else nxt
            guard += 1
        cache[pid] = per_plant
        candidates.extend(per_plant)
    return candidates


def pick_best(files):
    """Best-field-photo per I5 ranking rules.
    Sort by: field > stock (desc), created (desc)."""
    if not files:
        return None
    sorted_files = sorted(
        files,
        key=lambda f: (1 if f["is_field"] else 0, f["created"]),
        reverse=True,
    )
    return sorted_files[0]


def patch_single(fc, plant_type_uuid, file_id, dry_run=False):
    if dry_run:
        return True
    resp = fc.session.patch(
        f"{fc.hostname}/api/taxonomy_term/plant_type/{plant_type_uuid}/relationships/image",
        json={"data": [{"type": "file--file", "id": file_id}]},
        headers={"Content-Type": "application/vnd.api+json"},
    )
    return resp.ok


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--scope", default="P2", help="Row prefix (default P2)")
    args = parser.parse_args()

    fc = FarmOSClient()
    fc.connect()

    # Gather all active plant_types used by plants in scope sections
    print("Gathering plant_types in scope...", file=sys.stderr)
    url = (f"{fc.hostname}/api/asset/plant"
           f"?filter[status]=active&page[limit]=50&include=plant_type")
    all_plants = []
    all_plant_types = {}  # uuid -> name
    guard = 0
    while url and guard < 30:
        resp = fc.session.get(url, timeout=30)
        if not resp.ok:
            break
        body = resp.json()
        for p in body.get("data", []):
            name = p.get("attributes", {}).get("name", "")
            if name and any(name.find(f"- {args.scope}") >= 0 for _ in [0]) and (
                args.scope in name
            ):
                all_plants.append(p)
        for inc in body.get("included", []):
            if inc.get("type") == "taxonomy_term--plant_type":
                all_plant_types[inc["id"]] = inc.get("attributes", {}).get("name", "?")
        nxt = body.get("links", {}).get("next", {})
        url = nxt.get("href") if isinstance(nxt, dict) else nxt
        guard += 1

    # Filter to plant_types that actually have plants in P2
    used_plant_types = set()
    for p in all_plants:
        for t in (p.get("relationships", {}).get("plant_type", {}) or {}).get("data", []) or []:
            used_plant_types.add(t["id"])

    to_check = sorted([(uuid, all_plant_types.get(uuid, uuid)) for uuid in used_plant_types],
                      key=lambda x: x[1])
    print(f"  {len(to_check)} plant_types to check", file=sys.stderr)

    plant_log_cache = {}
    stats = defaultdict(int)
    actions = []

    for uuid, name in to_check:
        term, files = get_plant_type_files(fc, uuid)
        if not term:
            stats["fetch_error"] += 1
            continue

        if not files:
            stats["no_image"] += 1
            continue

        # Case A: already single-valued field photo — nothing to do
        if len(files) == 1 and files[0]["is_field"]:
            stats["already_field_single"] += 1
            continue

        # Case B: multi-valued with at least one field photo
        field_files = [f for f in files if f["is_field"]]
        if len(files) > 1 and field_files:
            best = pick_best(field_files)
            if patch_single(fc, uuid, best["id"], dry_run=args.dry_run):
                stats["multi_to_field"] += 1
                actions.append(("multi→field", name, best["filename"]))
                print(f"  ✓ {name:<35} → field {best['filename']}  ({len(files)} → 1)")
            else:
                stats["patch_failed"] += 1
            continue

        # Case C: single-valued stock — look for field photo in plant logs
        if len(files) == 1 and files[0]["is_stock"]:
            plants_of_type = get_active_plants_of_type(fc, uuid, limit=20)
            plant_ids = [p["id"] for p in plants_of_type]
            log_field_photos = get_field_photos_from_plant_logs(fc, plant_ids, plant_log_cache)
            if log_field_photos:
                best = pick_best(log_field_photos)
                if patch_single(fc, uuid, best["id"], dry_run=args.dry_run):
                    stats["stock_to_field"] += 1
                    actions.append(("stock→field", name, best["filename"]))
                    print(f"  ✓ {name:<35} → field {best['filename']}  (was stock-only)")
                else:
                    stats["patch_failed"] += 1
            else:
                stats["stock_no_field_available"] += 1
                print(f"  · {name:<35}  stock-only, no field photo in logs — skipped")
            continue

        # Case D: multi-valued all stock — look for field photo in plant logs
        # first (same as Case C), only fall back to collapsing to newest stock
        # if no field photo exists anywhere.
        if len(files) > 1 and not field_files:
            plants_of_type = get_active_plants_of_type(fc, uuid, limit=20)
            plant_ids = [p["id"] for p in plants_of_type]
            log_field_photos = get_field_photos_from_plant_logs(fc, plant_ids, plant_log_cache)
            if log_field_photos:
                best = pick_best(log_field_photos)
                if patch_single(fc, uuid, best["id"], dry_run=args.dry_run):
                    stats["multi_stock_to_field"] += 1
                    actions.append(("multi-stock→field", name, best["filename"]))
                    print(f"  ✓ {name:<35} → field {best['filename']}  ({len(files)} → 1, was all stock)")
                continue
            best = pick_best(files)
            if patch_single(fc, uuid, best["id"], dry_run=args.dry_run):
                stats["multi_stock_collapsed"] += 1
                actions.append(("multi-stock-collapsed", name, best["filename"]))
                print(f"  ~ {name:<35} → stock (collapsed) {best['filename']}  ({len(files)} → 1, no field photo)")

    print()
    print("=" * 60)
    print("Summary" + (" (DRY-RUN)" if args.dry_run else ""))
    print("=" * 60)
    for k, v in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"  {k:<32} {v}")


if __name__ == "__main__":
    raise SystemExit(main())
