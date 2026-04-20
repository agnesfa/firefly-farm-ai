#!/usr/bin/env python3
"""Revert plant_type reference photos from tier-1 (section-level multi-plant)
back to stock, where no plant-specific (tier 2+) photo is available.

Rationale: today's cleanup_i5 ran before the tier classifier was
added, so 16 species got promoted to tier-1 section-level photos that
mislead viewers (same multi-plant shot attached to multiple species
pages). Per Agnes's decision 2026-04-20, revert those to stock — an
honest "no field photo yet" signal beats a misleading field photo.

This script:
  1. Enumerates all plant_types in scope.
  2. Finds those whose current single image is tier-1 (matches
     FIELD_SECTION_SECTION pattern).
  3. Searches the farmOS file collection for a stock photo matching the
     species's botanical name (from knowledge/plant_types.csv).
  4. Patches the plant_type.image relationship to the stock photo.

Usage
-----
    python scripts/cleanup/revert_tier1_to_stock.py --dry-run
    python scripts/cleanup/revert_tier1_to_stock.py
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import urllib.parse
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "mcp-server"))
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from dotenv import load_dotenv
from farmos_client import FarmOSClient
from _paginate import paginate_offset, paginate_all

load_dotenv(str(_REPO_ROOT / ".env"))


FIELD_SECTION_SECTION = re.compile(r"^(P\d+R\d+|NURS|COMP|SPIR)\S*_section_")
STOCK_MARKERS = [
    re.compile(r"%[0-9A-F]{2}"),
    re.compile(r"wikipedia|wikimedia|köhler|medizinal", re.I),
    re.compile(r"^[A-Z][a-z]+_[a-z]+", re.I),  # genus_species pattern
]


def is_tier1_multi_plant(filename: str) -> bool:
    return bool(FIELD_SECTION_SECTION.match(filename or ""))


def is_stock(filename: str) -> bool:
    return any(p.search(filename or "") for p in STOCK_MARKERS)


def load_botanical_lookup() -> dict[str, str]:
    """{farmos_name: botanical_name}."""
    lookup = {}
    csv_path = _REPO_ROOT / "knowledge" / "plant_types.csv"
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("farmos_name") or "").strip()
            bot = (row.get("botanical_name") or "").strip()
            if name and bot:
                lookup[name] = bot
    return lookup


def find_stock_file(fc, botanical: str) -> dict | None:
    """Query farmOS file collection for a stock-pattern filename matching
    the genus (first word of botanical name)."""
    if not botanical:
        return None
    genus = botanical.split()[0]
    if len(genus) < 4:
        return None
    encoded = urllib.parse.quote(genus)
    url = (f"{fc.hostname}/api/file/file"
           f"?filter[filename][operator]=CONTAINS"
           f"&filter[filename][value]={encoded}"
           f"&page[limit]=50")
    resp = fc.session.get(url, timeout=30)
    if not resp.ok:
        return None
    files = resp.json().get("data", [])
    # Prefer stock-pattern filenames
    stock_candidates = [
        f for f in files
        if is_stock(f.get("attributes", {}).get("filename", ""))
    ]
    if not stock_candidates:
        return None
    # Pick earliest-created (oldest stock — likely the original reference)
    stock_candidates.sort(key=lambda f: f.get("attributes", {}).get("created", ""))
    return stock_candidates[0]


def get_plant_type_current_file(fc, uuid: str) -> dict | None:
    resp = fc.session.get(
        f"{fc.hostname}/api/taxonomy_term/plant_type/{uuid}",
        params={"include": "image"}, timeout=15,
    )
    if not resp.ok:
        return None
    data = resp.json()
    rels = ((data.get("data", {}).get("relationships", {}).get("image") or {}).get("data")) or []
    if isinstance(rels, dict):
        rels = [rels]
    if not rels:
        return None
    included = data.get("included", [])
    files = [f for f in included if f.get("type") == "file--file"]
    return files[0] if files else None


def patch_plant_type_image(fc, uuid: str, file_id: str, dry_run: bool) -> bool:
    if dry_run:
        return True
    resp = fc.session.patch(
        f"{fc.hostname}/api/taxonomy_term/plant_type/{uuid}/relationships/image",
        json={"data": [{"type": "file--file", "id": file_id}]},
        headers={"Content-Type": "application/vnd.api+json"},
    )
    return resp.ok


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    fc = FarmOSClient()
    fc.connect()

    botanical = load_botanical_lookup()

    # Enumerate all active plant_types
    print("Fetching plant_types...", file=sys.stderr)
    terms = paginate_all(
        fc.session, fc.hostname, "taxonomy_term/plant_type",
        filters={"status": "1"},
        sort="drupal_internal__tid",
    )
    print(f"  {len(terms)} active plant_types", file=sys.stderr)

    reverted = 0
    no_stock_available = 0
    skipped = 0

    for term in terms:
        name = term.get("attributes", {}).get("name", "")
        uuid = term["id"]
        current = get_plant_type_current_file(fc, uuid)
        if not current:
            continue
        fn = current.get("attributes", {}).get("filename", "")
        if not is_tier1_multi_plant(fn):
            continue

        # This species is at tier-1; find stock replacement
        bot = botanical.get(name, "")
        stock = find_stock_file(fc, bot) if bot else None
        if not stock:
            no_stock_available += 1
            print(f"  ? {name:<40}  tier-1 {fn[:50]} — NO STOCK FOUND for '{bot}'")
            continue

        stock_fn = stock.get("attributes", {}).get("filename", "")
        if patch_plant_type_image(fc, uuid, stock["id"], args.dry_run):
            reverted += 1
            print(f"  ✓ {name:<40}  tier-1 → stock {stock_fn[:50]}")
        else:
            print(f"  ✗ {name:<40}  patch failed")
            skipped += 1

    print()
    print("=" * 60)
    print("Summary" + (" (DRY-RUN)" if args.dry_run else ""))
    print("=" * 60)
    print(f"  Reverted to stock:          {reverted}")
    print(f"  No stock found (kept):      {no_stock_available}")
    print(f"  Patch failures:             {skipped}")


if __name__ == "__main__":
    raise SystemExit(main())
