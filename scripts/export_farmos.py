#!/usr/bin/env python3
"""
Export all farmOS data into organized JSON files.

Connects to the Firefly Corner farmOS instance and exports assets, logs,
and taxonomy terms. Used for data backup, analysis, and as the data source
for site generation (Phase 1+).

Credentials are loaded from .env file (see .env.example).

Usage:
    python scripts/export_farmos.py
    python scripts/export_farmos.py --output exports/

Output:
    {output_dir}/farm_info.json
    {output_dir}/assets/*.json
    {output_dir}/logs/*.json
    {output_dir}/taxonomy/*.json
    {output_dir}/export_summary.json
"""

import json
import os
import sys
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

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


class FarmOSExporter:
    """Exports data from farmOS instance."""

    def __init__(self, config: dict):
        self.config = config
        self.client = None

    def connect(self):
        """Authenticate with farmOS."""
        print(f"Connecting to {self.config['hostname']}...")
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

    def get_farm_info(self) -> Dict[str, Any]:
        """Get basic farm information."""
        print("\nFetching farm information...")
        try:
            info = {
                "hostname": self.config["hostname"],
                "exported_at": datetime.now().isoformat(),
                "api_version": "2.x",
            }
            print("✓ Farm info retrieved")
            return info
        except Exception as e:
            print(f"✗ Failed to get farm info: {e}")
            return {}

    def export_assets(self) -> List[Dict[str, Any]]:
        """Export all assets by type."""
        assets = []
        asset_types = [
            "plant", "animal", "equipment", "land", "water",
            "structure", "compost", "material", "seed", "group",
        ]

        print("Fetching all assets...")
        for atype in asset_types:
            try:
                print(f"  - Fetching {atype} assets...")
                for asset in self.client.asset.iterate(atype):
                    assets.append(asset)
                count = len([a for a in assets if a.get("type") == f"asset--{atype}"])
                print(f"    ✓ Found {count} {atype} assets")
            except Exception as e:
                print(f"    ⚠ No {atype} assets or error: {e}")
                continue

        print(f"✓ Total assets exported: {len(assets)}")
        return assets

    def export_logs(self) -> List[Dict[str, Any]]:
        """Export all logs by type."""
        logs = []
        log_types = [
            "activity", "observation", "harvest", "input",
            "seeding", "transplanting", "maintenance", "purchase",
            "sale", "lab_test", "medical", "birth",
        ]

        print("Fetching all logs...")
        for ltype in log_types:
            try:
                print(f"  - Fetching {ltype} logs...")
                for log in self.client.log.iterate(ltype):
                    logs.append(log)
                count = len([l for l in logs if l.get("type") == f"log--{ltype}"])
                print(f"    ✓ Found {count} {ltype} logs")
            except Exception as e:
                print(f"    ⚠ No {ltype} logs or error: {e}")
                continue

        print(f"✓ Total logs exported: {len(logs)}")
        return logs

    def export_taxonomy_terms(self) -> List[Dict[str, Any]]:
        """Export all taxonomy terms."""
        terms = []
        vocabularies = [
            "plant_type", "animal_type", "season",
            "unit", "log_category", "material_type",
            "crop_family", "quantity_type",
        ]

        print("Fetching all taxonomy terms...")
        for vocab in vocabularies:
            try:
                print(f"  - Fetching {vocab} terms...")
                for term in self.client.term.iterate(vocab):
                    terms.append(term)
                count = len([t for t in terms if vocab in t.get("type", "")])
                print(f"    ✓ Found {count} {vocab} terms")
            except Exception as e:
                print(f"    ⚠ No {vocab} terms or error: {e}")
                continue

        print(f"✓ Total taxonomy terms exported: {len(terms)}")
        return terms

    @staticmethod
    def save_json(data: Any, filepath: Path):
        """Save data as JSON file."""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"✓ Saved to {filepath}")

    def export_all(self, output_dir: Path):
        """Export all farmOS data."""
        if not self.connect():
            return False

        print(f"\n{'='*60}")
        print("STARTING FULL FARMOS DATA EXPORT")
        print(f"{'='*60}")
        print(f"\nOutput directory: {output_dir.absolute()}")

        # Farm info
        farm_info = self.get_farm_info()
        self.save_json(farm_info, output_dir / "farm_info.json")

        # Assets
        print(f"\n{'-'*60}\nEXPORTING ASSETS\n{'-'*60}")
        assets = self.export_assets()
        self.save_json(assets, output_dir / "assets" / "all_assets.json")

        assets_by_type = {}
        for asset in assets:
            asset_type = asset.get("type", "unknown")
            assets_by_type.setdefault(asset_type, []).append(asset)
        for asset_type, type_assets in assets_by_type.items():
            type_name = asset_type.replace("asset--", "")
            self.save_json(type_assets, output_dir / "assets" / f"{type_name}_assets.json")

        # Logs
        print(f"\n{'-'*60}\nEXPORTING LOGS\n{'-'*60}")
        logs = self.export_logs()
        self.save_json(logs, output_dir / "logs" / "all_logs.json")

        logs_by_type = {}
        for log in logs:
            log_type = log.get("type", "unknown")
            logs_by_type.setdefault(log_type, []).append(log)
        for log_type, type_logs in logs_by_type.items():
            type_name = log_type.replace("log--", "")
            self.save_json(type_logs, output_dir / "logs" / f"{type_name}_logs.json")

        # Taxonomy terms
        print(f"\n{'-'*60}\nEXPORTING TAXONOMY TERMS\n{'-'*60}")
        terms = self.export_taxonomy_terms()
        self.save_json(terms, output_dir / "taxonomy" / "all_terms.json")

        terms_by_vocab = {}
        for term in terms:
            term_type = term.get("type", "unknown")
            terms_by_vocab.setdefault(term_type, []).append(term)
        for vocab_type, vocab_terms in terms_by_vocab.items():
            vocab_name = vocab_type.replace("taxonomy_term--", "")
            self.save_json(vocab_terms, output_dir / "taxonomy" / f"{vocab_name}_terms.json")

        # Summary
        summary = {
            "export_info": farm_info,
            "statistics": {
                "total_assets": len(assets),
                "assets_by_type": {k.replace("asset--", ""): len(v) for k, v in assets_by_type.items()},
                "total_logs": len(logs),
                "logs_by_type": {k.replace("log--", ""): len(v) for k, v in logs_by_type.items()},
                "total_terms": len(terms),
                "terms_by_vocabulary": {k.replace("taxonomy_term--", ""): len(v) for k, v in terms_by_vocab.items()},
            },
        }
        self.save_json(summary, output_dir / "export_summary.json")

        print(f"\n{'='*60}")
        print("EXPORT COMPLETE!")
        print(f"{'='*60}")
        print(f"\nAll data exported to: {output_dir.absolute()}")
        print(f"\n  - Total Assets: {len(assets)}")
        print(f"  - Total Logs: {len(logs)}")
        print(f"  - Total Taxonomy Terms: {len(terms)}")
        return True


def main():
    parser = argparse.ArgumentParser(description="Export all data from farmOS")
    parser.add_argument(
        "--output",
        default=None,
        help="Output directory (default: exports/farmos_export_YYYYMMDD_HHMMSS)",
    )
    args = parser.parse_args()

    if args.output:
        output_dir = Path(args.output)
    else:
        output_dir = Path("exports") / f"farmos_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    config = get_farmos_config()
    exporter = FarmOSExporter(config)
    success = exporter.export_all(output_dir)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
