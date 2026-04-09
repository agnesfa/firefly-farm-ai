#!/usr/bin/env python3
"""
Update farmOS plant_type taxonomy terms with enriched data from v8 CSV.

Reads the master plant_types.csv (v8) and updates existing farmOS taxonomy terms
with enriched descriptions built by helpers.build_plant_type_description().

Uses the MCP server's farmos_client.py (raw HTTP with OAuth2) to avoid the
farmOS.py pydantic v1/v2 conflict. Must run in the mcp-server venv.

Features:
    - Dry-run mode (preview without changes)
    - Single-entry mode (--name filter)
    - Rename handling (--renames CSV maps old farmOS names to new CSV names)
    - Rate-limited API calls (0.3s between PATCH requests)
    - Idempotent (skips entries where description is already up to date)
    - Reports: updated, renamed, skipped (unchanged), skipped (not found), failed

Usage:
    # Preview all updates
    python scripts/update_farmos_taxonomy_v8.py --dry-run

    # Apply all updates
    python scripts/update_farmos_taxonomy_v8.py

    # Update a single entry
    python scripts/update_farmos_taxonomy_v8.py --name "Pigeon Pea"

    # With renames (CSV with columns: old_name,new_name)
    python scripts/update_farmos_taxonomy_v8.py --renames knowledge/v8_renames.csv

    # Verbose output
    python scripts/update_farmos_taxonomy_v8.py --dry-run --verbose
"""

import csv
import sys
import time
import argparse
from pathlib import Path

# Add the project root to sys.path so we can import from mcp-server
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "mcp-server"))

from farmos_client import FarmOSClient
from helpers import build_plant_type_description


def read_csv(csv_path: str) -> list[dict]:
    """Read plant types from CSV file. Returns list of row dicts."""
    with open(csv_path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_renames(renames_path: str) -> dict[str, str]:
    """Read rename mappings from CSV.

    Expected columns: old_name, new_name
    Returns dict mapping old_name -> new_name.
    """
    renames = {}
    with open(renames_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            old = row.get("old_name", "").strip()
            new = row.get("new_name", "").strip()
            if old and new:
                renames[old] = new
    return renames


def build_description_from_csv_row(row: dict) -> str:
    """Build a farmOS description from a CSV row using helpers.build_plant_type_description."""
    fields = {
        "description": row.get("description", ""),
        "botanical_name": row.get("botanical_name", ""),
        "lifecycle_years": row.get("lifecycle_years", ""),
        "strata": row.get("strata", ""),
        "succession_stage": row.get("succession_stage", ""),
        "plant_functions": row.get("plant_functions", ""),
        "crop_family": row.get("crop_family", ""),
        "lifespan_years": row.get("lifespan_years", ""),
        "source": row.get("source", ""),
    }
    return build_plant_type_description(fields)


def get_term_description_value(term: dict) -> str:
    """Extract description text from a farmOS taxonomy term."""
    desc = term.get("attributes", {}).get("description", {})
    if isinstance(desc, dict):
        return desc.get("value", "")
    return str(desc) if desc else ""


def normalize_description(desc: str) -> str:
    """Normalize a description for comparison purposes.

    Strips trailing whitespace per line and trailing newlines,
    so cosmetic formatting differences don't trigger unnecessary updates.
    """
    lines = [line.rstrip() for line in desc.split("\n")]
    return "\n".join(lines).strip()


class TaxonomyUpdater:
    """Updates farmOS plant_type taxonomy from v8 CSV."""

    def __init__(self, client: FarmOSClient, dry_run: bool = True,
                 verbose: bool = False, rate_limit: float = 0.3):
        self.client = client
        self.dry_run = dry_run
        self.verbose = verbose
        self.rate_limit = rate_limit
        self.stats = {
            "updated": 0,
            "renamed": 0,
            "skipped_unchanged": 0,
            "skipped_not_found": 0,
            "failed": 0,
        }

    def fetch_all_terms(self) -> dict[str, dict]:
        """Fetch all plant_type terms from farmOS. Returns name -> term dict."""
        print("Fetching all plant_type terms from farmOS...")
        terms = self.client.fetch_all_paginated("taxonomy_term/plant_type")
        by_name = {}
        for term in terms:
            name = term.get("attributes", {}).get("name", "")
            if name:
                by_name[name] = term
        print(f"  Found {len(by_name)} terms in farmOS.")
        return by_name

    def update_term(self, term: dict, new_name: str | None, new_description: str,
                    maturity_days: int | None, transplant_days: int | None) -> bool:
        """PATCH a single taxonomy term. Returns True on success."""
        uuid = term.get("id", "")
        current_name = term.get("attributes", {}).get("name", "")

        attributes = {
            "description": {"value": new_description, "format": "default"},
        }

        if new_name and new_name != current_name:
            attributes["name"] = new_name

        if maturity_days and maturity_days > 0:
            attributes["maturity_days"] = maturity_days
        if transplant_days and transplant_days > 0:
            attributes["transplant_days"] = transplant_days

        if self.dry_run:
            return True

        try:
            self.client.update_plant_type(uuid, attributes)
            time.sleep(self.rate_limit)
            return True
        except Exception as e:
            print(f"    ERROR: PATCH failed for '{current_name}': {e}")
            return False

    def process_entry(self, row: dict, terms_by_name: dict,
                      renames: dict[str, str]) -> None:
        """Process a single CSV row: find matching term, compare, update if needed."""
        farmos_name = row.get("farmos_name", "").strip()
        if not farmos_name:
            return

        # Determine which farmOS name to look up
        # Check if this entry is a rename target (new CSV name maps FROM an old farmOS name)
        old_name = None
        rename_new_name = None
        for old, new in renames.items():
            if new == farmos_name:
                old_name = old
                rename_new_name = farmos_name
                break

        # Look up the term: try current name first, then old name for renames
        term = terms_by_name.get(farmos_name)
        if term is None and old_name:
            term = terms_by_name.get(old_name)

        if term is None:
            if self.verbose:
                print(f"  SKIP (not found): {farmos_name}")
            self.stats["skipped_not_found"] += 1
            return

        current_name = term.get("attributes", {}).get("name", "")
        is_rename = (rename_new_name and current_name != rename_new_name)

        # Build new description
        new_description = build_description_from_csv_row(row)
        current_description = get_term_description_value(term)

        # Parse numeric fields
        maturity_days = None
        transplant_days = None
        for field, attr in [("maturity_days", "maturity_days"),
                            ("transplant_days", "transplant_days")]:
            val = row.get(field, "")
            if val:
                try:
                    int_val = int(val)
                    if int_val > 0:
                        if attr == "maturity_days":
                            maturity_days = int_val
                        else:
                            transplant_days = int_val
                except ValueError:
                    pass

        # Compare descriptions (normalized)
        desc_changed = (normalize_description(new_description)
                        != normalize_description(current_description))

        # Check numeric field changes
        current_attrs = term.get("attributes", {})
        maturity_changed = (maturity_days is not None
                            and current_attrs.get("maturity_days") != maturity_days)
        transplant_changed = (transplant_days is not None
                              and current_attrs.get("transplant_days") != transplant_days)

        if not desc_changed and not is_rename and not maturity_changed and not transplant_changed:
            if self.verbose:
                print(f"  SKIP (unchanged): {farmos_name}")
            self.stats["skipped_unchanged"] += 1
            return

        # Determine what to report
        if is_rename:
            action_label = f"RENAME '{current_name}' -> '{rename_new_name}'"
            if desc_changed:
                action_label += " + update description"
        elif desc_changed:
            action_label = f"UPDATE description: {farmos_name}"
        else:
            action_label = f"UPDATE fields: {farmos_name}"

        if self.dry_run:
            print(f"  Would {action_label}")
            if is_rename:
                self.stats["renamed"] += 1
            else:
                self.stats["updated"] += 1
            return

        # Apply the update
        target_name = rename_new_name if is_rename else None
        success = self.update_term(term, target_name, new_description,
                                   maturity_days, transplant_days)

        if success:
            print(f"  {action_label}")
            if is_rename:
                self.stats["renamed"] += 1
                # Update the lookup dict so subsequent lookups find the new name
                if current_name in terms_by_name:
                    terms_by_name[rename_new_name] = terms_by_name.pop(current_name)
            else:
                self.stats["updated"] += 1
        else:
            self.stats["failed"] += 1

    def run(self, csv_rows: list[dict], terms_by_name: dict,
            renames: dict[str, str], name_filter: str | None = None) -> None:
        """Process all CSV rows."""
        # Filter to single entry if --name provided
        if name_filter:
            csv_rows = [r for r in csv_rows if r.get("farmos_name", "").strip() == name_filter]
            if not csv_rows:
                print(f"\nNo CSV entry found matching --name '{name_filter}'")
                return

        print(f"\nProcessing {len(csv_rows)} CSV entries...")
        if renames:
            print(f"  ({len(renames)} rename mappings loaded)")
        print()

        for row in csv_rows:
            self.process_entry(row, terms_by_name, renames)

    def print_summary(self):
        """Print final summary."""
        total = sum(self.stats.values())
        print(f"\n{'='*60}")
        print("UPDATE SUMMARY")
        print(f"{'='*60}")
        print(f"  Updated:             {self.stats['updated']}")
        print(f"  Renamed:             {self.stats['renamed']}")
        print(f"  Skipped (unchanged): {self.stats['skipped_unchanged']}")
        print(f"  Skipped (not found): {self.stats['skipped_not_found']}")
        print(f"  Failed:              {self.stats['failed']}")
        print(f"  ─────────────────────────")
        print(f"  Total:               {total}")

        if self.dry_run:
            print(f"\n  ** DRY RUN -- no changes were made **")
        else:
            if self.stats["failed"] == 0:
                print(f"\n  Update completed successfully!")
            else:
                print(f"\n  Update completed with {self.stats['failed']} error(s).")
                print(f"  Re-run to retry failed operations (idempotent).")


def main():
    parser = argparse.ArgumentParser(
        description="Update farmOS plant_type taxonomy with enriched v8 CSV data"
    )
    parser.add_argument(
        "--csv",
        default="knowledge/plant_types.csv",
        help="Plant types CSV file (default: knowledge/plant_types.csv)",
    )
    parser.add_argument(
        "--renames",
        default=None,
        help="Optional CSV with old_name,new_name columns for rename handling",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without applying them",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Update only this specific farmos_name entry",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show skipped entries and additional detail",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"Error: CSV file not found: {csv_path}")
        sys.exit(1)

    # Load renames if provided
    renames = {}
    if args.renames:
        renames_path = Path(args.renames)
        if not renames_path.exists():
            print(f"Error: Renames file not found: {renames_path}")
            sys.exit(1)
        renames = read_renames(str(renames_path))
        print(f"Loaded {len(renames)} rename mappings from {renames_path}")

    # Read CSV
    csv_rows = read_csv(str(csv_path))
    print(f"Read {len(csv_rows)} plant types from {csv_path}")

    # Connect to farmOS
    print(f"\n{'='*60}")
    print("FIREFLY CORNER FARM")
    print("Plant Type Taxonomy Update (v8)")
    print(f"{'='*60}")

    if args.dry_run:
        print("\n  ** DRY RUN MODE -- No changes will be made **\n")

    client = FarmOSClient()
    try:
        client.connect()
        print(f"  Connected to {client.hostname}")
    except (ConnectionError, ValueError) as e:
        print(f"  Connection failed: {e}")
        sys.exit(1)

    # Fetch all existing terms
    updater = TaxonomyUpdater(
        client,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )
    terms_by_name = updater.fetch_all_terms()

    # Process
    updater.run(csv_rows, terms_by_name, renames, name_filter=args.name)
    updater.print_summary()

    sys.exit(0 if updater.stats["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
