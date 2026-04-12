#!/usr/bin/env python3
"""
Export farmOS data for site generation and backup.

Two modes:
  1. Full export (default): Dump all farmOS data as raw JSON files.
  2. Sections JSON (--sections-json): Build enriched sections.json for QR landing pages.

The sections JSON mode reads existing sections.json for section metadata
(has_trees, length, range, green_manure) and replaces plant data with live
farmOS data enriched with per-plant log histories and accurate dates.

Credentials are loaded from .env file (see .env.example).

Usage:
    # Full raw export
    python scripts/export_farmos.py
    python scripts/export_farmos.py --output exports/

    # Sections JSON for site generation (Phase 1+)
    python scripts/export_farmos.py --sections-json
    python scripts/export_farmos.py --sections-json --output site/src/data/sections.json
"""

import json
import os
import re
import sys
import argparse
import urllib.parse
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional

from dotenv import load_dotenv

try:
    from farmOS import farmOS as farmOS_client
except ImportError:
    print("ERROR: farmOS library not installed!")
    print("Please install it with: pip install farmOS")
    sys.exit(1)


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


# ═══════════════════════════════════════════════════════════════
# SECTIONS JSON EXPORTER (Phase 1+)
# ═══════════════════════════════════════════════════════════════

class SectionsExporter:
    """Export farmOS data as enriched sections.json for QR landing pages.

    Uses farmOS.py for auth, then raw HTTP session.http_request() for
    paginated/filtered queries. This avoids farmOS.py's iterate() pagination
    bug (unreliable with 200+ entries) while staying in the main project venv.

    Strategy:
    - Read existing sections.json for section metadata (has_trees, length, etc.)
    - For each section, CONTAINS query for plants and logs
    - Build enriched plant entries with first_planted dates and log timelines
    """

    def __init__(self, config: dict, existing_sections_path: str):
        self.config = config
        self.client = None
        self.session = None  # HTTP session from farmOS.py
        self.hostname = config["hostname"].rstrip("/")
        self.existing = self._load_existing(existing_sections_path)

    def _load_existing(self, path: str) -> dict:
        """Load existing sections.json for section metadata."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            sections = data.get("sections", {})
            rows = data.get("rows", {})
            print(f"  Loaded existing sections.json: {len(sections)} sections, {len(rows)} rows")
            return data
        except FileNotFoundError:
            print(f"  WARNING: {path} not found — will create from scratch")
            return {"sections": {}, "rows": {}}

    def connect(self) -> bool:
        """Authenticate with farmOS."""
        print(f"Connecting to {self.hostname}...")
        try:
            self.client = farmOS_client(
                hostname=self.hostname,
                client_id=self.config["client_id"],
                scope=self.config["scope"],
            )
            self.client.authorize(
                username=self.config["username"],
                password=self.config["password"],
            )
            self.session = self.client.session
            print("  ✓ Authenticated")
            return True
        except Exception as e:
            print(f"  ✗ Authentication failed: {e}")
            return False

    # ── Raw HTTP helpers ──────────────────────────────────────

    def _http_get(self, path: str) -> dict:
        """GET request via farmOS session. Returns parsed JSON."""
        resp = self.session.http_request(path)
        if resp.status_code != 200:
            return {}
        return resp.json()

    def _fetch_contains(self, api_path: str, name_contains: str,
                        extra_filters: str = "", sort: str = "") -> list:
        """Fetch entities using CONTAINS filter on name, with full pagination.

        This is the reliable pattern for querying 400+ entities.
        Pushes filtering to farmOS server side, then follows pagination links.
        """
        encoded = urllib.parse.quote(name_contains)
        path = (f"/api/{api_path}"
                f"?filter[name][operator]=CONTAINS"
                f"&filter[name][value]={encoded}"
                f"&page[limit]=50")
        if extra_filters:
            path += f"&{extra_filters}"
        if sort:
            path += f"&sort={sort}"

        all_items = []
        seen_ids = set()

        while path:
            data = self._http_get(path)
            if not data:
                break

            for item in data.get("data", []):
                item_id = item.get("id", "")
                if item_id and item_id not in seen_ids:
                    seen_ids.add(item_id)
                    all_items.append(item)

            # Follow pagination
            next_link = data.get("links", {}).get("next", {})
            if isinstance(next_link, dict):
                full_url = next_link.get("href", "")
            elif isinstance(next_link, str):
                full_url = next_link
            else:
                full_url = ""

            if full_url:
                # Strip hostname prefix since http_request prepends it
                if full_url.startswith(self.hostname):
                    path = full_url[len(self.hostname):]
                else:
                    path = full_url
            else:
                path = None

        return all_items

    # ── Data fetching ──────────────────────────────────────────

    def fetch_section_plants(self, section_id: str) -> list:
        """Fetch active plant assets for a section using CONTAINS filter."""
        plants = self._fetch_contains(
            "asset/plant", section_id,
            extra_filters="filter[status]=active"
        )
        # Post-filter to ensure exact section match (avoid substring collisions
        # like "P2R2.0-3" matching "P2R2.0-30")
        exact = []
        for p in plants:
            name = p.get("attributes", {}).get("name", "")
            # Section is always the last segment after " - "
            parts = name.split(" - ")
            if len(parts) >= 3 and parts[-1].strip() == section_id:
                exact.append(p)
        return exact

    def fetch_section_logs(self, section_id: str, log_type: str) -> list:
        """Fetch logs for a section using CONTAINS filter."""
        return self._fetch_contains(
            f"log/{log_type}", section_id,
            sort="-timestamp"
        )

    # ── Plant asset parsing ────────────────────────────────────

    @staticmethod
    def parse_plant_name(name: str) -> dict:
        """Parse plant asset name into components.

        Format: "{date_label} - {species} - {section_id}"
        Species can contain " - " (e.g., "Basil - Sweet (Classic)")
        """
        parts = name.split(" - ")
        if len(parts) >= 3:
            return {
                "date_label": parts[0].strip(),
                "species": " - ".join(parts[1:-1]).strip(),
                "section": parts[-1].strip(),
            }
        elif len(parts) == 2:
            return {
                "date_label": parts[0].strip(),
                "species": parts[1].strip(),
                "section": "",
            }
        return {"date_label": "", "species": name, "section": ""}

    @staticmethod
    def parse_date_label_to_iso(date_label: str) -> str:
        """Convert a farmOS date label like '25 APR 2025' to ISO date '2025-04-25'.

        Also handles 'APR 2025' → '2025-04-01' and 'SPRING 2025' → '2025-09-01'.
        """
        if not date_label:
            return ""

        # "25 APR 2025" → 2025-04-25
        try:
            dt = datetime.strptime(date_label.strip(), "%d %b %Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

        # "APR 2025" → 2025-04-01
        try:
            dt = datetime.strptime(date_label.strip(), "%b %Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

        # "SPRING 2025" → approximate
        label = date_label.strip().upper()
        if "SPRING" in label:
            try:
                year = int(label.replace("SPRING", "").strip())
                return f"{year}-09-01"
            except ValueError:
                pass
        if "SUMMER" in label:
            try:
                year = int(label.replace("SUMMER", "").strip())
                return f"{year}-12-01"
            except ValueError:
                pass

        return ""

    @staticmethod
    def format_log_timestamp(timestamp_val) -> str:
        """Convert farmOS timestamp to ISO date string.

        farmOS JSON:API returns timestamps as ISO strings like
        '2025-11-12T14:00:00+00:00' (not Unix timestamps).
        The MCP server sees Unix ints because farmOS.py converts them,
        but raw HTTP returns the ISO string.
        """
        if not timestamp_val:
            return ""

        # ISO format: "2025-11-12T14:00:00+00:00"
        if isinstance(timestamp_val, str) and "T" in timestamp_val:
            try:
                dt = datetime.fromisoformat(timestamp_val.replace("Z", "+00:00"))
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                pass

        # Unix timestamp (integer or string of digits)
        try:
            ts = int(timestamp_val)
            dt = datetime.fromtimestamp(ts, tz=AEST)
            return dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError, OSError):
            pass

        return ""

    @staticmethod
    def extract_log_notes(log: dict) -> str:
        """Extract plain text notes from a log."""
        notes_raw = log.get("attributes", {}).get("notes", {})
        if isinstance(notes_raw, dict):
            return notes_raw.get("value", "")
        elif isinstance(notes_raw, str):
            return notes_raw
        return ""

    # ── Quantity / inventory extraction ─────────────────────────

    @staticmethod
    def extract_inventory_count(plant: dict) -> Optional[int]:
        """Extract current inventory count from a plant asset's computed inventory field.

        farmOS computes inventory from all Quantity entities (with inventory_adjustment
        set to reset/increment/decrement) attached to logs referencing this asset.
        The result is available directly on the asset's `inventory` attribute:

            inventory: [{"measure": "count", "value": "4", "units": "plant"}]

        This is the farmOS-native way to track inventory — no need to manually
        look up individual Quantity entities or observation logs.
        """
        inventory = plant.get("attributes", {}).get("inventory", [])
        if inventory:
            for inv in inventory:
                val = inv.get("value")
                if val is not None:
                    try:
                        return int(float(val))
                    except (ValueError, TypeError):
                        pass
        return None

    # ── Plant strata lookup ────────────────────────────────────

    def get_plant_strata(self, species: str, plant_db: dict) -> str:
        """Look up strata from plant_types.csv.

        The plant_types.csv is the master reference for syntropic metadata.
        This avoids per-plant API calls to the taxonomy.
        """
        if species in plant_db:
            return plant_db[species].get("strata", "low")
        return "low"

    # ── Species reference photos ───────────────────────────────

    def fetch_species_photo_urls(self) -> dict:
        """Fetch the plant_type taxonomy and build {farmos_name: photo_url}.

        Plant types with no reference photo are omitted. The reference photo
        is populated by the import_observations photo pipeline (latest-wins
        per species).

        Photos are downloaded to site/public/photos/ at build time so they
        can be served as static files on GitHub Pages (farmOS file URLs
        require authentication and cannot be hotlinked from public pages).

        Returns {farmos_name: relative_path} e.g. {"Sunflower": "photos/sunflower.jpg"}.

        One API call fetches all plant_type terms with their image
        relationship included; the included[] array carries the file
        entities whose ``attributes.uri.url`` is the public path.
        """
        import re
        photos_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "site", "public", "photos")
        os.makedirs(photos_dir, exist_ok=True)

        remote_photos: dict[str, str] = {}  # {farmos_name: farmOS_url}
        # include=image pulls the file entities into included[]. page[limit]
        # is capped at 50 by farmOS; we paginate via links.next.
        path = "/api/taxonomy_term/plant_type?include=image&page[limit]=50"
        while path:
            data = self._http_get(path)
            if not data:
                break

            # Index included files by UUID so we can resolve the relationship.
            files_by_id: dict[str, str] = {}
            for inc in data.get("included", []) or []:
                if inc.get("type") != "file--file":
                    continue
                uri = (inc.get("attributes") or {}).get("uri") or {}
                url = uri.get("url") if isinstance(uri, dict) else ""
                if not url:
                    continue
                # Make relative URLs absolute against the farmOS host.
                if url.startswith("/"):
                    url = self.hostname.rstrip("/") + url
                files_by_id[inc.get("id", "")] = url

            for term in data.get("data", []) or []:
                attrs = term.get("attributes") or {}
                name = attrs.get("name", "")
                image_rel = (term.get("relationships") or {}).get("image") or {}
                rel_data = image_rel.get("data")
                # The image field is multi-value on taxonomy terms (data is a list)
                if isinstance(rel_data, list) and rel_data:
                    file_id = rel_data[-1].get("id", "")  # latest
                elif isinstance(rel_data, dict):
                    file_id = rel_data.get("id", "")
                else:
                    file_id = ""
                if file_id and file_id in files_by_id and name:
                    remote_photos[name] = files_by_id[file_id]

            # Follow pagination
            next_link = (data.get("links") or {}).get("next", {})
            if isinstance(next_link, dict):
                full_url = next_link.get("href", "")
            elif isinstance(next_link, str):
                full_url = next_link
            else:
                full_url = ""
            if full_url:
                path = full_url[len(self.hostname):] if full_url.startswith(self.hostname) else full_url
            else:
                path = None

        # Download each photo, create two versions:
        # 1. Thumbnail: 112×112 square crop (2× retina for 56px CSS cards) ~5KB
        # 2. Lightbox: 800px max dimension, preserves aspect ratio ~30-80KB
        from PIL import Image
        from io import BytesIO

        THUMB_SIZE = 112   # 2× for retina display at 56px CSS
        LIGHTBOX_MAX = 800  # Max dimension for lightbox view
        THUMB_QUALITY = 75
        LIGHTBOX_QUALITY = 80

        local_photos: dict[str, str] = {}
        for name, url in remote_photos.items():
            slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
            thumb_filename = f"{slug}.jpg"
            lightbox_filename = f"{slug}-full.jpg"
            thumb_path = os.path.join(photos_dir, thumb_filename)
            lightbox_path = os.path.join(photos_dir, lightbox_filename)
            try:
                resp = self.session.get(url, timeout=30)
                resp.raise_for_status()
                img = Image.open(BytesIO(resp.content))
                img = img.convert("RGB")

                # Lightbox: resize to max 800px, preserve aspect ratio
                lightbox_img = img.copy()
                lightbox_img.thumbnail((LIGHTBOX_MAX, LIGHTBOX_MAX), Image.LANCZOS)
                lightbox_img.save(lightbox_path, "JPEG", quality=LIGHTBOX_QUALITY, optimize=True)

                # Thumbnail: center-crop to square, then resize to 112×112
                w, h = img.size
                side = min(w, h)
                left = (w - side) // 2
                top = (h - side) // 2
                thumb_img = img.crop((left, top, left + side, top + side))
                thumb_img = thumb_img.resize((THUMB_SIZE, THUMB_SIZE), Image.LANCZOS)
                thumb_img.save(thumb_path, "JPEG", quality=THUMB_QUALITY, optimize=True)

                local_photos[name] = f"photos/{thumb_filename}"
            except Exception as e:
                print(f"    ! failed to download photo for {name}: {e}")

        return local_photos

    # ── Main export logic ──────────────────────────────────────

    def export_sections_json(self, output_path: str, plant_db: dict):
        """Build and write enriched sections.json from live farmOS data."""
        if not self.connect():
            return False

        existing_sections = self.existing.get("sections", {})
        existing_rows = self.existing.get("rows", {})

        if not existing_sections:
            print("ERROR: No existing sections found. Run parse_fieldsheets.py first.")
            return False

        enriched_sections = {}
        total_plants = 0
        total_logs = 0

        print(f"\n{'='*60}")
        print(f"EXPORTING ENRICHED SECTIONS JSON")
        print(f"{'='*60}")
        print(f"Sections to process: {len(existing_sections)}")

        # Build species → photo URL map from the plant_type taxonomy once.
        # The import_observations photo pipeline attaches latest-wins photos
        # to each term; we surface them on plant cards so WWOOFers have a
        # visual reference for species identification.
        print("Fetching species reference photos from plant_type taxonomy...")
        try:
            species_photos = self.fetch_species_photo_urls()
            print(f"  → {len(species_photos)} species with reference photos")
        except Exception as e:
            print(f"  ! reference photo fetch failed: {e}")
            species_photos = {}

        for section_id, section_meta in existing_sections.items():
            print(f"\n  {section_id}...")

            # Fetch plants for this section
            plants_raw = self.fetch_section_plants(section_id)
            print(f"    Plants: {len(plants_raw)}")

            # Fetch logs for this section (observation + transplanting)
            obs_logs = self.fetch_section_logs(section_id, "observation")
            trans_logs = self.fetch_section_logs(section_id, "transplanting")
            activity_logs = self.fetch_section_logs(section_id, "activity")
            all_logs = obs_logs + trans_logs + activity_logs
            print(f"    Logs: {len(obs_logs)} obs + {len(trans_logs)} trans + {len(activity_logs)} activity")

            # Build enriched plant entries
            enriched_plants = []
            latest_obs_date = ""

            for plant in plants_raw:
                attrs = plant.get("attributes", {})
                name = attrs.get("name", "")
                parsed = self.parse_plant_name(name)
                species = parsed["species"]
                date_label = parsed["date_label"]
                first_planted = self.parse_date_label_to_iso(date_label)

                # Get strata from plant_types.csv (the master reference)
                strata = self.get_plant_strata(species, plant_db)

                # Get inventory count — farmOS computes this from Quantity entities
                # on observation logs with inventory_adjustment: "reset"
                inventory = self.extract_inventory_count(plant)

                # Match logs to this plant by species name in log name
                plant_logs = []
                for log in all_logs:
                    log_name = log.get("attributes", {}).get("name", "")
                    # Log names contain the species or are associated with the plant
                    if species.lower() in log_name.lower() or name in log_name:
                        log_type = log.get("type", "").replace("log--", "")
                        log_ts = self.format_log_timestamp(
                            log.get("attributes", {}).get("timestamp")
                        )
                        log_notes = self.extract_log_notes(log)
                        plant_logs.append({
                            "type": log_type,
                            "date": log_ts,
                            "name": log_name,
                            "notes": log_notes[:200] if log_notes else "",
                        })

                        # Track latest observation date for section
                        if log_type == "observation" and log_ts > latest_obs_date:
                            latest_obs_date = log_ts

                # Sort logs by date ascending
                plant_logs.sort(key=lambda x: x["date"])

                # Extract notes from plant asset
                notes_raw = attrs.get("notes", {})
                notes = ""
                if isinstance(notes_raw, dict):
                    notes = notes_raw.get("value", "")
                elif isinstance(notes_raw, str):
                    notes = notes_raw
                # Strip HTML tags from notes
                notes = re.sub(r"<[^>]+>", "", notes).strip()

                # Determine first_planted from earliest transplanting log
                # (more accurate than asset name date for renovation plants)
                transplanting_dates = [
                    l["date"] for l in plant_logs
                    if l["type"] == "transplanting" and l["date"]
                ]
                if transplanting_dates:
                    first_planted_actual = min(transplanting_dates)
                else:
                    first_planted_actual = first_planted  # fallback to asset name date

                enriched_plants.append({
                    "species": species,
                    "strata": strata,
                    "count": inventory,
                    "notes": notes,
                    "first_planted": first_planted_actual,
                    "asset_name": name,
                    "logs": plant_logs,
                    "photo_url": species_photos.get(species, ""),
                })

            total_plants += len(enriched_plants)
            total_logs += len(all_logs)

            # Build enriched section — preserve metadata from existing
            enriched_section = {
                "id": section_id,
                "paddock": section_meta.get("paddock", 2),
                "row": section_meta.get("row", 0),
                "range": section_meta.get("range", ""),
                "length": section_meta.get("length", ""),
                "has_trees": section_meta.get("has_trees", False),
                "first_planted": first_planted if enriched_plants else section_meta.get("first_planted", ""),
                "inventory_date": latest_obs_date or section_meta.get("inventory_date", ""),
                "plants": enriched_plants,
            }

            # Preserve green_manure data from existing sections.json
            if "green_manure" in section_meta:
                enriched_section["green_manure"] = section_meta["green_manure"]

            # Compute section first_planted from earliest plant
            if enriched_plants:
                plant_dates = [p["first_planted"] for p in enriched_plants if p["first_planted"]]
                if plant_dates:
                    enriched_section["first_planted"] = min(plant_dates)

            enriched_sections[section_id] = enriched_section

        # Build output structure
        output = {
            "generated": True,
            "generated_from": "farmOS",
            "generated_at": datetime.now(tz=AEST).isoformat(),
            "sections": enriched_sections,
            "rows": existing_rows,
        }

        # Write output
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        print(f"\n{'='*60}")
        print(f"SECTIONS JSON EXPORT COMPLETE")
        print(f"{'='*60}")
        print(f"  Sections: {len(enriched_sections)}")
        print(f"  Plants: {total_plants}")
        print(f"  Logs matched: {total_logs}")
        print(f"  Output: {output_file}")

        return True


# ═══════════════════════════════════════════════════════════════
# FULL RAW EXPORTER (existing)
# ═══════════════════════════════════════════════════════════════

class FarmOSExporter:
    """Exports data from farmOS instance."""

    def __init__(self, config: dict):
        self.config = config
        self.client = None

    def connect(self):
        """Authenticate with farmOS."""
        print(f"Connecting to {self.config['hostname']}...")
        try:
            self.client = farmOS_client(
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


# ═══════════════════════════════════════════════════════════════
# PLANT DATABASE LOADER
# ═══════════════════════════════════════════════════════════════

def load_plant_db(csv_path: str) -> dict:
    """Load plant_types.csv into a lookup dict keyed by farmos_name."""
    import csv
    plants = {}
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = row.get("farmos_name", "").strip() or row.get("common_name", "").strip()
                if key:
                    plants[key] = {
                        "strata": row.get("strata", "low"),
                        "succession": row.get("succession_stage", ""),
                        "botanical": row.get("botanical_name", ""),
                    }
    except FileNotFoundError:
        print(f"  WARNING: {csv_path} not found")
    return plants


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Export data from farmOS")
    parser.add_argument(
        "--output",
        default=None,
        help="Output path (directory for full export, file for --sections-json)",
    )
    parser.add_argument(
        "--sections-json",
        action="store_true",
        help="Export enriched sections.json for QR landing pages (instead of full raw export)",
    )
    parser.add_argument(
        "--existing",
        default="site/src/data/sections.json",
        help="Path to existing sections.json for metadata (used with --sections-json)",
    )
    parser.add_argument(
        "--plants",
        default="knowledge/plant_types.csv",
        help="Path to plant_types.csv for strata lookup (used with --sections-json)",
    )
    args = parser.parse_args()

    config = get_farmos_config()

    if args.sections_json:
        # Sections JSON mode
        output_path = args.output or "site/src/data/sections.json"
        plant_db = load_plant_db(args.plants)
        print(f"  Plant DB: {len(plant_db)} types loaded")

        exporter = SectionsExporter(config, args.existing)
        success = exporter.export_sections_json(output_path, plant_db)
    else:
        # Full raw export mode (existing behavior)
        if args.output:
            output_dir = Path(args.output)
        else:
            output_dir = Path("exports") / f"farmos_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        exporter = FarmOSExporter(config)
        success = exporter.export_all(output_dir)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
