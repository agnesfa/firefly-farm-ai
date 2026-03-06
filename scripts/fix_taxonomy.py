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
    """Fetch ALL plant_type terms using raw HTTP with explicit pagination."""
    all_terms = []
    seen_ids = set()

    # Use the client's session for auth, but do manual pagination
    session = client.session
    hostname = client.session.hostname
    url = "/api/taxonomy_term/plant_type?page[limit]=50"

    page = 0
    while url:
        page += 1
        resp = session.http_request(url)
        if resp.status_code != 200:
            print(f"  ERROR: HTTP {resp.status_code} fetching page {page}")
            break

        data = resp.json()
        terms = data.get("data", [])

        for term in terms:
            tid = term.get("id", "")
            if tid and tid not in seen_ids:
                seen_ids.add(tid)
                all_terms.append(term)

        # Get next page URL — strip hostname since http_request prepends it
        next_url = data.get("links", {}).get("next", {})
        if isinstance(next_url, dict):
            full_url = next_url.get("href", "")
        elif isinstance(next_url, str):
            full_url = next_url
        else:
            full_url = ""

        if full_url:
            # Strip hostname prefix if present
            if full_url.startswith(hostname):
                url = full_url[len(hostname):]
            else:
                url = full_url
        else:
            url = None

    return all_terms


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

    # Step 1: Fetch ALL terms with reliable pagination
    print("Fetching ALL plant_type terms (paginated)...")
    all_terms = fetch_all_terms(client)
    print(f"  Total terms (unique UUIDs): {len(all_terms)}")

    # Group by name
    by_name = defaultdict(list)
    for term in all_terms:
        name = term.get("attributes", {}).get("name", "")
        by_name[name.lower()].append(term)

    duplicates = {n: ts for n, ts in by_name.items() if len(ts) > 1}
    all_names = {term.get("attributes", {}).get("name", "") for term in all_terms}
    archived = sum(1 for n in all_names if n.startswith("[ARCHIVED]"))

    print(f"  Unique names: {len(by_name)}")
    print(f"  Active: {len(by_name) - archived}")
    print(f"  Archived: {archived}")
    print(f"  Duplicate groups: {len(duplicates)}")

    # Step 2: Load v7 plant data
    plant_data = {}
    with open(args.plants, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            farmos_name = row.get("farmos_name", "").strip()
            if farmos_name:
                plant_data[farmos_name] = row

    # Step 3: Delete duplicates
    deleted = 0
    delete_failed = 0
    if duplicates:
        print(f"\n{'='*60}")
        print(f"{'DRY RUN — ' if dry_run else ''}DELETING DUPLICATES ({len(duplicates)} groups)")
        print(f"{'='*60}\n")

        for name, terms in sorted(duplicates.items()):
            def score(t):
                desc = t.get("attributes", {}).get("description", {})
                desc_value = desc.get("value", "") if isinstance(desc, dict) else ""
                has_v7 = "Syntropic Agriculture Data" in desc_value
                return (has_v7, len(desc_value))

            terms_scored = sorted(terms, key=score, reverse=True)
            keep = terms_scored[0]
            to_delete = terms_scored[1:]
            keep_name = keep.get("attributes", {}).get("name", "")

            for dup in to_delete:
                dup_id = dup.get("id", "")
                if dry_run:
                    print(f"  Would delete duplicate: {keep_name} ({dup_id[:8]}...)")
                    deleted += 1
                    # Remove from by_name for accurate missing check later
                    by_name[name].remove(dup)
                else:
                    try:
                        client.term.delete("plant_type", dup_id)
                        print(f"  Deleted duplicate: {keep_name} ({dup_id[:8]}...)")
                        deleted += 1
                        by_name[name].remove(dup)
                    except Exception as e:
                        print(f"  FAILED: {keep_name} ({dup_id[:8]}...) — {e}")
                        delete_failed += 1

    # Step 4: Find and create missing v7 entries
    existing_lower = {n.lower() for n in all_names}
    # Remove names of deleted entries... actually just use by_name keys
    # since we cleaned it above
    remaining_names = set()
    for name_lower, terms in by_name.items():
        if terms:  # still has at least one entry
            for t in terms:
                remaining_names.add(t.get("attributes", {}).get("name", ""))

    missing = []
    for farmos_name in sorted(plant_data.keys()):
        if farmos_name not in remaining_names and farmos_name.lower() not in {n.lower() for n in remaining_names}:
            missing.append(farmos_name)

    created = 0
    create_failed = 0
    if missing:
        print(f"\n{'='*60}")
        print(f"{'DRY RUN — ' if dry_run else ''}CREATING MISSING ENTRIES ({len(missing)})")
        print(f"{'='*60}\n")

        for farmos_name in missing:
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
    print(f"  {'Would delete' if dry_run else 'Deleted'} duplicates: {deleted}")
    if delete_failed:
        print(f"  Delete failures: {delete_failed}")
    print(f"  {'Would create' if dry_run else 'Created'} missing: {created}")
    if create_failed:
        print(f"  Create failures: {create_failed}")

    expected_total = len(all_terms) - deleted + created
    print(f"  Expected total after fix: {expected_total}")

    if dry_run:
        print(f"\n  ** DRY RUN — run with --execute to apply fixes **")
    else:
        print(f"\n  Fix complete. Run again to verify.")


if __name__ == "__main__":
    main()
