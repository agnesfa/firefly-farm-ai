#!/usr/bin/env python3
"""
Cleanup nursery plant assets in farmOS.

Compares the enriched nursery CSV (source of truth) against live farmOS data
and archives misplaced plants from the earlier CORRECTED_17Mar import.

Actions:
  - ARCHIVE: Plants in farmOS that don't match any CSV entry (wrong zone from old import)
  - CREATE:  Plants in CSV that don't exist in farmOS
  - No count updates needed (all matching entries have correct counts)

Usage:
    python scripts/cleanup_nursery.py --dry-run     # Preview changes
    python scripts/cleanup_nursery.py               # Execute cleanup
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
AEST = timezone(timedelta(hours=10))


class NurseryCleanup:
    def __init__(self, config, dry_run=False):
        self.config = config
        self.dry_run = dry_run
        self.session = None
        self.plant_type_cache = {}
        self.stats = {
            "archived": 0,
            "created": 0,
            "skipped": 0,
            "failed": 0,
            "already_correct": 0,
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

    def fetch_all_nursery_plants(self):
        """Fetch all active plant assets in nursery zones."""
        plants = []
        url = (
            f"{self.config['url']}/api/asset/plant"
            f"?filter[status]=active"
            f"&filter[name][operator]=CONTAINS&filter[name][value]=NURS."
            f"&page[limit]=50"
        )
        while url:
            resp = self.session.get(url)
            if resp.status_code != 200:
                print(f"Error fetching plants: {resp.status_code}")
                break
            data = resp.json()
            plants.extend(data.get("data", []))
            url = data.get("links", {}).get("next", {})
            if isinstance(url, dict):
                url = url.get("href")
        return plants

    def archive_plant(self, plant_id, plant_name, reason):
        """Archive a plant asset (set status to archived)."""
        data = {
            "data": {
                "type": "asset--plant",
                "id": plant_id,
                "attributes": {
                    "status": "archived",
                },
            }
        }
        try:
            resp = self.session.patch(
                f"{self.config['url']}/api/asset/plant/{plant_id}",
                json=data
            )
            if resp.status_code in (200, 201):
                # Create activity log explaining the archive
                self._create_archive_log(plant_id, plant_name, reason)
                return True
            else:
                print(f"    ! Archive failed: {resp.status_code} {resp.text[:150]}")
                return False
        except Exception as e:
            print(f"    ! Archive failed: {e}")
            return False

    def _create_archive_log(self, plant_id, plant_name, reason):
        """Create an activity log documenting why the plant was archived."""
        now = int(datetime.now(tz=AEST).timestamp())
        log_data = {
            "data": {
                "type": "log--activity",
                "attributes": {
                    "name": f"Archived — {plant_name}",
                    "timestamp": str(now),
                    "status": "done",
                    "notes": {"value": reason, "format": "default"},
                },
                "relationships": {
                    "asset": {
                        "data": [{"type": "asset--plant", "id": plant_id}]
                    },
                },
            }
        }
        try:
            self.session.post(f"{self.config['url']}/api/log/activity", json=log_data)
        except Exception:
            pass  # Non-critical

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

    def create_plant_with_inventory(self, asset_name, farmos_name, process, location_id, count):
        """Create a plant asset with observation log for inventory + location."""
        plant_type_uuid = self.get_plant_type_uuid(farmos_name)
        if not plant_type_uuid:
            print(f"    ! Plant type not found: {farmos_name}")
            return False

        location_uuid = LOCATION_UUIDS.get(location_id)
        if not location_uuid:
            print(f"    ! Location not found: {location_id}")
            return False

        # Create plant asset
        notes = f"Growing process: {process}" if process else ""
        data = {
            "data": {
                "type": "asset--plant",
                "attributes": {
                    "name": asset_name,
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
            if resp.status_code not in (200, 201):
                print(f"    ! Create plant failed: {resp.status_code} {resp.text[:150]}")
                return False
            plant_id = resp.json().get("data", {}).get("id")
        except Exception as e:
            print(f"    ! Create plant failed: {e}")
            return False

        # Create quantity entity
        qty_data = {
            "data": {
                "type": "quantity--standard",
                "attributes": {
                    "value": {"decimal": str(int(count))},
                    "measure": "count",
                    "label": "plants",
                    "inventory_adjustment": "reset",
                },
                "relationships": {
                    "units": {"data": {"type": "taxonomy_term--unit", "id": PLANT_UNIT_UUID}},
                    "inventory_asset": {"data": {"type": "asset--plant", "id": plant_id}},
                },
            }
        }
        try:
            resp = self.session.post(f"{self.config['url']}/api/quantity/standard", json=qty_data)
            quantity_id = resp.json().get("data", {}).get("id") if resp.status_code in (200, 201) else None
        except Exception:
            quantity_id = None

        # Create observation log (inventory + movement)
        now = int(datetime.now(tz=AEST).timestamp())
        log_data = {
            "data": {
                "type": "log--observation",
                "attributes": {
                    "name": f"Nursery inventory — {farmos_name} — {location_id}",
                    "timestamp": str(now),
                    "status": "done",
                    "is_movement": True,
                },
                "relationships": {
                    "asset": {"data": [{"type": "asset--plant", "id": plant_id}]},
                    "location": {"data": [{"type": "asset--structure", "id": location_uuid}]},
                },
            }
        }
        if quantity_id:
            log_data["data"]["relationships"]["quantity"] = {
                "data": [{"type": "quantity--standard", "id": quantity_id}]
            }
        try:
            self.session.post(f"{self.config['url']}/api/log/observation", json=log_data)
        except Exception:
            pass

        return True

    def run(self, csv_path):
        print(f"\n{'='*60}")
        print("FIREFLY CORNER FARM — Nursery Data Cleanup")
        print(f"{'='*60}")

        if self.dry_run:
            print("\n🔍 DRY RUN — No changes will be made\n")
        else:
            print()

        # Load CSV (source of truth)
        csv_lookup = {}
        with open(csv_path) as f:
            for row in csv.DictReader(f):
                loc = row.get('Location ID', '').strip()
                species = row.get('Species (farmOS)', '').strip()
                process = row.get('Process', '').strip()
                viable_col = [k for k in row.keys() if k.startswith('Viable')][0]
                try:
                    viable = float(row.get(viable_col, '0') or '0')
                except ValueError:
                    viable = 0
                if species and viable > 0:
                    process_label = f' ({process})' if process else ''
                    name = f'MAR 2026 - {species}{process_label} - {loc}'
                    csv_lookup[name] = {
                        'species': species, 'process': process,
                        'location': loc, 'count': int(viable)
                    }

        print(f"Loaded {len(csv_lookup)} viable entries from CSV\n")

        # Always connect — dry-run only skips writes, not reads
        if not self.connect():
            return False

        # Fetch all nursery plants from farmOS
        farmos_plants = self.fetch_all_nursery_plants()
        print(f"Found {len(farmos_plants)} active nursery plant assets in farmOS\n")

        farmos_lookup = {}
        for p in farmos_plants:
            name = p["attributes"]["name"]
            inv = p["attributes"].get("inventory", [])
            count = int(float(inv[0]["value"])) if inv else 0
            farmos_lookup[name] = {"id": p["id"], "count": count}

        # Phase 1: Archive misplaced plants
        print("Phase 1: ARCHIVE misplaced plants from old import")
        print("-" * 50)
        to_archive = sorted(n for n in farmos_lookup if n not in csv_lookup)
        if not to_archive:
            print("  (none to archive)")
        for name in to_archive:
            data = farmos_lookup[name]
            reason = (
                "Archived during nursery cleanup (March 29, 2026). "
                "This plant asset was created by the CORRECTED_17Mar import "
                "with incorrect zone mapping. The correct entry exists under "
                "the enriched March 20 import."
            )
            if self.dry_run:
                print(f"  🗄️  WOULD ARCHIVE: {name} (count={data['count']})")
                self.stats["archived"] += 1
            else:
                if self.archive_plant(data["id"], name, reason):
                    print(f"  🗄️  ARCHIVED: {name}")
                    self.stats["archived"] += 1
                else:
                    print(f"  ❌ FAILED: {name}")
                    self.stats["failed"] += 1

        # Phase 2: Create missing plants
        print(f"\nPhase 2: CREATE missing plants")
        print("-" * 50)
        to_create = sorted(
            (n, d) for n, d in csv_lookup.items()
            if n not in farmos_lookup
        )
        if not to_create:
            print("  (none to create)")
        for name, data in to_create:
            if self.dry_run:
                print(f"  ➕ WOULD CREATE: {name} (count={data['count']})")
                self.stats["created"] += 1
            else:
                # Idempotency: check if asset exists by exact name before creating
                existing = self.fetch_by_name("asset/plant", name)
                if any(a["attributes"]["name"] == name and a["attributes"]["status"] == "active" for a in existing):
                    print(f"  ⏭️  SKIPPED (already exists): {name}")
                    self.stats["already_correct"] += 1
                    continue
                if self.create_plant_with_inventory(
                    name, data['species'], data['process'],
                    data['location'], data['count']
                ):
                    print(f"  ➕ CREATED: {name} (count={data['count']})")
                    self.stats["created"] += 1
                else:
                    print(f"  ❌ FAILED: {name}")
                    self.stats["failed"] += 1

        # Phase 3: Count matching
        matching = sum(1 for n in csv_lookup if n in farmos_lookup)
        self.stats["already_correct"] = matching

        # Summary
        print(f"\n{'='*60}")
        print("CLEANUP SUMMARY")
        print(f"{'='*60}")
        print(f"  Plants archived:      {self.stats['archived']}")
        print(f"  Plants created:       {self.stats['created']}")
        print(f"  Already correct:      {self.stats['already_correct']}")
        print(f"  Failed:               {self.stats['failed']}")
        if self.dry_run:
            print(f"\n  ** DRY RUN — run without --dry-run to apply changes **")
        else:
            total_after = len(csv_lookup) + matching - self.stats["already_correct"] + self.stats["created"]
            print(f"\n  farmOS nursery should now have {len(csv_lookup)} active plant assets")
            print(f"  matching the enriched CSV exactly.")
        return True


def main():
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

    parser = argparse.ArgumentParser(description="Cleanup nursery data in farmOS")
    parser.add_argument("--data", default="knowledge/nursery_inventory_sheet_march2026.csv",
                        help="Path to enriched nursery CSV (source of truth)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview changes without modifying farmOS")
    args = parser.parse_args()

    data_path = Path(args.data)
    if not data_path.exists():
        data_path = Path(__file__).resolve().parent.parent / args.data
    if not data_path.exists():
        print(f"Error: {data_path} not found")
        sys.exit(1)

    cleanup = NurseryCleanup(config, dry_run=args.dry_run)
    success = cleanup.run(str(data_path))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
