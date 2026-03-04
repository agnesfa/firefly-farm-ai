#!/usr/bin/env python3
"""
Import plant types from CSV into farmOS taxonomy.

Reads the master plant types CSV and creates taxonomy terms in farmOS with
syntropic agriculture metadata embedded in the description field.

Credentials are loaded from .env file (see .env.example).

Features:
    - Dry-run mode (preview without changes)
    - Duplicate detection (case-insensitive)
    - Idempotent (safe to re-run)
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
        self.existing_plant_types = {}
        self.stats = {"created": 0, "skipped": 0, "failed": 0}

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

    def load_existing_plant_types(self):
        """Load existing plant types from farmOS to avoid duplicates."""
        print("\nLoading existing plant types...")
        try:
            response = self.client.term.iterate("plant_type")
            for term in response:
                name = term.get("attributes", {}).get("name", "").lower()
                self.existing_plant_types[name] = term
            print(f"✓ Found {len(self.existing_plant_types)} existing plant types")
        except Exception as e:
            print(f"⚠ Warning: Could not load existing plant types: {e}")

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
        if plant.get("lifecycle"):
            metadata.append(f"**Life Cycle:** {plant['lifecycle'].title()}")
        if plant.get("strata"):
            metadata.append(f"**Strata:** {plant['strata'].title()}")
        if plant.get("succession_stage"):
            metadata.append(f"**Succession Stage:** {plant['succession_stage'].title()}")
        if plant.get("plant_functions"):
            functions = plant["plant_functions"].replace("_", " ").replace(",", ", ")
            metadata.append(f"**Functions:** {functions.title()}")
        if plant.get("crop_family"):
            metadata.append(f"**Family:** {plant['crop_family']}")
        if plant.get("lifespan"):
            metadata.append(f"**Lifespan:** {plant['lifespan']} years")
        if plant.get("source"):
            metadata.append(f"**Source:** {plant['source']}")

        if metadata:
            parts.append("\n\n---\n**Syntropic Agriculture Data:**\n" + "\n".join(metadata))

        return "\n".join(parts)

    def create_plant_type(self, plant: dict) -> bool:
        """Create a single plant type in farmOS."""
        name = plant.get("common_name", "").strip()
        if not name:
            return False

        if name.lower() in self.existing_plant_types:
            print(f"  ⏭ Skipped (already exists): {name}")
            self.stats["skipped"] += 1
            return True

        term_data = {
            "attributes": {
                "name": name,
                "description": {
                    "value": self.build_description(plant),
                    "format": "default",
                },
            }
        }

        # Add standard farmOS numeric fields if present
        for field in ("maturity_days", "transplant_days", "harvest_days"):
            val = plant.get(field)
            if val:
                try:
                    term_data["attributes"][field] = int(val)
                except ValueError:
                    pass

        if self.dry_run:
            botanical = plant.get("botanical_name", "")
            print(f"  ➤ Would create: {name}" + (f" ({botanical})" if botanical else ""))
            self.stats["created"] += 1
            return True

        try:
            self.client.term.send("plant_type", term_data)
            botanical = plant.get("botanical_name", "")
            print(f"  ✓ Created: {name}" + (f" ({botanical})" if botanical else ""))
            self.stats["created"] += 1
            return True
        except Exception as e:
            print(f"  ✗ Failed to create {name}: {e}")
            self.stats["failed"] += 1
            return False

    def import_all(self, csv_path: str):
        """Main import process."""
        print(f"\n{'='*60}")
        print("FIREFLY CORNER FARM — Plant Type Importer")
        print(f"{'='*60}")

        if self.dry_run:
            print("\n🔍 DRY RUN MODE — No changes will be made\n")

        if not self.connect():
            return False

        self.load_existing_plant_types()

        plants = self.read_csv(csv_path)
        if not plants:
            return False

        print(f"\n{'='*60}")
        print(f"IMPORTING {len(plants)} PLANT TYPES")
        print(f"{'='*60}\n")

        for i, plant in enumerate(plants, 1):
            name = plant.get("common_name", "Unknown")
            print(f"[{i}/{len(plants)}] {name}")
            self.create_plant_type(plant)

        print(f"\n{'='*60}")
        print("IMPORT SUMMARY")
        print(f"{'='*60}")
        print(f"  Total in CSV:    {len(plants)}")
        print(f"  Created:         {self.stats['created']}")
        print(f"  Skipped:         {self.stats['skipped']}")
        print(f"  Failed:          {self.stats['failed']}")

        if self.dry_run:
            print(f"\n🔍 This was a DRY RUN — no changes were made")
            print(f"   Run without --dry-run to actually import")
        else:
            print(f"\n✓ Import completed!")

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
