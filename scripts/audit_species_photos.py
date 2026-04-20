#!/usr/bin/env python3
"""
Audit species reference photos in farmOS against PlantNet.

Scans every plant_type taxonomy term that has a reference photo,
downloads the photo, runs it through PlantNet, and reports whether
the photo matches the claimed species.

Usage:
    # Dry-run report (no changes):
    python scripts/audit_species_photos.py

    # Remove wrong photos after review:
    python scripts/audit_species_photos.py --fix

    # Limit API calls (default: no limit, but there are only ~31):
    python scripts/audit_species_photos.py --limit 10
"""

import argparse
import os
import sys

# Add mcp-server to path for plantnet_verify
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "mcp-server"))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

from farmos_client import FarmOSClient
from plantnet_verify import (
    build_botanical_lookup,
    verify_species_photo,
    get_call_count,
    CONFIDENCE_THRESHOLD,
)


def main():
    parser = argparse.ArgumentParser(description="Audit species reference photos against PlantNet")
    parser.add_argument("--fix", action="store_true", help="Remove wrong photos from farmOS (requires review first)")
    parser.add_argument("--limit", type=int, default=0, help="Max PlantNet API calls (0 = no limit)")
    args = parser.parse_args()

    # Connect to farmOS
    farmos = FarmOSClient()
    if not farmos.connect():
        print("ERROR: Failed to connect to farmOS", file=sys.stderr)
        return 1

    # Build botanical lookup
    lookup = build_botanical_lookup()
    reverse = lookup.get("__reverse__", {})
    print(f"Loaded {len(reverse)} species with botanical names")

    # Fetch all plant_type terms with images via offset-based pagination
    # (shared _paginate helper — avoids farmOS links.next 250-item bug).
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parent))
    from _paginate import paginate_offset

    print("Fetching plant_type taxonomy with images...")
    terms_with_photos = []
    for term, included in paginate_offset(
        farmos.session, farmos.hostname, "taxonomy_term/plant_type",
        filters={"status": "1"},
        sort="drupal_internal__tid",
        include="image",
    ):
        attrs = term.get("attributes") or {}
        name = attrs.get("name", "")
        term_id = term.get("id", "")
        image_rel = (term.get("relationships") or {}).get("image") or {}
        rel_data = image_rel.get("data")
        if isinstance(rel_data, list) and rel_data:
            file_id = rel_data[-1].get("id", "")
        elif isinstance(rel_data, dict):
            file_id = rel_data.get("id", "")
        else:
            file_id = ""
        if not (file_id and name):
            continue
        file_rec = included.get(("file--file", file_id))
        if not file_rec:
            continue
        uri = (file_rec.get("attributes") or {}).get("uri") or {}
        url = uri.get("url") if isinstance(uri, dict) else ""
        if url and url.startswith("/"):
            url = farmos.hostname.rstrip("/") + url
        if not url:
            continue
        terms_with_photos.append({
            "name": name,
            "term_id": term_id,
            "file_id": file_id,
            "photo_url": url,
        })

    print(f"Found {len(terms_with_photos)} species with reference photos\n")

    if not terms_with_photos:
        print("Nothing to audit.")
        return 0

    # Audit each photo
    correct = []
    wrong = []
    unverifiable = []
    api_errors = []

    for i, term in enumerate(terms_with_photos):
        if args.limit and get_call_count() >= args.limit:
            print(f"\n  ⚠ Reached API call limit ({args.limit}). Stopping.")
            break

        name = term["name"]
        expected = reverse.get(name, "")

        if not expected:
            unverifiable.append(term)
            print(f"  [{i+1}/{len(terms_with_photos)}] {name}: no botanical name → skip")
            continue

        # Download photo
        try:
            resp = farmos.session.get(term["photo_url"], timeout=30)
            resp.raise_for_status()
            photo_bytes = resp.content
        except Exception as e:
            api_errors.append({**term, "error": str(e)})
            print(f"  [{i+1}/{len(terms_with_photos)}] {name}: download failed — {e}")
            continue

        # Verify against PlantNet
        result = verify_species_photo(photo_bytes, name, lookup)

        if result["verified"]:
            correct.append({**term, **result})
            print(f"  [{i+1}/{len(terms_with_photos)}] ✓ {name}: {result['reason']}")
        elif result["reason"].startswith("api_"):
            api_errors.append({**term, **result})
            print(f"  [{i+1}/{len(terms_with_photos)}] ? {name}: {result['reason']}")
        else:
            wrong.append({**term, **result})
            print(f"  [{i+1}/{len(terms_with_photos)}] ✗ {name}: {result['reason']}")

    # Summary
    print(f"\n{'='*60}")
    print(f"AUDIT RESULTS")
    print(f"{'='*60}")
    print(f"  Correct:      {len(correct)}")
    print(f"  WRONG:        {len(wrong)}")
    print(f"  Unverifiable: {len(unverifiable)} (no botanical name)")
    print(f"  API errors:   {len(api_errors)}")
    print(f"  PlantNet calls: {get_call_count()}")

    if wrong:
        print(f"\n{'─'*60}")
        print("WRONG PHOTOS (need removal):")
        for w in wrong:
            print(f"  ✗ {w['name']}")
            print(f"    PlantNet says: {w.get('plantnet_top', '?')} ({w.get('confidence', 0):.0%})")
            print(f"    Expected: {reverse.get(w['name'], '?')}")
            print(f"    Term ID: {w['term_id']}")

    if args.fix and wrong:
        print(f"\n{'─'*60}")
        print(f"FIXING: Removing {len(wrong)} wrong reference photos...")
        removed = 0
        for w in wrong:
            try:
                # PATCH the taxonomy term to remove the image relationship
                patch_url = f"/api/taxonomy_term/plant_type/{w['term_id']}"
                patch_data = {
                    "data": {
                        "type": "taxonomy_term--plant_type",
                        "id": w["term_id"],
                        "relationships": {
                            "image": {"data": []}
                        }
                    }
                }
                farmos._patch(patch_url, patch_data)
                removed += 1
                print(f"  ✓ Removed photo from {w['name']}")
            except Exception as e:
                print(f"  ✗ Failed to remove photo from {w['name']}: {e}")
        print(f"\nRemoved {removed}/{len(wrong)} wrong photos.")
    elif wrong and not args.fix:
        print(f"\nTo remove wrong photos, run: python scripts/audit_species_photos.py --fix")

    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
