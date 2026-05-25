"""One-off: promote the curated Walnut (Placentia) Drive photo to the
plant_type reference image.

Source: Agnes's Drive folder
https://drive.google.com/drive/folders/1pjOpy2pMtCp2Fn6MfXsL6DyFnzbf9TiB
Two near-identical exposures; we use the larger (less compressed) one.

Run scripts/promote_davidson_walnut_photos_2026_05_25.py first — that one
attached the on-log photos to the asset. This script then fills in the
species-wide reference photo so QR pages have something to show for
Walnut (Placentia), which had no stock reference photo at all.

Pre-req: download both candidates to /tmp/walnut_drive/ via
  curl -sL "https://drive.google.com/uc?export=download&id=FILE_ID" -o walnut.jpg

Safe to re-run: upload is idempotent enough (creates a new file entity
each time, but the plant_type/image relationship is to-many so duplicates
just stack — the most recent is shown first).
"""
from __future__ import annotations

import sys
from pathlib import Path

MCP = Path(__file__).resolve().parent.parent / "mcp-server"
sys.path.insert(0, str(MCP))

from dotenv import load_dotenv  # noqa: E402
from farmos_client import FarmOSClient  # noqa: E402

load_dotenv(Path("/Users/agnes/Repos/FireflyCorner/.env"))

SPECIES = "Walnut (Placentia)"
PHOTO_PATH = Path("/tmp/walnut_drive/walnut_b.jpg")  # larger of the two


def main() -> int:
    c = FarmOSClient()
    c.connect()

    if not PHOTO_PATH.exists():
        print(f"ERROR: {PHOTO_PATH} not found. Download Drive photo first.")
        return 2

    binary = PHOTO_PATH.read_bytes()
    print(f"Loaded {PHOTO_PATH.name}: {len(binary):,} bytes")

    # Find Walnut (Placentia) plant_type term
    r = c.session.get(
        f"{c.hostname}/api/taxonomy_term/plant_type?filter[name]={SPECIES}",
        timeout=30,
    )
    r.raise_for_status()
    matches = r.json().get("data", [])
    if not matches:
        print(f"ERROR: no plant_type named {SPECIES!r}")
        return 2

    pt = matches[0]
    pt_id = pt["id"]
    cur_imgs = pt["relationships"].get("image", {}).get("data") or []
    print(f"plant_type {SPECIES}: id={pt_id} (current images: {len(cur_imgs)})")

    # Upload binary as plant_type image
    new_fid = c.upload_file(
        entity_type=f"taxonomy_term/plant_type",
        entity_id=pt_id,
        field_name="image",
        filename="walnut-placentia-firefly-2026-04.jpg",
        binary_data=binary,
        mime_type="image/jpeg",
    )
    if not new_fid:
        print("FAILED: upload returned no file id")
        return 2

    print(f"PATCHED ✓ plant_type {pt_id} now has image file {new_fid}")
    print("\nDone. Run scripts/export_farmos.py + scripts/generate_site.py to refresh QR pages.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
