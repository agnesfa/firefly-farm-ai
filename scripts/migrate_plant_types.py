#!/usr/bin/env python3
"""
Migrate farmOS plant_type taxonomy from v6 to v7.

Reads the mapping file (knowledge/plant_type_name_mapping.csv) and the master
plant types CSV (knowledge/plant_types.csv) to perform a full migration of the
farmOS plant_type taxonomy. Handles four action types:

  RENAME  — Find existing term by old name, rename to new farmos_name
  ARCHIVE — Find existing term, mark as archived
  EXISTS  — Find existing term, update description if changed
  CREATE  — Create new term (only if name doesn't already exist after renames)

Processes in the order above to handle edge cases where a RENAME creates a name
that a CREATE row also references, or where two RENAMEs target the same name.

Credentials are loaded from .env file (see .env.example).

Usage:
    python scripts/migrate_plant_types.py --dry-run       # Preview (default)
    python scripts/migrate_plant_types.py --execute        # Apply changes
    python scripts/migrate_plant_types.py --execute --verbose
"""

import csv
import os
import re
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


def parse_rename_action(action_str):
    """
    Parse a RENAME action string to extract old and new names.

    Handles both arrow styles:
      RENAME: "old" -> "new"
      RENAME: "old" → "new"

    Returns (old_name, new_name) or None if parsing fails.
    """
    # Match: RENAME: "old name" → "new name" or RENAME: "old name" -> "new name"
    match = re.match(
        r'RENAME:\s*"([^"]+)"\s*(?:→|->)\s*"([^"]+)"',
        action_str,
    )
    if match:
        return match.group(1), match.group(2)
    return None


class PlantTypeMigrator:
    """Handles full v6 to v7 farmOS plant_type taxonomy migration."""

    def __init__(self, config: dict, dry_run: bool = True, verbose: bool = False):
        self.config = config
        self.dry_run = dry_run
        self.verbose = verbose
        self.client = None

        # Keyed by lowercase name -> full term dict from farmOS
        self.existing_terms = {}

        # Plant data from v7 CSV, keyed by farmos_name
        self.plant_data = {}

        # Categorised actions from mapping file
        self.renames = []   # list of (farmos_name, common_name, variety, v6_name, old_name, new_name)
        self.archives = []  # list of (farmos_name,)
        self.exists = []    # list of (farmos_name, common_name, variety)
        self.creates = []   # list of (farmos_name, common_name, variety)

        # Stats
        self.stats = {
            "renamed": 0,
            "archived": 0,
            "updated": 0,
            "created": 0,
            "skipped": 0,
            "failed": 0,
        }

    # ── Connection ──────────────────────────────────────────────────

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
            print("  Connected successfully.")
            return True
        except Exception as e:
            print(f"  Authentication failed: {e}")
            return False

    # ── Data Loading ────────────────────────────────────────────────

    def load_existing_terms(self):
        """Load all existing plant_type terms from farmOS."""
        print("\nLoading existing plant_type terms from farmOS...")
        try:
            for term in self.client.term.iterate("plant_type"):
                name = term.get("attributes", {}).get("name", "")
                self.existing_terms[name.lower()] = term
            print(f"  Found {len(self.existing_terms)} existing terms.")
        except Exception as e:
            print(f"  ERROR loading existing terms: {e}")
            sys.exit(1)

    def load_plant_data(self, csv_path: str):
        """Load v7 plant types CSV for building descriptions."""
        print(f"\nLoading plant data from {csv_path}...")
        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    farmos_name = row.get("farmos_name", "").strip()
                    if farmos_name:
                        self.plant_data[farmos_name] = row
            print(f"  Loaded {len(self.plant_data)} plant type records.")
        except FileNotFoundError:
            print(f"  ERROR: CSV file not found: {csv_path}")
            sys.exit(1)

    def load_mapping(self, mapping_path: str):
        """Load and categorise the mapping file."""
        print(f"\nLoading mapping file from {mapping_path}...")
        try:
            with open(mapping_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
        except FileNotFoundError:
            print(f"  ERROR: Mapping file not found: {mapping_path}")
            sys.exit(1)

        for row in rows:
            farmos_name = row.get("farmos_name", "").strip()
            common_name = row.get("common_name", "").strip()
            variety = row.get("variety", "").strip()
            v6_name = row.get("v6_name", "").strip()
            action = row.get("action", "").strip()

            if action == "CREATE":
                self.creates.append((farmos_name, common_name, variety))
            elif action == "EXISTS":
                self.exists.append((farmos_name, common_name, variety))
            elif action.startswith("RENAME"):
                parsed = parse_rename_action(action)
                if parsed:
                    old_name, new_name = parsed
                    self.renames.append((farmos_name, common_name, variety, v6_name, old_name, new_name))
                else:
                    print(f"  WARNING: Could not parse RENAME action: {action}")
            elif action == "ARCHIVE":
                self.archives.append((farmos_name,))
            else:
                print(f"  WARNING: Unknown action '{action}' for {farmos_name}")

        print(f"  Loaded {len(rows)} mapping entries:")
        print(f"    RENAME:  {len(self.renames)}")
        print(f"    ARCHIVE: {len(self.archives)}")
        print(f"    EXISTS:  {len(self.exists)}")
        print(f"    CREATE:  {len(self.creates)}")

    # ── Description Builder ─────────────────────────────────────────

    def build_description(self, plant: dict) -> str:
        """Build rich description with syntropic data embedded.

        Same logic as import_plants.py — ensures consistent descriptions
        across all plant_type terms.
        """
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

    # ── Term Lookup Helper ──────────────────────────────────────────

    def find_term(self, name: str):
        """Find an existing term by name (case-insensitive). Returns the term dict or None."""
        return self.existing_terms.get(name.lower())

    def get_term_id(self, term: dict) -> str:
        """Extract UUID from a farmOS term dict."""
        return term.get("id", "")

    def get_term_name(self, term: dict) -> str:
        """Extract name from a farmOS term dict."""
        return term.get("attributes", {}).get("name", "")

    def get_term_description(self, term: dict) -> str:
        """Extract description value from a farmOS term dict."""
        desc = term.get("attributes", {}).get("description", {})
        if isinstance(desc, dict):
            return desc.get("value", "")
        return ""

    # ── PATCH Helper ────────────────────────────────────────────────

    def patch_term(self, term: dict, updates: dict) -> bool:
        """
        PATCH an existing term with the given attribute updates.

        Args:
            term: The existing term dict (must have 'id')
            updates: Dict of attributes to update (e.g. {"name": "New Name"})

        Returns True on success, False on failure.
        """
        term_id = self.get_term_id(term)
        if not term_id:
            print(f"    ERROR: Term has no ID, cannot update.")
            return False

        patch_data = {
            "id": term_id,
            "type": "taxonomy_term--plant_type",
            "attributes": updates,
        }

        if self.dry_run:
            return True

        try:
            self.client.term.send("plant_type", patch_data)
            return True
        except Exception as e:
            print(f"    ERROR: PATCH failed: {e}")
            return False

    # ── Action Processors ───────────────────────────────────────────

    def process_renames(self):
        """Process all RENAME actions. Must run first."""
        if not self.renames:
            return

        print(f"\n{'='*60}")
        print(f"PHASE 1: RENAME ({len(self.renames)} entries)")
        print(f"{'='*60}\n")

        # Track which farmos_names have already been renamed-to,
        # so we can handle the "two RENAMEs to same target" case.
        renamed_to = set()

        for farmos_name, common_name, variety, v6_name, old_name, new_name in self.renames:
            term = self.find_term(old_name)

            if not term:
                print(f"  SKIP: Old term '{old_name}' not found in farmOS (may have been renamed already)")
                self.stats["skipped"] += 1
                continue

            # Check if the target name already exists (e.g., two RENAMEs to the same name)
            if new_name.lower() in renamed_to:
                # The target already has a term. Archive this one instead.
                print(f"  ARCHIVE (duplicate target): '{old_name}' -- target '{new_name}' already taken")
                actual_name = self.get_term_name(term)
                updates = {"name": f"[ARCHIVED] {actual_name}"}
                if self.patch_term(term, updates):
                    if self.dry_run:
                        print(f"    Would archive '{actual_name}' (duplicate rename target)")
                    else:
                        # Update our index
                        del self.existing_terms[actual_name.lower()]
                        self.existing_terms[f"[archived] {actual_name}".lower()] = term
                        print(f"    Archived '{actual_name}' (duplicate rename target)")
                    self.stats["archived"] += 1
                else:
                    self.stats["failed"] += 1
                continue

            # Build new description from v7 data
            plant = self.plant_data.get(farmos_name, {})
            updates = {"name": new_name}
            if plant:
                new_desc = self.build_description(plant)
                if new_desc:
                    updates["description"] = {
                        "value": new_desc,
                        "format": "default",
                    }

            if self.dry_run:
                print(f"  Would rename: '{old_name}' -> '{new_name}'")
                if self.verbose and plant:
                    botanical = plant.get("botanical_name", "")
                    if botanical:
                        print(f"    Botanical: {botanical}")
                # Track in index for dry-run consistency checks
                self.existing_terms[new_name.lower()] = term
                if old_name.lower() != new_name.lower():
                    del self.existing_terms[old_name.lower()]
                renamed_to.add(new_name.lower())
                self.stats["renamed"] += 1
            else:
                if self.patch_term(term, updates):
                    print(f"  Renamed: '{old_name}' -> '{new_name}'")
                    # Update our index
                    if old_name.lower() != new_name.lower():
                        del self.existing_terms[old_name.lower()]
                    self.existing_terms[new_name.lower()] = term
                    renamed_to.add(new_name.lower())
                    self.stats["renamed"] += 1
                else:
                    self.stats["failed"] += 1

    def process_archives(self):
        """Process all ARCHIVE actions."""
        if not self.archives:
            return

        print(f"\n{'='*60}")
        print(f"PHASE 2: ARCHIVE ({len(self.archives)} entries)")
        print(f"{'='*60}\n")

        for (farmos_name,) in self.archives:
            term = self.find_term(farmos_name)

            if not term:
                # Could already be archived or renamed away
                print(f"  SKIP: Term '{farmos_name}' not found (may be already archived or renamed)")
                self.stats["skipped"] += 1
                continue

            actual_name = self.get_term_name(term)

            # Check if already archived
            if actual_name.startswith("[ARCHIVED]"):
                print(f"  SKIP: '{actual_name}' already archived")
                self.stats["skipped"] += 1
                continue

            updates = {"name": f"[ARCHIVED] {actual_name}"}

            if self.dry_run:
                print(f"  Would archive: '{actual_name}'")
                # Update index for dry-run consistency
                del self.existing_terms[actual_name.lower()]
                self.existing_terms[f"[archived] {actual_name}".lower()] = term
                self.stats["archived"] += 1
            else:
                if self.patch_term(term, updates):
                    print(f"  Archived: '{actual_name}'")
                    del self.existing_terms[actual_name.lower()]
                    self.existing_terms[f"[archived] {actual_name}".lower()] = term
                    self.stats["archived"] += 1
                else:
                    self.stats["failed"] += 1

    def process_exists(self):
        """Process all EXISTS actions — update descriptions if changed."""
        if not self.exists:
            return

        print(f"\n{'='*60}")
        print(f"PHASE 3: EXISTS / UPDATE ({len(self.exists)} entries)")
        print(f"{'='*60}\n")

        for farmos_name, common_name, variety in self.exists:
            term = self.find_term(farmos_name)

            if not term:
                # This term should exist but doesn't. It may have been renamed
                # away (e.g., "Lavender" EXISTS but also got RENAME to "Lavender - French").
                # In this case the RENAME already handled it.
                print(f"  SKIP: Term '{farmos_name}' not found (may have been renamed in Phase 1)")
                self.stats["skipped"] += 1
                continue

            # Build new description
            plant = self.plant_data.get(farmos_name, {})
            if not plant:
                if self.verbose:
                    print(f"  SKIP: No v7 data for '{farmos_name}' — cannot update description")
                self.stats["skipped"] += 1
                continue

            new_desc = self.build_description(plant)
            current_desc = self.get_term_description(term)

            if new_desc == current_desc:
                if self.verbose:
                    print(f"  No change: '{farmos_name}' (description identical)")
                self.stats["skipped"] += 1
                continue

            updates = {
                "description": {
                    "value": new_desc,
                    "format": "default",
                },
            }

            if self.dry_run:
                print(f"  Would update description: '{farmos_name}'")
                self.stats["updated"] += 1
            else:
                if self.patch_term(term, updates):
                    print(f"  Updated description: '{farmos_name}'")
                    self.stats["updated"] += 1
                else:
                    self.stats["failed"] += 1

    def process_creates(self):
        """Process all CREATE actions — only create if name doesn't already exist."""
        if not self.creates:
            return

        print(f"\n{'='*60}")
        print(f"PHASE 4: CREATE ({len(self.creates)} entries)")
        print(f"{'='*60}\n")

        for farmos_name, common_name, variety in self.creates:
            # Skip if name already exists (from RENAME or previous run)
            if self.find_term(farmos_name):
                if self.verbose:
                    print(f"  SKIP: '{farmos_name}' already exists (likely from RENAME)")
                self.stats["skipped"] += 1
                continue

            # Build description from v7 data
            plant = self.plant_data.get(farmos_name, {})
            description = self.build_description(plant) if plant else ""

            term_data = {
                "attributes": {
                    "name": farmos_name,
                    "description": {
                        "value": description,
                        "format": "default",
                    },
                }
            }

            # Add standard farmOS numeric fields if present in plant data
            # Only maturity_days and transplant_days are valid plant_type fields.
            # Skip zero values as farmOS may reject them.
            if plant:
                for field in ("maturity_days", "transplant_days"):
                    val = plant.get(field, "")
                    if val:
                        try:
                            int_val = int(val)
                            if int_val > 0:
                                term_data["attributes"][field] = int_val
                        except ValueError:
                            # Skip non-numeric values (e.g., ranges like "40-50")
                            pass

            if self.dry_run:
                botanical = plant.get("botanical_name", "") if plant else ""
                print(f"  Would create: '{farmos_name}'" + (f" ({botanical})" if botanical else ""))
                # Add to index for dry-run consistency
                self.existing_terms[farmos_name.lower()] = {"id": "dry-run-placeholder"}
                self.stats["created"] += 1
            else:
                try:
                    result = self.client.term.send("plant_type", term_data)
                    botanical = plant.get("botanical_name", "") if plant else ""
                    print(f"  Created: '{farmos_name}'" + (f" ({botanical})" if botanical else ""))
                    # Update our index
                    self.existing_terms[farmos_name.lower()] = result
                    self.stats["created"] += 1
                except Exception as e:
                    print(f"  ERROR creating '{farmos_name}': {e}")
                    self.stats["failed"] += 1

    # ── Main ────────────────────────────────────────────────────────

    def migrate(self, mapping_path: str, plants_csv_path: str):
        """Run the full migration."""
        print(f"\n{'='*60}")
        print("FIREFLY CORNER FARM")
        print("Plant Type Taxonomy Migration (v6 -> v7)")
        print(f"{'='*60}")

        if self.dry_run:
            print("\n  ** DRY RUN MODE -- No changes will be made **\n")
        else:
            print("\n  ** EXECUTE MODE -- Changes will be applied to farmOS **\n")

        # Step 1: Connect
        if not self.dry_run:
            if not self.connect():
                return False
            self.load_existing_terms()
        else:
            if not self.connect():
                return False
            self.load_existing_terms()

        # Step 2: Load data files
        self.load_plant_data(plants_csv_path)
        self.load_mapping(mapping_path)

        # Step 3: Validate before executing
        self._validate()

        # Step 4: Execute in order
        self.process_renames()
        self.process_archives()
        self.process_exists()
        self.process_creates()

        # Step 5: Summary
        self._print_summary()

        return self.stats["failed"] == 0

    def _validate(self):
        """Pre-flight validation: check for obvious issues."""
        print(f"\n{'='*60}")
        print("PRE-FLIGHT VALIDATION")
        print(f"{'='*60}\n")

        issues = 0

        # Check that RENAME old names actually exist
        for farmos_name, common_name, variety, v6_name, old_name, new_name in self.renames:
            if not self.find_term(old_name):
                print(f"  WARNING: RENAME source '{old_name}' not found in farmOS")
                issues += 1

        # Check that ARCHIVE terms exist
        for (farmos_name,) in self.archives:
            if not self.find_term(farmos_name):
                print(f"  WARNING: ARCHIVE target '{farmos_name}' not found in farmOS")
                issues += 1

        # Check that EXISTS terms exist
        for farmos_name, common_name, variety in self.exists:
            if not self.find_term(farmos_name):
                # Could be expected if a RENAME will move it
                renamed_targets = {old_name.lower() for _, _, _, _, old_name, _ in self.renames}
                if farmos_name.lower() in renamed_targets:
                    if self.verbose:
                        print(f"  INFO: EXISTS term '{farmos_name}' will be renamed away in Phase 1 (OK)")
                else:
                    print(f"  WARNING: EXISTS target '{farmos_name}' not found in farmOS")
                    issues += 1

        # Check that plant data exists for CREATE entries
        missing_data = 0
        for farmos_name, common_name, variety in self.creates:
            if farmos_name not in self.plant_data:
                if self.verbose:
                    print(f"  WARNING: No v7 plant data for CREATE entry '{farmos_name}'")
                missing_data += 1

        if missing_data:
            print(f"  WARNING: {missing_data} CREATE entries have no matching v7 plant data")
            issues += 1

        if issues == 0:
            print("  All checks passed.")
        else:
            print(f"\n  {issues} warning(s) found. Proceeding anyway...")

    def _print_summary(self):
        """Print final migration summary."""
        total_actions = sum(self.stats.values())

        print(f"\n{'='*60}")
        print("MIGRATION SUMMARY")
        print(f"{'='*60}")
        print(f"  Renamed:   {self.stats['renamed']}")
        print(f"  Archived:  {self.stats['archived']}")
        print(f"  Updated:   {self.stats['updated']}")
        print(f"  Created:   {self.stats['created']}")
        print(f"  Skipped:   {self.stats['skipped']}")
        print(f"  Failed:    {self.stats['failed']}")
        print(f"  ─────────────────────────")
        print(f"  Total:     {total_actions}")

        if self.dry_run:
            print(f"\n  ** This was a DRY RUN -- no changes were made **")
            print(f"  Run with --execute to apply changes to farmOS.")
        else:
            if self.stats["failed"] == 0:
                print(f"\n  Migration completed successfully!")
            else:
                print(f"\n  Migration completed with {self.stats['failed']} error(s).")
                print(f"  Re-run the script to retry failed operations (idempotent).")


def main():
    parser = argparse.ArgumentParser(
        description="Migrate farmOS plant_type taxonomy from v6 to v7 for Firefly Corner Farm"
    )
    parser.add_argument(
        "--mapping",
        default="knowledge/plant_type_name_mapping.csv",
        help="Mapping CSV file (default: knowledge/plant_type_name_mapping.csv)",
    )
    parser.add_argument(
        "--plants",
        default="knowledge/plant_types.csv",
        help="Plant types CSV file (default: knowledge/plant_types.csv)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Preview migration without making changes (default)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually apply changes to farmOS",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show additional detail (skip reasons, descriptions, etc.)",
    )
    args = parser.parse_args()

    # --execute overrides --dry-run
    dry_run = not args.execute

    mapping_path = Path(args.mapping)
    if not mapping_path.exists():
        print(f"Error: Mapping file not found: {mapping_path}")
        sys.exit(1)

    plants_path = Path(args.plants)
    if not plants_path.exists():
        print(f"Error: Plant types CSV not found: {plants_path}")
        sys.exit(1)

    config = get_farmos_config()
    migrator = PlantTypeMigrator(config, dry_run=dry_run, verbose=args.verbose)
    success = migrator.migrate(str(mapping_path), str(plants_path))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
