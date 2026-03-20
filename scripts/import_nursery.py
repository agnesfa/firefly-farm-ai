#!/usr/bin/env python3
"""
Import nursery inventory into farmOS as Plant assets + Observation logs.

Reads Nursery_inventory_CORRECTED_17Mar2026.csv and creates for each entry
with viable plants > 0:
1. Plant asset — named "MAR 2026 - {farmos_name} ({process}) - {location}"
2. Quantity entity — inventory count (plants)
3. Observation log — sets inventory count (inventory_adjustment=reset) + location
4. Transplanting log (pending) — if RTT > 0 and destination known

Features:
    - Dry-run mode (preview without changes)
    - Idempotent (checks for existing plant assets before creating)
    - Pre-validates all plant types exist in farmOS
    - Maps Claire's location names to farmOS structure asset UUIDs
    - Creates pending transplanting logs for ready-to-transplant plants

Usage:
    python scripts/import_nursery.py --dry-run
    python scripts/import_nursery.py
    python scripts/import_nursery.py --filter avocado
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

# farmOS UUIDs for nursery locations
LOCATION_UUIDS = {
    "NURS.SH1-1": "edfd9c77-692d-4f9d-b6e7-046bba464c51",
    "NURS.SH1-2": "04d00096-a9cc-463a-8964-d559de4df3a2",
    "NURS.SH1-3": "9e04d8e9-665a-4079-9199-b30c3f1b04c0",
    "NURS.SH1-4": "e19aa74a-6cfd-43e9-b9bd-558a0e1cfeb5",
    "NURS.SH2-1": "a33d9c74-653a-4d59-973a-e4e6ab3eead8",
    "NURS.SH2-2": "0c0905d3-fa12-40c1-8454-3aacce7fdc17",
    "NURS.SH2-3": "fc5085f4-3fea-4b32-a330-3da6899ac51e",
    "NURS.SH2-4": "62a03f0b-ded8-482d-9ae7-18a33255523b",
    "NURS.SH3-1": "ed56e74c-941e-4240-be5f-d5d6b800943a",
    "NURS.SH3-2": "3a44692b-a130-403c-806e-ccfc4de9aced",
    "NURS.SH3-3": "e237cfc5-b9bf-434d-8f6f-966d7182e514",
    "NURS.SH3-4": "99c20fe4-c670-4b88-8592-3402584f36db",
    "NURS.GR": "b597901d-69c0-43dd-bca6-7aebbd60d32f",
    "NURS.GL": "aaeece6f-67f4-4e3a-9de1-9f8b19584848",
    "NURS.BCK": "8f13ac07-593f-4491-90b9-e9845998f7c7",
    "NURS.FRT": "d4ee283d-b59d-424d-994e-1cb0bda5de10",
    "NURS.HILL": "072cc7a6-8ef8-4be3-ad90-0070d02a3142",
    "NURS.STRB": "18ac6701-c216-4c12-b9ce-8b87e7d6e9a7",
}

PLANT_UNIT_UUID = "2371b79e-a87b-4152-b6e4-ea6a9ed37fd0"
NURSERY_PARENT_UUID = "1baae724-ee3a-4637-b605-dd5f98682af1"  # "Plant nursery" asset
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


def map_location(shelves, floor):
    """Map Claire's SHELVES+FLOOR to farmOS location ID."""
    shelves = (shelves or '').strip()
    floor = (floor or '').strip()

    if shelves in ('I', 'II', 'III'):
        unit = {'I': '1', 'II': '2', 'III': '3'}[shelves]
        if ',' in floor:
            shelf_num = floor.split(',')[0].strip()
        elif floor in ('1', '2', '3', '4'):
            shelf_num = floor
        else:
            shelf_num = '1'  # default to top shelf
        return f"NURS.SH{unit}-{shelf_num}"
    elif shelves == 'GR' or floor == 'GR':
        return 'NURS.GR'
    elif shelves == 'GL' or floor == 'GL':
        return 'NURS.GL'
    elif shelves.lower() in ('behind nursery',) or floor.lower() in ('behind nursery',):
        return 'NURS.BCK'
    elif shelves == 'Hill Behind Nursery' or floor == 'Hill Behind Nursery':
        return 'NURS.HILL'
    elif shelves == 'outside' or floor in ('front nursery', 'outside'):
        return 'NURS.FRT'
    elif shelves.lower() == 'strawberries':
        return 'NURS.STRB'
    elif shelves == 'Front toolshed':
        return 'NURS.FRT'
    else:
        return 'NURS.GR'  # fallback


class NurseryImporter:
    def __init__(self, config, dry_run=False):
        self.config = config
        self.dry_run = dry_run
        self.session = None
        self.plant_type_cache = {}
        self.stats = {
            "plants_created": 0,
            "plants_skipped": 0,
            "obs_logs_created": 0,
            "transplant_logs_created": 0,
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

    def plant_asset_exists(self, asset_name):
        assets = self.fetch_by_name("asset/plant", asset_name)
        for a in assets:
            if a["attributes"]["name"] == asset_name:
                return a["id"]
        return None

    def create_plant_asset(self, name, plant_type_uuid, notes=""):
        data = {
            "data": {
                "type": "asset--plant",
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
        }
        if notes:
            data["data"]["attributes"]["notes"] = {"value": notes, "format": "default"}

        try:
            resp = self.session.post(f"{self.config['url']}/api/asset/plant", json=data)
            if resp.status_code in (200, 201):
                return resp.json().get("data", {}).get("id")
            else:
                print(f"    ! Create plant failed: {resp.status_code} {resp.text[:150]}")
                return None
        except Exception as e:
            print(f"    ! Create plant failed: {e}")
            return None

    def create_quantity(self, plant_id, value):
        payload = {
            "data": {
                "type": "quantity--standard",
                "attributes": {
                    "value": {"decimal": str(int(value))},
                    "measure": "count",
                    "label": "plants",
                    "inventory_adjustment": "reset",
                },
                "relationships": {
                    "units": {
                        "data": {"type": "taxonomy_term--unit", "id": PLANT_UNIT_UUID}
                    },
                    "inventory_asset": {
                        "data": {"type": "asset--plant", "id": plant_id}
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

    def create_observation_log(self, plant_id, quantity_id, log_name, location_uuid):
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
                        "data": [{"type": "asset--plant", "id": plant_id}]
                    },
                    "location": {
                        "data": [{"type": "asset--structure", "id": location_uuid}]
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
                print(f"    ! Create obs log failed: {resp.status_code} {resp.text[:150]}")
                return None
        except Exception as e:
            print(f"    ! Create obs log failed: {e}")
            return None

    def create_transplanting_log(self, plant_id, log_name, destination_text, rtt_count):
        """Create a PENDING transplanting log for ready-to-transplant plants."""
        now = int(datetime.now(tz=AEST).timestamp())
        notes = f"Ready to transplant: {rtt_count} plants.\nDestination: {destination_text}"
        log_data = {
            "data": {
                "type": "log--transplanting",
                "attributes": {
                    "name": log_name,
                    "timestamp": str(now),
                    "status": "pending",
                    "notes": {"value": notes, "format": "default"},
                },
                "relationships": {
                    "asset": {
                        "data": [{"type": "asset--plant", "id": plant_id}]
                    },
                },
            }
        }
        try:
            resp = self.session.post(f"{self.config['url']}/api/log/transplanting", json=log_data)
            if resp.status_code in (200, 201):
                return resp.json().get("data", {}).get("id")
            else:
                print(f"    ! Create transplanting log failed: {resp.status_code} {resp.text[:150]}")
                return None
        except Exception as e:
            print(f"    ! Create transplanting log failed: {e}")
            return None

    def build_asset_name(self, farmos_name, process, location_id):
        process_label = f" ({process})" if process else ""
        return f"MAR 2026 - {farmos_name}{process_label} - {location_id}"

    def build_notes(self, entry):
        parts = []
        process = entry.get('Process', '').strip()
        if process:
            parts.append(f"Growing process: {process}")
        date = entry.get('Seeding/Planting Date', '').strip()
        if date:
            parts.append(f"Seeding/planting date: {date}")
        pots = entry.get('Pots Planted', '').strip()
        if pots:
            parts.append(f"Pots planted: {pots}")
        viable = entry.get('_viable_str', '').strip()
        if viable:
            parts.append(f"Viable plants: {viable}")
        rate = entry.get('Success Rate %', '').strip()
        if rate:
            parts.append(f"Success rate: {rate}%")
        nrtt = entry.get('Not RTT', '').strip()
        if nrtt:
            parts.append(f"Not ready to transplant: {nrtt}")
        rtt = entry.get('RTT', '').strip()
        if rtt and rtt != '0':
            parts.append(f"Ready to transplant: {rtt}")
        where = entry.get('Destination', '').strip()
        if where:
            parts.append(f"Destination: {where}")
        source = entry.get('Source', '').strip()
        if source:
            parts.append(f"Source: {source}")
        mix_note = entry.get('_mix_note', '')
        if mix_note:
            parts.append(f"\n⚠️ {mix_note}")
        return "\n".join(parts)

    def import_all(self, csv_path, name_filter=None):
        print(f"\n{'='*60}")
        print("FIREFLY CORNER FARM — Nursery Inventory Importer")
        print(f"{'='*60}")

        if self.dry_run:
            print("\nDRY RUN — No changes will be made\n")

        with open(csv_path) as f:
            entries = list(csv.DictReader(f))

        # Detect CSV format: new enriched format has "Location ID" + "Species (farmOS)"
        has_new_format = "Location ID" in entries[0] and "Species (farmOS)" in entries[0]
        if has_new_format:
            print("Detected enriched CSV format (March 2026+)")
        else:
            print("ERROR: Expected enriched CSV format with 'Location ID' and 'Species (farmOS)' columns.")
            print("  Run scripts/transform_nursery_csv.py first to enrich the raw CSV.")
            return False

        # Find viable column (may be "Viable (Mar 20)" or "Viable (Mar 17)" etc.)
        viable_col = None
        for col in entries[0].keys():
            if col.startswith("Viable"):
                viable_col = col
                break
        if not viable_col:
            print("ERROR: No 'Viable (...)' column found")
            return False
        print(f"Using viable column: '{viable_col}'")

        # Filter to entries with viable plants > 0 and a farmos_name
        # Special handling: split "Mix Guava+Lemon" into two separate assets
        importable = []
        for e in entries:
            common = e.get('Common Name', '').strip()
            farmos_name = e.get('Species (farmOS)', '').strip()

            # Handle mixed pot — create two entries
            if 'Mix' in common and '+' in common and not farmos_name:
                try:
                    viable = float(e.get(viable_col, '0') or '0')
                except ValueError:
                    viable = 0
                if viable > 0:
                    mix_note = f"Mixed pot with {common} ({int(viable)} total viable). Shares pot — split TBD."
                    half = max(1, int(viable // 2))
                    remainder = int(viable) - half
                    for species, count in [("Guava (Strawberry)", half), ("Lemon", remainder)]:
                        clone = dict(e)
                        clone['Species (farmOS)'] = species
                        clone[viable_col] = str(count)
                        clone['_viable_str'] = str(count)
                        clone['_mix_note'] = mix_note
                        importable.append(clone)
                continue

            if not farmos_name:
                continue
            try:
                viable = float(e.get(viable_col, '0') or '0')
            except ValueError:
                viable = 0
            if viable <= 0:
                continue
            if name_filter and name_filter.lower() not in farmos_name.lower():
                continue
            e['_viable_str'] = e.get(viable_col, '0')
            importable.append(e)

        print(f"Processing {len(importable)} entries with viable plants (skipped {len(entries) - len(importable)})")

        if not self.dry_run:
            if not self.connect():
                return False

            # Pre-validate plant types
            all_species = set(e['Species (farmOS)'].strip() for e in importable)
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

        self.stats["obs_updated"] = 0

        for entry in sorted(importable, key=lambda e: e['Species (farmOS)']):
            farmos_name = entry['Species (farmOS)'].strip()
            process = entry.get('Process', '').strip()
            location_id = entry.get('Location ID', '').strip()
            viable = float(entry.get(viable_col, '0') or '0')
            rtt = entry.get('RTT', '').strip()
            where = entry.get('Destination', '').strip()

            location_uuid = LOCATION_UUIDS.get(location_id)
            asset_name = self.build_asset_name(farmos_name, process, location_id)

            try:
                rtt_count = float(rtt) if rtt else 0
            except ValueError:
                rtt_count = 0

            if self.dry_run:
                rtt_info = f" [RTT:{int(rtt_count)} → {where}]" if rtt_count > 0 and where else ""
                rtt_info = f" [RTT:{int(rtt_count)}]" if rtt_count > 0 and not where else rtt_info
                print(f"  + {asset_name} ({int(viable)} viable){rtt_info}")
                self.stats["plants_created"] += 1
                self.stats["obs_logs_created"] += 1
                if rtt_count > 0 and where:
                    self.stats["transplant_logs_created"] += 1
                continue

            if not location_uuid:
                print(f"  ! {asset_name} — unknown location {location_id}")
                self.stats["failed"] += 1
                continue

            # Check if plant asset already exists
            existing_id = self.plant_asset_exists(asset_name)

            if existing_id:
                # UPDATE: create new observation log with current count for existing plant
                quantity_id = self.create_quantity(existing_id, viable)
                obs_name = f"Nursery inventory Mar 20 — {farmos_name} — {location_id}"
                obs_id = self.create_observation_log(existing_id, quantity_id, obs_name, location_uuid)
                if obs_id:
                    print(f"  ↻ {asset_name} (updated count: {int(viable)})")
                    self.stats["obs_updated"] += 1
                else:
                    print(f"  ! {asset_name} (update failed)")
                    self.stats["failed"] += 1
                continue

            plant_type_uuid = self.get_plant_type_uuid(farmos_name)
            notes = self.build_notes(entry)

            # 1. Create plant asset
            plant_id = self.create_plant_asset(asset_name, plant_type_uuid, notes)
            if not plant_id:
                self.stats["failed"] += 1
                continue
            self.stats["plants_created"] += 1

            # 2. Create quantity + observation log (inventory + location)
            quantity_id = self.create_quantity(plant_id, viable)
            obs_name = f"Nursery inventory — {farmos_name} — {location_id}"
            obs_id = self.create_observation_log(plant_id, quantity_id, obs_name, location_uuid)
            if obs_id:
                print(f"  + {asset_name} ({int(viable)} viable)")
                self.stats["obs_logs_created"] += 1
            else:
                print(f"  ~ {asset_name} (asset OK, obs log failed)")
                self.stats["failed"] += 1

            # 3. Create pending transplanting log if RTT > 0 with destination
            if rtt_count > 0 and where:
                tx_name = f"Transplant pending — {farmos_name} → {where}"
                tx_id = self.create_transplanting_log(plant_id, tx_name, where, int(rtt_count))
                if tx_id:
                    print(f"    📋 Pending transplant: {int(rtt_count)} → {where}")
                    self.stats["transplant_logs_created"] += 1

        # Summary
        print(f"\n{'='*60}")
        print("IMPORT SUMMARY")
        print(f"{'='*60}")
        print(f"  Plant assets created:     {self.stats['plants_created']}")
        print(f"  Plant assets updated:     {self.stats.get('obs_updated', 0)}")
        print(f"  Plant assets skipped:     {self.stats['plants_skipped']}")
        print(f"  Observation logs:         {self.stats['obs_logs_created']}")
        print(f"  Transplanting (pending):  {self.stats['transplant_logs_created']}")
        print(f"  Failed:                   {self.stats['failed']}")

        if self.dry_run:
            print(f"\n  ** DRY RUN — run without --dry-run to apply changes **")
        else:
            print(f"\n  Import completed!")

        return True


def main():
    parser = argparse.ArgumentParser(description="Import nursery inventory into farmOS")
    parser.add_argument("--data", default="knowledge/nursery_inventory_sheet_march2026.csv",
                        help="Path to enriched nursery inventory CSV")
    parser.add_argument("--filter", default=None,
                        help="Filter by species name (case-insensitive substring)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview without making changes")
    args = parser.parse_args()

    data_path = Path(args.data)
    if not data_path.exists():
        # Try relative to home
        data_path = Path.home() / args.data
    if not data_path.exists():
        print(f"Error: {data_path} not found")
        sys.exit(1)

    config = get_config()
    importer = NurseryImporter(config, dry_run=args.dry_run)
    success = importer.import_all(str(data_path), name_filter=args.filter)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
