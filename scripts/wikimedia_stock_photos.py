#!/usr/bin/env python3
"""
Wikimedia Stock Photo Batch — Tier 2 reference photo enrichment.

Fetches CC-licensed species photos from Wikimedia Commons for plant types
that have no reference photo in farmOS. These are Tier 2 display photos
for WWOOFer identification on QR pages — NOT counted in the
species_photo_coverage metric (which only counts Tier 1 farm-sourced).

Usage:
    python scripts/wikimedia_stock_photos.py --dry-run
    python scripts/wikimedia_stock_photos.py --species "Pigeon Pea"
    python scripts/wikimedia_stock_photos.py

Requires: FARMOS_URL, FARMOS_USERNAME, FARMOS_PASSWORD, FARMOS_CLIENT_ID
in .env or environment.
"""

import argparse
import io
import os
import sys
import time
from pathlib import Path

# Add parent dirs for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "mcp-server"))

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from farmos_client import FarmOSClient
from helpers import parse_plant_type_metadata
from interaction_stamp import build_stamp

# ── Wikimedia Commons API ─────────────────────────────────────

WIKI_API = "https://en.wikipedia.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "FireflyCornerFarmBot/1.0 (https://agnesfa.github.io/firefly-farm-ai/; agnes@fireflycorner.farm)"
RATE_LIMIT_SECONDS = 1.0
MAX_IMAGE_DIM = 800


def fetch_wikimedia_image(botanical_name: str, session: requests.Session) -> tuple[bytes, str] | None:
    """Fetch a species image from Wikimedia Commons via Wikipedia.

    Strategy:
    1. Search Wikipedia for the botanical name
    2. Get the page's main image (pageimage)
    3. Fetch the original from Commons

    Returns (image_bytes, filename) or None.
    """
    # Step 1: Find Wikipedia page for the species
    params = {
        "action": "query",
        "titles": botanical_name,
        "prop": "pageimages",
        "piprop": "original",
        "format": "json",
        "redirects": 1,
    }
    try:
        resp = session.get(WIKI_API, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  Wikipedia API error: {e}")
        return None

    pages = data.get("query", {}).get("pages", {})
    for page_id, page in pages.items():
        if page_id == "-1":
            continue
        original = page.get("original", {})
        source_url = original.get("source")
        if source_url:
            return _download_image(source_url, session)

    # Step 2: Try Commons directly with search
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": f"File:{botanical_name}",
        "gsrnamespace": 6,  # File namespace
        "gsrlimit": 3,
        "prop": "imageinfo",
        "iiprop": "url|mime",
        "iiurlwidth": MAX_IMAGE_DIM,
        "format": "json",
    }
    try:
        resp = session.get(COMMONS_API, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  Commons API error: {e}")
        return None

    pages = data.get("query", {}).get("pages", {})
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        url = info.get("thumburl") or info.get("url")
        mime = info.get("mime", "")
        if url and "image" in mime:
            return _download_image(url, session)

    return None


def _download_image(url: str, session: requests.Session) -> tuple[bytes, str] | None:
    """Download and resize an image."""
    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        image_bytes = resp.content
        if len(image_bytes) < 1000:
            return None

        # Resize if needed
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(image_bytes))
            if max(img.size) > MAX_IMAGE_DIM:
                img.thumbnail((MAX_IMAGE_DIM, MAX_IMAGE_DIM), Image.LANCZOS)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=80)
            image_bytes = buf.getvalue()
        except ImportError:
            pass  # PIL not available, use original

        filename = url.rsplit("/", 1)[-1].split("?")[0]
        if not filename.lower().endswith((".jpg", ".jpeg", ".png")):
            filename = "wikimedia_stock.jpg"

        return image_bytes, filename
    except Exception as e:
        print(f"  Download error: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Fetch Wikimedia stock photos for species without reference photos")
    parser.add_argument("--dry-run", action="store_true", help="Preview what would happen")
    parser.add_argument("--species", type=str, help="Process a single species by farmos_name")
    parser.add_argument("--limit", type=int, default=0, help="Max species to process (0=unlimited)")
    args = parser.parse_args()

    # Connect to farmOS
    farmos = FarmOSClient(
        url=os.environ["FARMOS_URL"],
        client_id=os.environ.get("FARMOS_CLIENT_ID", "farm"),
        username=os.environ["FARMOS_USERNAME"],
        password=os.environ["FARMOS_PASSWORD"],
    )
    farmos.connect()

    # Fetch all plant types
    print("Fetching plant types from farmOS...")
    all_types = farmos.get_all_plant_types_cached()
    print(f"Found {len(all_types)} plant types")

    # Build list of species needing photos
    needs_photo = []
    for pt in all_types:
        name = pt.get("attributes", {}).get("name", "")
        desc = pt.get("attributes", {}).get("description", {})
        desc_text = desc.get("value", "") if isinstance(desc, dict) else str(desc or "")
        meta = parse_plant_type_metadata(desc_text)
        botanical = meta.get("botanical_name", "")

        # Check if already has a photo
        image_rel = pt.get("relationships", {}).get("image", {}).get("data")
        has_photo = image_rel is not None and image_rel != [] and image_rel != {}

        if args.species:
            if name != args.species:
                continue
        if has_photo:
            continue
        if not botanical:
            continue

        needs_photo.append({
            "name": name,
            "botanical": botanical,
            "uuid": pt.get("id"),
        })

    if args.limit > 0:
        needs_photo = needs_photo[:args.limit]

    print(f"\n{len(needs_photo)} species need stock photos")
    if not needs_photo:
        print("Nothing to do.")
        return

    # Process
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    stats = {
        "processed": 0,
        "uploaded": 0,
        "no_image_found": 0,
        "errors": 0,
        "skipped_dry_run": 0,
    }

    for sp in needs_photo:
        stats["processed"] += 1
        print(f"\n[{stats['processed']}/{len(needs_photo)}] {sp['name']} ({sp['botanical']})")

        result = fetch_wikimedia_image(sp["botanical"], session)
        time.sleep(RATE_LIMIT_SECONDS)

        if not result:
            # Try genus-only search
            genus = sp["botanical"].split()[0] if " " in sp["botanical"] else sp["botanical"]
            if genus != sp["botanical"]:
                print(f"  Trying genus: {genus}")
                result = fetch_wikimedia_image(genus, session)
                time.sleep(RATE_LIMIT_SECONDS)

        if not result:
            print(f"  No image found on Wikimedia")
            stats["no_image_found"] += 1
            continue

        image_bytes, filename = result
        print(f"  Found: {filename} ({len(image_bytes)} bytes)")

        if args.dry_run:
            print(f"  [DRY RUN] Would upload to farmOS taxonomy_term/{sp['uuid']}")
            stats["skipped_dry_run"] += 1
            continue

        # Upload to farmOS
        try:
            stamp = build_stamp(
                initiator="wikimedia_stock_batch",
                role="system",
                channel="automated",
                executor="wikimedia_api",
                action="created",
                target="plant_type",
                related_entities=[sp["name"]],
            )
            # Note: the stamp goes into the upload but farmOS image fields
            # don't have a notes field — the stamp is for our tracking
            farmos.upload_file(
                entity_type="taxonomy_term/plant_type",
                entity_id=sp["uuid"],
                field_name="image",
                filename=filename,
                binary_data=image_bytes,
                mime_type="image/jpeg",
            )
            print(f"  Uploaded to farmOS")
            stats["uploaded"] += 1
        except Exception as e:
            print(f"  Upload error: {e}")
            stats["errors"] += 1

    # Summary
    print(f"\n{'='*50}")
    print(f"Wikimedia Stock Photo Batch — Results")
    print(f"{'='*50}")
    print(f"Species processed:    {stats['processed']}")
    print(f"Photos uploaded:      {stats['uploaded']}")
    print(f"No image found:       {stats['no_image_found']}")
    print(f"Errors:               {stats['errors']}")
    if args.dry_run:
        print(f"Skipped (dry run):    {stats['skipped_dry_run']}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
