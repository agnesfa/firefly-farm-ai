#!/usr/bin/env python3
"""
Fix farmOS plant_type taxonomy: delete duplicates AND recreate missing entries.

Uses raw HTTP pagination to reliably fetch ALL terms (works around farmOS.py
iterate() pagination issues with 200+ terms).

Usage:
    python scripts/fix_taxonomy.py --dry-run   # Preview (default)
    python scripts/fix_taxonomy.py --execute    # Apply fixes
"""

import csv
import json
import os
import sys
import argparse
from collections import defaultdict

from dotenv import load_dotenv

try:
    from farmOS import farmOS
except ImportError:
    print("ERROR: farmOS library not installed!")
    sys.exit(1)


def get_farmos_config():
    load_dotenv()
    config = {
        "hostname": os.getenv("FARMOS_URL"),
        "username": os.getenv("FARMOS_USERNAME"),
        "password": os.getenv("FARMOS_PASSWORD"),
        "client_id": os.getenv("FARMOS_CLIENT_ID", "farm"),
        "scope": os.getenv("FARMOS_SCOPE", "farm_manager"),
    }
    missing = [k for k in ("hostname", "username", "password") if not config[k]]
    if missing:
        print(f"ERROR: Missing: {', '.join('FARMOS_' + k.upper() for k in missing)}")
        sys.exit(1)
    return config


def fetch_all_terms(client):
    """Fetch ALL plant_type terms using raw HTTP with explicit pagination.

    NOTE: farmOS JSON:API pagination caps at ~250 entries (5 pages of 50).
    This is unreliable for complete enumeration. Use fetch_terms_by_name()
    for guaranteed complete results.

    Uses offset-based pagination via the shared _paginate helper —
    links.next is unreliable past ~250 results (arch decision #11).
    """
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parent))
    from _paginate import paginate_all
    return paginate_all(
        client.session, client.session.hostname,
        "taxonomy_term/plant_type",
        sort="drupal_internal__tid",
    )


def fetch_terms_by_name(client, name):
    """Fetch ALL terms with a specific name. Reliable — not affected by pagination limits."""
    import urllib.parse
    session = client.session
    encoded = urllib.parse.quote(name)
    url = f"/api/taxonomy_term/plant_type?filter[name]={encoded}&page[limit]=50"
    resp = session.http_request(url)
    if resp.status_code != 200:
        return []
    return resp.json().get("data", [])


def build_description(plant: dict) -> str:
    """Build rich description with syntropic data embedded."""
    parts = []
    if plant.get("description"):
        parts.append(plant["description"])
    metadata = []
    if plant.get("botanical_name"):
        metadata.append(f"**Botanical Name:** {plant['botanical_name']}")
    if plant.get("lifecycle_years") or plant.get("lifecycle"):
        lifecycle_val = plant.get("lifecycle_years") or plant.get("lifecycle")
        metadata.append(f"**Life Cycle:** {lifecycle_val} years")
    if plant.get("strata"):
        metadata.append(f"**Strata:** {plant['strata'].title()}")
    if plant.get("succession_stage"):
        metadata.append(f"**Succession Stage:** {plant['succession_stage'].title()}")
    if plant.get("plant_functions"):
        functions = plant["plant_functions"].replace("_", " ").replace(",", ", ")
        metadata.append(f"**Functions:** {functions.title()}")
    if plant.get("crop_family"):
        metadata.append(f"**Family:** {plant['crop_family']}")
    if plant.get("lifespan_years") or plant.get("lifespan"):
        lifespan_val = plant.get("lifespan_years") or plant.get("lifespan")
        metadata.append(f"**Lifespan:** {lifespan_val} years")
    if plant.get("source"):
        metadata.append(f"**Source:** {plant['source']}")
    if metadata:
        parts.append("\n\n---\n**Syntropic Agriculture Data:**\n" + "\n".join(metadata))
    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(description="Fix farmOS plant_type taxonomy")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--plants", default="knowledge/plant_types.csv")
    args = parser.parse_args()
    dry_run = not args.execute

    config = get_farmos_config()

    print(f"\nConnecting to {config['hostname']}...")
    client = farmOS(
        hostname=config["hostname"],
        client_id=config["client_id"],
        scope=config["scope"],
    )
    client.authorize(username=config["username"], password=config["password"])
    print("  Connected.\n")

    # Step 1: Load v7 plant data
    plant_data = {}
    with open(args.plants, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            farmos_name = row.get("farmos_name", "").strip()
            if farmos_name:
                plant_data[farmos_name] = row

    # Step 2: Query each v7 name individually (reliable — not affected by pagination caps)
    print(f"Querying {len(plant_data)} v7 plant names individually...")
    total_terms = 0
    total_dupes = 0
    duplicate_groups = {}  # name -> list of terms
    missing_names = []
    found_names = set()

    for farmos_name in sorted(plant_data.keys()):
        terms = fetch_terms_by_name(client, farmos_name)
        count = len(terms)
        total_terms += count

        if count == 0:
            missing_names.append(farmos_name)
        elif count == 1:
            found_names.add(farmos_name)
        else:
            found_names.add(farmos_name)
            duplicate_groups[farmos_name] = terms
            total_dupes += count - 1

    # Also check for [ARCHIVED] terms
    archived_terms = fetch_terms_by_name(client, "[ARCHIVED]")
    # That won't work with exact match, let's use pagination for archived
    archived_count = 0
    for term in fetch_all_terms(client):
        name = term.get("attributes", {}).get("name", "")
        if name.startswith("[ARCHIVED]"):
            archived_count += 1

    print(f"  Total v7 terms found: {total_terms}")
    print(f"  V7 names present: {len(found_names)}/{len(plant_data)}")
    print(f"  V7 names missing: {len(missing_names)}")
    print(f"  Duplicate groups: {len(duplicate_groups)}")
    print(f"  Extra entries to delete: {total_dupes}")
    print(f"  Archived terms: {archived_count}")

    # Step 3: Delete duplicates
    deleted = 0
    delete_failed = 0
    if duplicate_groups:
        print(f"\n{'='*60}")
        print(f"{'DRY RUN — ' if dry_run else ''}DELETING DUPLICATES ({len(duplicate_groups)} groups, {total_dupes} entries)")
        print(f"{'='*60}\n")

        for name, terms in sorted(duplicate_groups.items()):
            def score(t):
                desc = t.get("attributes", {}).get("description", {})
                desc_value = desc.get("value", "") if isinstance(desc, dict) else ""
                has_v7 = "Syntropic Agriculture Data" in desc_value
                return (has_v7, len(desc_value))

            terms_scored = sorted(terms, key=score, reverse=True)
            keep = terms_scored[0]
            to_delete = terms_scored[1:]

            print(f"  {name} ({len(terms)}x → keep 1, delete {len(to_delete)})")

            for dup in to_delete:
                dup_id = dup.get("id", "")
                if dry_run:
                    deleted += 1
                else:
                    try:
                        client.term.delete("plant_type", dup_id)
                        print(f"    Deleted {dup_id[:12]}...")
                        deleted += 1
                    except Exception as e:
                        print(f"    FAILED {dup_id[:12]}... — {e}")
                        delete_failed += 1

    # Step 4: Create missing v7 entries
    created = 0
    create_failed = 0
    if missing_names:
        print(f"\n{'='*60}")
        print(f"{'DRY RUN — ' if dry_run else ''}CREATING MISSING ENTRIES ({len(missing_names)})")
        print(f"{'='*60}\n")

        for farmos_name in missing_names:
            plant = plant_data[farmos_name]
            description = build_description(plant)
            term_data = {
                "attributes": {
                    "name": farmos_name,
                    "description": {"value": description, "format": "default"},
                }
            }
            for field in ("maturity_days", "transplant_days"):
                val = plant.get(field, "")
                if val:
                    try:
                        int_val = int(val)
                        if int_val > 0:
                            term_data["attributes"][field] = int_val
                    except ValueError:
                        pass

            botanical = plant.get("botanical_name", "")
            if dry_run:
                print(f"  Would create: {farmos_name}" + (f" ({botanical})" if botanical else ""))
                created += 1
            else:
                try:
                    client.term.send("plant_type", term_data)
                    print(f"  Created: {farmos_name}" + (f" ({botanical})" if botanical else ""))
                    created += 1
                except Exception as e:
                    print(f"  FAILED: {farmos_name} — {e}")
                    create_failed += 1

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"  V7 names checked:  {len(plant_data)}")
    print(f"  Already present:   {len(found_names)}")
    print(f"  {'Would delete' if dry_run else 'Deleted'} duplicates: {deleted}")
    if delete_failed:
        print(f"  Delete failures:   {delete_failed}")
    print(f"  {'Would create' if dry_run else 'Created'} missing:    {created}")
    if create_failed:
        print(f"  Create failures:   {create_failed}")

    expected = len(found_names) + created
    print(f"  Expected v7 terms after fix: {expected}")

    if dry_run:
        print(f"\n  ** DRY RUN — run with --execute to apply fixes **")
    else:
        print(f"\n  Fix complete. Run again to verify (should show 0 duplicates, 0 missing).")


if __name__ == "__main__":
    main()
