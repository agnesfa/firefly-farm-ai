#!/usr/bin/env python3
"""
Sync plant types from CSV into farmOS taxonomy.

Reads the master plant types CSV and creates/updates taxonomy terms in farmOS
with syntropic agriculture metadata embedded in the description field.

Uses per-name API queries (filter[name]=X) for reliable existence checks.
This avoids the farmOS.py iterate() pagination bug that causes duplicates
with 200+ terms.

Features:
    - Dry-run mode (preview without changes)
    - Idempotent (safe to re-run — creates, updates, or skips as needed)
    - Self-healing (detects and removes duplicates automatically)
    - Embeds syntropic data in descriptions until farm_syntropic module (Phase 4)

Usage:
    python scripts/import_plants.py --dry-run
    python scripts/import_plants.py
    python scripts/import_plants.py --csv knowledge/plant_types.csv --dry-run
"""

import csv
import os
import sys
import argparse
from pathlib import Path

from dotenv import load_dotenv

try:
    from farmOS import farmOS
except ImportError:
    print("ERROR: farmOS library not installed!")
    print("Please install it with: pip install farmOS")
    sys.exit(1)


def get_farmos_config():
    """Load farmOS configuration from environment variables."""
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
        print(f"ERROR: Missing environment variables: {', '.join('FARMOS_' + k.upper() for k in missing)}")
        print("Create a .env file from .env.example and fill in your credentials.")
        sys.exit(1)

    return config


class PlantTypeImporter:
    """Imports plant types into farmOS from CSV."""

    def __init__(self, config: dict, dry_run: bool = False):
        self.config = config
        self.dry_run = dry_run
        self.client = None
        self.stats = {"created": 0, "updated": 0, "skipped": 0, "failed": 0}

    def connect(self) -> bool:
        """Authenticate with farmOS."""
        print(f"\nConnecting to {self.config['hostname']}...")
        try:
            self.client = farmOS(
                hostname=self.config["hostname"],
                client_id=self.config["client_id"],
                scope=self.config["scope"],
            )
            self.client.authorize(
                username=self.config["username"],
                password=self.config["password"],
            )
            print("✓ Successfully authenticated!")
            return True
        except Exception as e:
            print(f"✗ Authentication failed: {e}")
            return False

    def fetch_terms_by_name(self, name):
        """Fetch ALL terms with a specific name. Reliable — not affected by pagination limits.

        Uses filter[name]=X which always returns complete results, unlike iterate()
        or raw HTTP pagination which cap at ~250 terms.
        """
        import urllib.parse
        session = self.client.session
        encoded = urllib.parse.quote(name)
        url = f"/api/taxonomy_term/plant_type?filter[name]={encoded}&page[limit]=50"
        resp = session.http_request(url)
        if resp.status_code != 200:
            return []
        return resp.json().get("data", [])

    def read_csv(self, csv_path: str) -> list:
        """Read plant types from CSV file."""
        plants = []
        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                plants = list(reader)
            print(f"✓ Read {len(plants)} plant types from {csv_path}")
        except FileNotFoundError:
            print(f"✗ CSV file not found: {csv_path}")
        except Exception as e:
            print(f"✗ Error reading CSV: {e}")
        return plants

    def build_description(self, plant: dict) -> str:
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

    def sync_plant_type(self, plant: dict) -> bool:
        """Create or update a single plant type in farmOS.

        Uses per-name API query (reliable) to check existence, then:
        - Creates if missing
        - Updates description if exists but content differs
        - Skips if already up to date
        - Self-heals duplicates (keeps best, deletes rest)
        """
        name = plant.get("farmos_name", "").strip() or plant.get("common_name", "").strip()
        if not name:
            return False

        # Reliable existence check — always returns complete results
        existing = self.fetch_terms_by_name(name)

        description = self.build_description(plant)
        term_data = {
            "attributes": {
                "name": name,
                "description": {"value": description, "format": "default"},
            }
        }

        # Add standard farmOS numeric fields (NOT harvest_days — causes 422)
        for field in ("maturity_days", "transplant_days"):
            val = plant.get(field)
            if val:
                try:
                    int_val = int(val)
                    if int_val > 0:
                        term_data["attributes"][field] = int_val
                except ValueError:
                    pass

        if len(existing) == 0:
            # CREATE
            if self.dry_run:
                botanical = plant.get("botanical_name", "")
                print(f"  + Would create: {name}" + (f" ({botanical})" if botanical else ""))
                self.stats["created"] += 1
                return True
            try:
                self.client.term.send("plant_type", term_data)
                print(f"  + Created: {name}")
                self.stats["created"] += 1
                return True
            except Exception as e:
                print(f"  ! Failed to create {name}: {e}")
                self.stats["failed"] += 1
                return False

        elif len(existing) == 1:
            # Check if update needed (description changed)
            current_desc = existing[0].get("attributes", {}).get("description", {})
            current_value = current_desc.get("value", "") if isinstance(current_desc, dict) else ""
            if current_value.strip() == description.strip():
                self.stats["skipped"] += 1
                return True
            # UPDATE — include id to trigger PATCH
            term_data["id"] = existing[0]["id"]
            term_data["type"] = "taxonomy_term--plant_type"
            if self.dry_run:
                print(f"  ~ Would update: {name}")
                self.stats["updated"] += 1
                return True
            try:
                self.client.term.send("plant_type", term_data)
                print(f"  ~ Updated: {name}")
                self.stats["updated"] += 1
                return True
            except Exception as e:
                print(f"  ! Failed to update {name}: {e}")
                self.stats["failed"] += 1
                return False

        else:
            # DUPLICATES — self-heal: keep best, delete rest
            print(f"  ! {name}: {len(existing)} duplicates found, cleaning up")
            def score(t):
                desc = t.get("attributes", {}).get("description", {})
                desc_value = desc.get("value", "") if isinstance(desc, dict) else ""
                has_v7 = "Syntropic Agriculture Data" in desc_value
                return (has_v7, len(desc_value))
            sorted_terms = sorted(existing, key=score, reverse=True)
            for dup in sorted_terms[1:]:
                if not self.dry_run:
                    try:
                        self.client.term.delete("plant_type", dup["id"])
                    except Exception as e:
                        print(f"    ! Failed to delete duplicate: {e}")
            self.stats["skipped"] += 1
            return True

    def import_all(self, csv_path: str):
        """Main import process."""
        print(f"\n{'='*60}")
        print("FIREFLY CORNER FARM — Plant Type Importer")
        print(f"{'='*60}")

        if self.dry_run:
            print("\n🔍 DRY RUN MODE — No changes will be made\n")

        if not self.connect():
            return False

        plants = self.read_csv(csv_path)
        if not plants:
            return False

        print(f"\n{'='*60}")
        print(f"{'DRY RUN — ' if self.dry_run else ''}SYNCING {len(plants)} PLANT TYPES")
        print(f"{'='*60}\n")

        for i, plant in enumerate(plants, 1):
            name = plant.get("farmos_name", "") or plant.get("common_name", "Unknown")
            self.sync_plant_type(plant)

        print(f"\n{'='*60}")
        print("SYNC SUMMARY")
        print(f"{'='*60}")
        print(f"  Total in CSV:    {len(plants)}")
        print(f"  Created:         {self.stats['created']}")
        print(f"  Updated:         {self.stats['updated']}")
        print(f"  Unchanged:       {self.stats['skipped']}")
        print(f"  Failed:          {self.stats['failed']}")

        if self.dry_run:
            print(f"\n  ** DRY RUN — run without --dry-run to apply changes **")
        else:
            print(f"\n  Sync completed!")

        return True


def main():
    parser = argparse.ArgumentParser(
        description="Import plant types into farmOS for Firefly Corner Farm"
    )
    parser.add_argument(
        "--csv",
        default="knowledge/plant_types.csv",
        help="CSV file to import (default: knowledge/plant_types.csv)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview import without making changes",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"Error: CSV file not found: {csv_path}")
        sys.exit(1)

    config = get_farmos_config()
    importer = PlantTypeImporter(config, dry_run=args.dry_run)
    success = importer.import_all(str(csv_path))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
