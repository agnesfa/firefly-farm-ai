#!/usr/bin/env python3
"""
Import field sheet data into farmOS as Plant assets + Observation logs.

Reads sections.json and creates for each species with count > 0 per section:
1. Plant asset — named "{planted_date} - {farmos_name} - {section_id}"
2. Quantity entity — inventory count (measure=count, adjustment=reset)
3. Observation log — sets plant location (is_movement=true) and links quantity

Uses per-name API queries for reliable existence checks (avoids pagination bugs).

Features:
    - Dry-run mode (preview without changes)
    - Row filter (--row P2R1 to import specific row only)
    - Idempotent (checks for existing plant assets before creating)
    - Pre-validates all plant types and sections before creating anything

Usage:
    python scripts/import_fieldsheets.py --dry-run
    python scripts/import_fieldsheets.py
    python scripts/import_fieldsheets.py --row P2R1 --dry-run
"""

import argparse
import json
import os
import sys
import urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path

from dotenv import load_dotenv

try:
    from farmOS import farmOS
except ImportError:
    print("ERROR: farmOS library not installed!")
    print("Please install it with: pip install farmOS")
    sys.exit(1)


PLANT_UNIT_UUID = "2371b79e-a87b-4152-b6e4-ea6a9ed37fd0"
AEST = timezone(timedelta(hours=10))


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


class FieldSheetImporter:
    """Imports field sheet data into farmOS as Plant assets + Observation logs."""

    def __init__(self, config: dict, dry_run: bool = False):
        self.config = config
        self.dry_run = dry_run
        self.client = None
        self.plant_type_cache = {}  # farmos_name → UUID
        self.section_cache = {}     # section_id → UUID
        self.stats = {
            "plants_created": 0,
            "plants_skipped": 0,
            "logs_created": 0,
            "failed": 0,
        }

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
            print("Connected successfully.")
            return True
        except Exception as e:
            print(f"Authentication failed: {e}")
            return False

    # ── API helpers ──────────────────────────────────────────────

    def fetch_by_name(self, api_path, name):
        """Per-name API query — reliable, not affected by pagination limits."""
        session = self.client.session
        encoded = urllib.parse.quote(name)
        url = f"/api/{api_path}?filter[name]={encoded}&page[limit]=50"
        resp = session.http_request(url)
        if resp.status_code != 200:
            return []
        return resp.json().get("data", [])

    def get_plant_type_uuid(self, farmos_name):
        """Get plant_type taxonomy term UUID by name (cached)."""
        if farmos_name in self.plant_type_cache:
            return self.plant_type_cache[farmos_name]
        terms = self.fetch_by_name("taxonomy_term/plant_type", farmos_name)
        if terms:
            uuid = terms[0]["id"]
            self.plant_type_cache[farmos_name] = uuid
            return uuid
        return None

    def get_section_uuid(self, section_id):
        """Get section land asset UUID by name (cached)."""
        if section_id in self.section_cache:
            return self.section_cache[section_id]
        assets = self.fetch_by_name("asset/land", section_id)
        if assets:
            uuid = assets[0]["id"]
            self.section_cache[section_id] = uuid
            return uuid
        return None

    def plant_asset_exists(self, asset_name):
        """Check if a plant asset with this name already exists. Returns UUID or None."""
        assets = self.fetch_by_name("asset/plant", asset_name)
        return assets[0]["id"] if assets else None

    # ── Entity creation ─────────────────────────────────────────

    def create_plant_asset(self, name, plant_type_uuid, notes=""):
        """Create a Plant asset in farmOS. Location is set via movement log."""
        data = {
            "attributes": {
                "name": name,
                "status": "active",
            },
            "relationships": {
                "plant_type": {
                    "data": [{"type": "taxonomy_term--plant_type", "id": plant_type_uuid}]
                },
            },
        }
        if notes:
            data["attributes"]["notes"] = {"value": notes, "format": "default"}

        try:
            result = self.client.asset.send("plant", data)
            return result.get("data", {}).get("id")
        except Exception as e:
            print(f"    ! Failed to create plant asset: {e}")
            return None

    def create_quantity(self, plant_id, count):
        """Create a quantity entity for inventory count tracking via raw HTTP."""
        payload = {
            "data": {
                "type": "quantity--standard",
                "attributes": {
                    "value": {"decimal": str(count)},
                    "measure": "count",
                    "label": "plants",
                    "inventory_adjustment": "reset",
                },
                "relationships": {
                    "units": {
                        "data": {
                            "type": "taxonomy_term--unit",
                            "id": PLANT_UNIT_UUID,
                        }
                    },
                    "inventory_asset": {
                        "data": {
                            "type": "asset--plant",
                            "id": plant_id,
                        }
                    },
                },
            }
        }
        try:
            session = self.client.session
            resp = session.http_request(
                "/api/quantity/standard",
                method="POST",
                options={"json": payload},
            )
            return resp.json().get("data", {}).get("id")
        except Exception as e:
            print(f"    ! Failed to create quantity: {e}")
            return None

    def create_observation_log(self, plant_id, section_uuid, quantity_id,
                               inventory_date, section_id, farmos_name):
        """Create observation log to set plant location and inventory count."""
        timestamp = self.parse_date(inventory_date)
        log_name = f"Inventory {section_id} — {farmos_name}"

        log_data = {
            "attributes": {
                "name": log_name,
                "timestamp": str(timestamp),
                "status": "done",
                "is_movement": True,
            },
            "relationships": {
                "asset": {
                    "data": [{"type": "asset--plant", "id": plant_id}]
                },
                "location": {
                    "data": [{"type": "asset--land", "id": section_uuid}]
                },
            },
        }
        if quantity_id:
            log_data["relationships"]["quantity"] = {
                "data": [{"type": "quantity--standard", "id": quantity_id}]
            }

        try:
            result = self.client.log.send("observation", log_data)
            return result.get("data", {}).get("id")
        except Exception as e:
            print(f"    ! Failed to create observation log: {e}")
            return None

    # ── Date parsing ────────────────────────────────────────────

    def format_planted_label(self, date_str):
        """Format first_planted date for plant asset name. E.g., '2025-04-25' → '25 APR 2025'."""
        if not date_str:
            return "SPRING 2025"

        # ISO format: 2025-04-25
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            return dt.strftime("%-d %b %Y").upper()  # "25 APR 2025"
        except ValueError:
            pass

        # Text format: "April 2025"
        try:
            dt = datetime.strptime(date_str, "%B %Y")
            return dt.strftime("%b %Y").upper()  # "APR 2025"
        except ValueError:
            pass

        return date_str.upper()

    def parse_date(self, date_str):
        """Parse date string to Unix timestamp (farmOS format)."""
        if not date_str:
            return int(datetime(2025, 4, 1, tzinfo=AEST).timestamp())

        # ISO format: 2025-10-09
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=AEST)
            return int(dt.timestamp())
        except ValueError:
            pass

        # "2025-MARCH-20 to 24TH" format
        try:
            parts = date_str.upper().replace(",", "").split("-")
            if len(parts) >= 2:
                year = int(parts[0].strip())
                month_names = {
                    "JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "APRIL": 4,
                    "MAY": 5, "JUNE": 6, "JULY": 7, "AUGUST": 8,
                    "SEPTEMBER": 9, "OCTOBER": 10, "NOVEMBER": 11, "DECEMBER": 12,
                }
                month_str = parts[1].strip()
                if month_str in month_names:
                    day = 1
                    if len(parts) >= 3:
                        day_str = parts[2].strip().split()[0]
                        try:
                            day = int("".join(c for c in day_str if c.isdigit()))
                        except ValueError:
                            day = 1
                    dt = datetime(year, month_names[month_str], max(1, day), tzinfo=AEST)
                    return int(dt.timestamp())
        except (ValueError, IndexError):
            pass

        # Fallback: spring 2025
        return int(datetime(2025, 4, 1, tzinfo=AEST).timestamp())

    # ── Main import ─────────────────────────────────────────────

    def import_all(self, sections_path, row_filter=None):
        """Main import process."""
        print(f"\n{'='*60}")
        print("FIREFLY CORNER FARM — Field Sheet Importer")
        print(f"{'='*60}")

        if self.dry_run:
            print("\nDRY RUN — No changes will be made\n")

        # Load sections data
        with open(sections_path) as f:
            data = json.load(f)

        sections = data.get("sections", {})

        # Filter by row if requested
        if row_filter:
            sections = {k: v for k, v in sections.items() if k.startswith(row_filter)}
            print(f"Filtered to {len(sections)} sections matching {row_filter}")

        # Count plants to import
        total_plants = 0
        all_species = set()
        for section in sections.values():
            for plant in section.get("plants", []):
                if (plant.get("count") or 0) > 0:
                    total_plants += 1
                    all_species.add(plant["species"])

        print(f"Processing {len(sections)} sections, {total_plants} plant entries "
              f"({len(all_species)} unique species)\n")

        if not self.dry_run:
            if not self.connect():
                return False

            # Pre-validate all plant types exist in farmOS
            print(f"Validating {len(all_species)} plant types...")
            missing_types = []
            for species in sorted(all_species):
                uuid = self.get_plant_type_uuid(species)
                if not uuid:
                    missing_types.append(species)

            if missing_types:
                print(f"\n! {len(missing_types)} plant types not found in farmOS:")
                for name in missing_types:
                    print(f"    - {name}")
                print("\nCreate these plant types first (import_plants.py), then re-run.")
                return False
            print(f"  All {len(all_species)} plant types verified.")

            # Pre-validate all sections exist in farmOS
            print(f"Validating {len(sections)} sections...")
            missing_sections = []
            for section_id in sorted(sections.keys()):
                uuid = self.get_section_uuid(section_id)
                if not uuid:
                    missing_sections.append(section_id)

            if missing_sections:
                print(f"\n! {len(missing_sections)} sections not found in farmOS:")
                for sid in missing_sections:
                    print(f"    - {sid}")
                print("\nCreate these land assets in farmOS first, then re-run.")
                return False
            print(f"  All {len(sections)} sections verified.\n")

        # Process each section
        for section_id in sorted(sections.keys()):
            section = sections[section_id]
            inventory_date = section.get("inventory_date", "")
            plants = section.get("plants", [])

            # Only plants with count > 0
            active_plants = [p for p in plants if (p.get("count") or 0) > 0]

            if not active_plants:
                continue

            first_planted = section.get("first_planted", "")
            planted_label = self.format_planted_label(first_planted)
            print(f"  {section_id}: {len(active_plants)} species ({inventory_date})")
            section_uuid = self.section_cache.get(section_id)

            for plant in active_plants:
                species = plant["species"]
                count = plant["count"]
                notes = plant.get("notes", "")
                asset_name = f"{planted_label} - {species} - {section_id}"

                if self.dry_run:
                    print(f"    + {asset_name} (count: {count})")
                    self.stats["plants_created"] += 1
                    self.stats["logs_created"] += 1
                    continue

                # Idempotent: skip if plant already exists
                existing_id = self.plant_asset_exists(asset_name)
                if existing_id:
                    print(f"    = {asset_name} (exists)")
                    self.stats["plants_skipped"] += 1
                    continue

                plant_type_uuid = self.get_plant_type_uuid(species)

                # 1. Create plant asset
                plant_id = self.create_plant_asset(asset_name, plant_type_uuid, notes)
                if not plant_id:
                    self.stats["failed"] += 1
                    continue
                self.stats["plants_created"] += 1

                # 2. Create quantity (inventory count)
                quantity_id = self.create_quantity(plant_id, count)

                # 3. Create observation log (movement + inventory)
                log_id = self.create_observation_log(
                    plant_id, section_uuid, quantity_id,
                    inventory_date, section_id, species
                )
                if log_id:
                    print(f"    + {asset_name} (count: {count})")
                    self.stats["logs_created"] += 1
                else:
                    print(f"    ~ {asset_name} (plant OK, log failed)")
                    self.stats["failed"] += 1

        # Summary
        print(f"\n{'='*60}")
        print("IMPORT SUMMARY")
        print(f"{'='*60}")
        print(f"  Plants created:  {self.stats['plants_created']}")
        print(f"  Plants skipped:  {self.stats['plants_skipped']}")
        print(f"  Logs created:    {self.stats['logs_created']}")
        print(f"  Failed:          {self.stats['failed']}")

        if self.dry_run:
            print(f"\n  ** DRY RUN — run without --dry-run to apply changes **")
        else:
            print(f"\n  Import completed!")

        return True


def main():
    parser = argparse.ArgumentParser(
        description="Import field sheet data into farmOS"
    )
    parser.add_argument(
        "--data", default="site/src/data/sections.json",
        help="Path to sections.json (default: site/src/data/sections.json)",
    )
    parser.add_argument(
        "--row", default=None,
        help="Filter to specific row (e.g., P2R1, P2R2, P2R3)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview import without making changes",
    )
    args = parser.parse_args()

    data_path = Path(args.data)
    if not data_path.exists():
        print(f"Error: Data file not found: {data_path}")
        sys.exit(1)

    config = get_farmos_config()
    importer = FieldSheetImporter(config, dry_run=args.dry_run)
    success = importer.import_all(str(data_path), row_filter=args.row)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
