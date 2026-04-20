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
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from dotenv import load_dotenv
from farmos_client import FarmOSClient
from _paginate import paginate_offset, paginate_all

load_dotenv(str(_REPO_ROOT / ".env"))


STOCK_PATTERNS = [
    re.compile(r"%[0-9A-F]{2}"),
    re.compile(r"wikipedia|wikimedia|köhler|medizinal", re.I),
    re.compile(r"^[A-Z][a-z]+_[a-z]+(_[0-9]+)?\.(jpg|jpeg|png)$", re.I),
]
# Tiered field-photo classification.
# Higher tier = better candidate for species reference photo.
FIELD_SUBMISSION_PLANT = re.compile(r"^[0-9a-f]{8}_.+_plant_")   # tier 3 — submission + plant-specific
FIELD_SUBMISSION = re.compile(r"^[0-9a-f]{8}_")                  # tier 3 — submission-prefixed (fallback)
FIELD_SECTION_PLANT = re.compile(r"^(P\d+R\d+|NURS|COMP|SPIR)\S*_plant_")  # tier 2
FIELD_SECTION_SECTION = re.compile(r"^(P\d+R\d+|NURS|COMP|SPIR)\S*_section_")  # tier 1 — multi-plant, weak reference


def is_stock(fn: str) -> bool:
    return any(p.search(fn or "") for p in STOCK_PATTERNS)


def field_tier(fn: str) -> int:
    """Rank field photos. Higher = better species reference candidate.

    3: plant-specific, submission-id-prefixed (best — QR observation of one plant)
    3: submission-id-prefixed without _plant_ (still user-submitted, plant-specific in practice)
    2: section-prefixed AND contains _plant_ (plant-specific import)
    1: section-prefixed with _section_ (multi-plant frame, weak reference)
    0: not a field photo
    """
    if not fn:
        return 0
    if FIELD_SUBMISSION_PLANT.match(fn):
        return 3
    if FIELD_SUBMISSION.match(fn):
        return 3
    if FIELD_SECTION_PLANT.match(fn):
        return 2
    if FIELD_SECTION_SECTION.match(fn):
        return 1
    return 0


def is_field(fn: str) -> bool:
    return field_tier(fn) > 0


def file_record(f):
    fn = f.get("attributes", {}).get("filename", "")
    tier = field_tier(fn)
    return {
        "id": f["id"],
        "filename": fn,
        "filesize": f.get("attributes", {}).get("filesize", 0),
        "created": f.get("attributes", {}).get("created", ""),
        "is_field": tier > 0,
        "is_stock": is_stock(fn),
        "field_tier": tier,
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
    """All active plant assets matching this plant_type.

    Uses offset-based pagination via the shared `_paginate` helper to
    avoid the farmOS links.next 250-item bug (see architecture #11).
    """
    return paginate_all(
        fc.session, fc.hostname, "asset/plant",
        filters={"plant_type.id": plant_type_uuid, "status": "active"},
        sort="drupal_internal__id",
    )


def get_field_photos_from_plant_logs(fc, plant_asset_ids, cache):
    """Collect all field-photo file records across logs on these plants.

    Uses offset pagination (via `_paginate`) for each per-plant log
    query. Per-plant log counts are small so pagination is mainly a
    correctness guarantee, not a scale concern.
    """
    candidates = []
    for pid in plant_asset_ids[:20]:
        if pid in cache:
            candidates.extend(cache[pid])
            continue
        per_plant = []
        for lg, included in paginate_offset(
            fc.session, fc.hostname, "log/observation",
            filters={"asset.id": pid},
            include="image",
            sort="drupal_internal__id",
        ):
            img_refs = ((lg.get("relationships", {}).get("image") or {}).get("data")) or []
            if isinstance(img_refs, dict):
                img_refs = [img_refs]
            for ref in img_refs:
                f = included.get(("file--file", ref.get("id", "")))
                if not f:
                    continue
                rec = file_record(f)
                if rec["is_field"]:
                    per_plant.append(rec)
        cache[pid] = per_plant
        candidates.extend(per_plant)
    return candidates


def pick_best(files):
    """Best-field-photo per I5 ranking rules.

    Sort by: field_tier (desc), created (desc).
    tier 3 = plant-specific submission photo (best)
    tier 2 = plant-specific section-import photo
    tier 1 = section-level multi-plant photo (weak — avoid if possible)
    tier 0 = stock
    """
    if not files:
        return None
    sorted_files = sorted(
        files,
        key=lambda f: (f.get("field_tier", 1 if f["is_field"] else 0), f["created"]),
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

    # Gather all active plant_types used by plants in scope sections.
    # Offset-based pagination via the shared helper — avoids the farmOS
    # links.next 250-item bug (arch decision #11). We have 669 active
    # plants total; with links.next the alphabetically-late plants were
    # silently dropped, and any plant_type only used by those plants
    # never got checked.
    print("Gathering plant_types in scope...", file=sys.stderr)
    all_plants = []
    all_plant_types = {}  # uuid -> name
    for p, included in paginate_offset(
        fc.session, fc.hostname, "asset/plant",
        filters={"status": "active"},
        include="plant_type",
        sort="drupal_internal__id",
    ):
        name = p.get("attributes", {}).get("name", "")
        if name and args.scope in name:
            all_plants.append(p)
        # Merge included plant_types across pages
        for key, inc in included.items():
            if key[0] == "taxonomy_term--plant_type":
                all_plant_types[key[1]] = inc.get("attributes", {}).get("name", "?")

    # Filter to plant_types that actually have plants in P2
    used_plant_types = set()
    for p in all_plants:
        for t in (p.get("relationships", {}).get("plant_type", {}) or {}).get("data", []) or []:
            used_plant_types.add(t["id"])

    to_check = sorted([(uuid, all_plant_types.get(uuid, uuid)) for uuid in used_plant_types],
                      key=lambda x: x[1])
    print(f"  {len(all_plants)} active plants in {args.scope}, {len(to_check)} plant_types to check", file=sys.stderr)

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

        # Compute the best candidate available ANYWHERE:
        # 1. The plant_type's current files
        # 2. Field photos on the plant logs of active plants of this species
        # Pick the highest-ranked. Only skip if current state already matches
        # the best candidate (i.e., no-op).

        current_best = pick_best(files)
        plants_of_type = get_active_plants_of_type(fc, uuid, limit=20)
        plant_ids = [p["id"] for p in plants_of_type]
        log_field_photos = get_field_photos_from_plant_logs(fc, plant_ids, plant_log_cache)

        all_candidates = list(files) + list(log_field_photos)
        best = pick_best(all_candidates)

        # No-op case: already pointing at the best candidate
        if len(files) == 1 and best and best["id"] == files[0]["id"]:
            if files[0]["field_tier"] >= 2:
                stats["already_plant_specific"] += 1
            elif files[0]["field_tier"] == 1:
                stats["already_section_level_no_better"] += 1
                print(f"  · {name:<35}  section-level photo (tier 1), no plant-specific available — kept")
            else:
                stats["already_stock_no_field_available"] += 1
            continue

        if not best:
            stats["no_candidate"] += 1
            continue

        # Execute: patch to single file with the best candidate
        old_desc = f"{len(files)} file(s), current tier {current_best['field_tier']}"
        new_tier = best.get("field_tier", 0)
        tier_labels = {3: "plant-specific/submission", 2: "plant-specific/import", 1: "section-level", 0: "stock"}
        if patch_single(fc, uuid, best["id"], dry_run=args.dry_run):
            # Categorise the upgrade for reporting
            if current_best["field_tier"] < new_tier:
                stats[f"upgraded_to_tier_{new_tier}"] += 1
                mark = "✓"
            elif len(files) > 1 and new_tier == current_best["field_tier"]:
                stats["collapsed_to_single"] += 1
                mark = "~"
            else:
                stats["patched_other"] += 1
                mark = "~"
            actions.append((f"tier{current_best['field_tier']}→tier{new_tier}", name, best["filename"]))
            print(f"  {mark} {name:<35} → {tier_labels.get(new_tier,'?')} {best['filename']}  ({old_desc} → tier {new_tier})")
        else:
            stats["patch_failed"] += 1

    print()
    print("=" * 60)
    print("Summary" + (" (DRY-RUN)" if args.dry_run else ""))
    print("=" * 60)
    for k, v in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"  {k:<32} {v}")


if __name__ == "__main__":
    raise SystemExit(main())
