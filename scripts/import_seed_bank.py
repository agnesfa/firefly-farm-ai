#!/usr/bin/env python3
"""
Import seed bank inventory into farmOS as Seed assets + Observation logs.

Reads knowledge/seed_bank.csv and creates for each entry with seed data:
1. Seed asset — named "{farmos_name} Seeds — {source}" (or "{farmos_name} Seeds" if single source)
2. Quantity entity — inventory (grams for bulk, stock_level 0/0.5/1 for sachets)
3. Observation log — sets inventory count (inventory_adjustment=reset)

All Seed assets are linked to the "Seed Bank" group asset and the
corresponding plant_type taxonomy term.

Features:
    - Dry-run mode (preview without changes)
    - Idempotent (checks for existing seed assets before creating)
    - Pre-validates all plant types exist in farmOS
    - Handles European decimals (0,5 → 0.5)
    - Separate unit types: grams (bulk) vs stock level (sachets)

Usage:
    python scripts/import_seed_bank.py --dry-run
    python scripts/import_seed_bank.py
    python scripts/import_seed_bank.py --filter pigeon
"""

import argparse
import csv
import os
import sys
import urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path

from dotenv import load_dotenv
import requests

# farmOS UUIDs
SEED_BANK_GROUP_UUID = "78540b12-37b9-4c07-b94d-db00ca91b635"
NURS_FRDG_UUID = "429fcdd3-8be6-436a-b439-49186f56b3c7"
UNIT_GRAMS_UUID = "e7bad672-9c33-4138-9fc3-1b0548a33aca"
UNIT_STOCK_LEVEL_UUID = "51960965-dc18-4e52-8ef9-702afd1fb603"
AEST = timezone(timedelta(hours=10))


def get_config():
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    config = {
        "url": os.getenv("FARMOS_URL"),
        "username": os.getenv("FARMOS_USERNAME"),
        "password": os.getenv("FARMOS_PASSWORD"),
    }
    missing = [k for k, v in config.items() if not v]
    if missing:
        print(f"ERROR: Missing env vars: {', '.join('FARMOS_' + k.upper() for k in missing)}")
        sys.exit(1)
    return config


class SeedBankImporter:
    def __init__(self, config, dry_run=False):
        self.config = config
        self.dry_run = dry_run
        self.session = None
        self.plant_type_cache = {}  # farmos_name → UUID
        self.stats = {
            "assets_created": 0,
            "assets_skipped": 0,
            "logs_created": 0,
            "failed": 0,
        }

    def connect(self):
        self.session = requests.Session()
        resp = self.session.post(f"{self.config['url']}/oauth/token", data={
            "grant_type": "password",
            "username": self.config["username"],
            "password": self.config["password"],
            "client_id": "farm",
            "scope": "farm_manager",
        })
        if resp.status_code != 200:
            print(f"Auth failed: {resp.status_code}")
            return False
        token = resp.json()["access_token"]
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/vnd.api+json",
        })
        print("Connected to farmOS.")
        return True

    # ── API helpers ──────────────────────────────────────────────

    def fetch_by_name(self, api_path, name):
        encoded = urllib.parse.quote(name)
        url = f"{self.config['url']}/api/{api_path}?filter[name]={encoded}&page[limit]=50"
        resp = self.session.get(url)
        if resp.status_code != 200:
            return []
        return resp.json().get("data", [])

    def get_plant_type_uuid(self, farmos_name):
        if farmos_name in self.plant_type_cache:
            return self.plant_type_cache[farmos_name]
        terms = self.fetch_by_name("taxonomy_term/plant_type", farmos_name)
        for t in terms:
            if t["attributes"]["name"] == farmos_name:
                uuid = t["id"]
                self.plant_type_cache[farmos_name] = uuid
                return uuid
        return None

    def seed_asset_exists(self, asset_name):
        assets = self.fetch_by_name("asset/seed", asset_name)
        for a in assets:
            if a["attributes"]["name"] == asset_name:
                return a["id"]
        return None

    # ── Entity creation ─────────────────────────────────────────

    def create_seed_asset(self, name, plant_type_uuid, notes=""):
        data = {
            "data": {
                "type": "asset--seed",
                "attributes": {
                    "name": name,
                    "status": "active",
                },
                "relationships": {
                    "plant_type": {
                        "data": [{"type": "taxonomy_term--plant_type", "id": plant_type_uuid}]
                    },
                    "parent": {
                        "data": [{"type": "asset--group", "id": SEED_BANK_GROUP_UUID}]
                    },
                },
            }
        }
        if notes:
            data["data"]["attributes"]["notes"] = {"value": notes, "format": "default"}

        try:
            resp = self.session.post(f"{self.config['url']}/api/asset/seed", json=data)
            if resp.status_code in (200, 201):
                return resp.json().get("data", {}).get("id")
            else:
                print(f"    ! Create seed failed: {resp.status_code} {resp.text[:150]}")
                return None
        except Exception as e:
            print(f"    ! Create seed failed: {e}")
            return None

    def create_quantity(self, seed_id, value, unit_uuid, measure, label):
        payload = {
            "data": {
                "type": "quantity--standard",
                "attributes": {
                    "value": {"decimal": str(value)},
                    "measure": measure,
                    "label": label,
                    "inventory_adjustment": "reset",
                },
                "relationships": {
                    "units": {
                        "data": {"type": "taxonomy_term--unit", "id": unit_uuid}
                    },
                    "inventory_asset": {
                        "data": {"type": "asset--seed", "id": seed_id}
                    },
                },
            }
        }
        try:
            resp = self.session.post(f"{self.config['url']}/api/quantity/standard", json=payload)
            if resp.status_code in (200, 201):
                return resp.json().get("data", {}).get("id")
            else:
                print(f"    ! Create quantity failed: {resp.status_code} {resp.text[:150]}")
                return None
        except Exception as e:
            print(f"    ! Create quantity failed: {e}")
            return None

    def create_observation_log(self, seed_id, quantity_id, log_name):
        now = int(datetime.now(tz=AEST).timestamp())
        log_data = {
            "data": {
                "type": "log--observation",
                "attributes": {
                    "name": log_name,
                    "timestamp": str(now),
                    "status": "done",
                    "is_movement": True,
                },
                "relationships": {
                    "asset": {
                        "data": [{"type": "asset--seed", "id": seed_id}]
                    },
                    "location": {
                        "data": [{"type": "asset--structure", "id": NURS_FRDG_UUID}]
                    },
                },
            }
        }
        if quantity_id:
            log_data["data"]["relationships"]["quantity"] = {
                "data": [{"type": "quantity--standard", "id": quantity_id}]
            }
        try:
            resp = self.session.post(f"{self.config['url']}/api/log/observation", json=log_data)
            if resp.status_code in (200, 201):
                return resp.json().get("data", {}).get("id")
            else:
                print(f"    ! Create log failed: {resp.status_code} {resp.text[:150]}")
                return None
        except Exception as e:
            print(f"    ! Create log failed: {e}")
            return None

    # ── Quantity parsing ────────────────────────────────────────

    def parse_european_decimal(self, value_str):
        """Parse European decimal format: '0,5' → 0.5"""
        if not value_str:
            return None
        cleaned = value_str.strip().replace(",", ".")
        try:
            return float(cleaned)
        except ValueError:
            return None

    # ── Asset naming ────────────────────────────────────────────

    def build_asset_name(self, farmos_name, source, is_multi_source):
        """Build seed asset name. Multi-source gets source suffix."""
        if is_multi_source and source:
            # Shorten common source prefixes
            short_source = source
            for prefix in ["Greenpatch Organic Seeds", "Mr Fothergill's",
                           "Daleys Fruit Nursery", "FFC (farm saved)",
                           "EDEN SEEDS", "Supermarket SEEDS/STONES"]:
                if source.startswith(prefix):
                    short_source = prefix.split("(")[0].strip().split(" Seeds")[0].strip()
                    if "(farm saved)" in source:
                        short_source = "FFC"
                    elif "(bought plant)" in source:
                        short_source = source.split("(")[0].strip()
                    break
            return f"{farmos_name} Seeds — {short_source}"
        return f"{farmos_name} Seeds"

    def build_notes(self, entry):
        """Build notes from seed bank entry metadata."""
        parts = []
        if entry.get("expiry_date"):
            parts.append(f"Expiry: {entry['expiry_date']}")
        if entry.get("quality"):
            q = "Good" if entry["quality"] == "G" else "Bad/expired" if entry["quality"] == "B" else entry["quality"]
            parts.append(f"Quality: {q}")
        if entry.get("dominant_function"):
            parts.append(f"Function: {entry['dominant_function']}")
        if entry.get("season_to_plant"):
            parts.append(f"Season: {entry['season_to_plant']}")
        if entry.get("qty_seeds_per_m2"):
            parts.append(f"Seeding rate: {entry['qty_seeds_per_m2']} g/m²")
        if entry.get("source"):
            parts.append(f"Source: {entry['source']}")
        return "\n".join(parts)

    # ── Main import ─────────────────────────────────────────────

    def import_all(self, csv_path, name_filter=None):
        print(f"\n{'='*60}")
        print("FIREFLY CORNER FARM — Seed Bank Importer")
        print(f"{'='*60}")

        if self.dry_run:
            print("\nDRY RUN — No changes will be made\n")

        # Load seed bank CSV
        with open(csv_path) as f:
            entries = list(csv.DictReader(f))

        # Filter to entries with seed data
        seed_entries = []
        for e in entries:
            has_seed = (
                bool(e.get("stock_level", "").strip()) or
                bool(e.get("unit", "").strip()) or
                (e.get("quantity_grams", "").strip() not in ("", "0"))
            )
            if not has_seed:
                continue
            if name_filter and name_filter.lower() not in e.get("farmos_name", "").lower():
                continue
            seed_entries.append(e)

        # Determine multi-source species (need source in asset name)
        from collections import Counter
        species_source_count = Counter(e["farmos_name"] for e in seed_entries)
        multi_source = {name for name, count in species_source_count.items() if count > 1}

        print(f"Processing {len(seed_entries)} seed entries "
              f"({len(species_source_count)} species, {len(multi_source)} multi-source)")

        if not self.dry_run:
            if not self.connect():
                return False

            # Pre-validate plant types
            all_species = set(e["farmos_name"] for e in seed_entries)
            print(f"\nValidating {len(all_species)} plant types...")
            missing = []
            for name in sorted(all_species):
                if not self.get_plant_type_uuid(name):
                    missing.append(name)
            if missing:
                print(f"\n! {len(missing)} plant types not found:")
                for n in missing:
                    print(f"    - {n}")
                print("\nAdd these to farmOS first, then re-run.")
                return False
            print(f"  All {len(all_species)} plant types verified.\n")

        # Process each entry
        for entry in sorted(seed_entries, key=lambda e: e["farmos_name"]):
            farmos_name = entry["farmos_name"]
            source = entry.get("source", "").strip()
            unit = entry.get("unit", "").strip().lower()
            qty_grams = self.parse_european_decimal(entry.get("quantity_grams", ""))
            stock_level = self.parse_european_decimal(entry.get("stock_level", ""))

            is_multi = farmos_name in multi_source
            asset_name = self.build_asset_name(farmos_name, source, is_multi)

            # Determine quantity value and unit
            if unit == "bulk" and qty_grams and qty_grams > 0:
                qty_value = qty_grams
                qty_unit_uuid = UNIT_GRAMS_UUID
                qty_measure = "weight"
                qty_label = "grams"
                qty_display = f"{qty_grams:.0f}g"
            elif stock_level is not None:
                qty_value = stock_level
                qty_unit_uuid = UNIT_STOCK_LEVEL_UUID
                qty_measure = "ratio"
                qty_label = "stock level"
                qty_display = f"stock={stock_level}"
            else:
                qty_value = None
                qty_display = "no qty"

            if self.dry_run:
                print(f"  + {asset_name} ({qty_display})")
                self.stats["assets_created"] += 1
                if qty_value is not None:
                    self.stats["logs_created"] += 1
                continue

            # Idempotent: skip if exists
            existing = self.seed_asset_exists(asset_name)
            if existing:
                print(f"  = {asset_name} (exists)")
                self.stats["assets_skipped"] += 1
                continue

            plant_type_uuid = self.get_plant_type_uuid(farmos_name)
            notes = self.build_notes(entry)

            # 1. Create seed asset
            seed_id = self.create_seed_asset(asset_name, plant_type_uuid, notes)
            if not seed_id:
                self.stats["failed"] += 1
                continue
            self.stats["assets_created"] += 1

            # 2. Create quantity + observation log (if we have qty data)
            if qty_value is not None:
                quantity_id = self.create_quantity(
                    seed_id, qty_value, qty_unit_uuid, qty_measure, qty_label
                )
                log_name = f"Seed inventory — {farmos_name}"
                log_id = self.create_observation_log(seed_id, quantity_id, log_name)
                if log_id:
                    print(f"  + {asset_name} ({qty_display})")
                    self.stats["logs_created"] += 1
                else:
                    print(f"  ~ {asset_name} (asset OK, log failed)")
                    self.stats["failed"] += 1
            else:
                print(f"  + {asset_name} (no qty)")

        # Summary
        print(f"\n{'='*60}")
        print("IMPORT SUMMARY")
        print(f"{'='*60}")
        print(f"  Seed assets created:  {self.stats['assets_created']}")
        print(f"  Seed assets skipped:  {self.stats['assets_skipped']}")
        print(f"  Observation logs:     {self.stats['logs_created']}")
        print(f"  Failed:               {self.stats['failed']}")

        if self.dry_run:
            print(f"\n  ** DRY RUN — run without --dry-run to apply changes **")
        else:
            print(f"\n  Import completed!")

        return True


def main():
    parser = argparse.ArgumentParser(description="Import seed bank into farmOS")
    parser.add_argument("--data", default="knowledge/seed_bank.csv",
                        help="Path to seed_bank.csv")
    parser.add_argument("--filter", default=None,
                        help="Filter by species name (case-insensitive substring)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview without making changes")
    args = parser.parse_args()

    data_path = Path(args.data)
    if not data_path.exists():
        print(f"Error: {data_path} not found")
        sys.exit(1)

    config = get_config()
    importer = SeedBankImporter(config, dry_run=args.dry_run)
    success = importer.import_all(str(data_path), name_filter=args.filter)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
