#!/usr/bin/env python3
"""Re-attach Leah's 2026-04-14 field-walk photos to their matching farmOS logs.

Background
==========
Leah's April 14 submissions imported into farmOS successfully, but the
photos that came with them got cross-contaminated across the 15 logs in
the same day+section Drive folders (the bug fixed by ADR 0005 on April
15). The cleanup detached all 114 file entities, leaving logs without
any photos.

Agnes has since downloaded Leah's original Drive photos, manually verified
each one against PlantNet on desktop, and renamed the files with a
species tag suffix (``..._parsley.jpg`` etc.). For P2R5.29-38, this
script used PlantNet to verify each photo (April 18 session).

This script walks a hardcoded MAPPING of (farmOS log ID, claimed species,
photo paths) and:

1. Uploads each photo to the target log's ``image`` field.
2. For each distinct species, runs PlantNet on the first photo; if it
   matches the claimed species, promotes the photo as the plant_type
   reference photo (ADR 0001 latest-wins semantics).

Ambiguity handling follows the April 18 decisions:
- P2R5.29-38 obs 06:21 Papaya (count 4→4): Leah submitted 2 photos, both
  identified by PlantNet as Okra (97.9% and 85.3%). Per Agnes's decision
  these attach to the current Okra log (c1aef2b5…), not the Papaya log.
- P2R5.29-38 obs 06:19 Papaya (count 4→3): the original log for this
  submission was rejected during review. The photo is genuinely Papaya
  per PlantNet, so attaches to the surviving 06:21 Papaya log (6054f8b3…).

Usage
-----
    python scripts/attach_leah_photos.py --dry-run
    python scripts/attach_leah_photos.py
"""

from __future__ import annotations

import argparse
import io
import mimetypes
import os
import sys
from pathlib import Path

import requests
from PIL import Image

# Make the mcp-server clients importable without installing them.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "mcp-server"))

from dotenv import load_dotenv  # noqa: E402

from farmos_client import FarmOSClient  # noqa: E402
from plantnet_verify import build_botanical_lookup  # noqa: E402


# ── PlantNet verification with browser-style Origin header ──
# plantnet_verify.py in the MCP server does not send an Origin header,
# which means it only works from IPs on the PlantNet allowlist. Railway
# happens to be allowlisted, but this script runs locally. Sending the
# Origin header that matches one of the authorised domains is the
# portable approach.
_PLANTNET_URL = "https://my-api.plantnet.org/v2/identify/all"
_PLANTNET_ORIGIN = "https://agnesfa.github.io"


def _resize_for_plantnet(image_bytes: bytes, max_dim: int = 1200) -> bytes:
    img = Image.open(io.BytesIO(image_bytes))
    img.thumbnail((max_dim, max_dim))
    buf = io.BytesIO()
    if img.mode != "RGB":
        img = img.convert("RGB")
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _plantnet_verify(
    image_bytes: bytes,
    claimed_species: str,
    botanical_lookup: dict,
    api_key: str,
) -> dict:
    """Mirror of plantnet_verify.verify_species_photo, but with Origin header."""
    # Expected botanical name from the farm taxonomy (reverse lookup shipped
    # as the "__reverse__" key inside build_botanical_lookup's result).
    reverse = botanical_lookup.get("__reverse__", {})
    expected = (reverse.get(claimed_species) or "").lower()
    if not expected:
        return {"verified": False, "reason": "no_botanical_name"}

    resized = _resize_for_plantnet(image_bytes)
    try:
        resp = requests.post(
            f"{_PLANTNET_URL}?api-key={api_key}&lang=en&nb-results=3",
            files={"images": ("photo.jpg", resized, "image/jpeg")},
            data={"organs": "auto"},
            headers={"Origin": _PLANTNET_ORIGIN},
            timeout=30,
        )
        if not resp.ok:
            return {"verified": False, "reason": f"api_http_{resp.status_code}"}
        payload = resp.json()
    except Exception as e:
        return {"verified": False, "reason": f"api_error: {e}"}

    results = payload.get("results") or []
    if not results:
        return {"verified": False, "reason": "no_results"}

    # Expected genus is the first word of the botanical name
    expected_genus = expected.split()[0].lower() if expected else ""
    for r in results[:3]:
        sci = r.get("species", {}).get("scientificNameWithoutAuthor", "").lower()
        score = r.get("score", 0)
        if expected and sci.startswith(expected):
            return {
                "verified": True,
                "reason": f"exact:{sci}@{round(score*100,1)}%",
            }
        if expected_genus and sci.startswith(expected_genus + " "):
            return {
                "verified": True,
                "reason": f"genus:{sci}@{round(score*100,1)}%",
            }
    top = results[0].get("species", {}).get("scientificNameWithoutAuthor", "?")
    top_score = results[0].get("score", 0)
    return {
        "verified": False,
        "reason": f"top_was:{top}@{round(top_score*100,1)}%",
    }


PHOTO_BASE = Path.home() / "Downloads" / "2026-04-14"


MAPPING: list[dict] = [
    # ── P2R5.0-8 (Agnes's manual PlantNet-desktop verification) ──
    {
        "section": "P2R5.0-8",
        "species": "Basil - Perennial (Thai)",
        "log_id": "8a39b87c-0d4c-483b-8673-6a489e6b177e",
        "photos": [
            "P2R5.0-8/P2R5.0-8_plant_001_sweet-basil.jpg",
            "P2R5.0-8/P2R5.0-8_plant_002_sweet-basil.jpg",
        ],
        "plantnet_matches_species": False,  # Thai perennial vs sweet basil — PlantNet confuses them
    },
    {
        "section": "P2R5.0-8",
        "species": "Sweet Potato",
        "log_id": "70968d0a-0d56-47b3-8964-26c9d89b1bba",
        "photos": ["P2R5.0-8/P2R5.0-8_plant_001_unknown.jpg"],
        "plantnet_matches_species": False,  # PlantNet could not ID
    },
    {
        "section": "P2R5.0-8",
        "species": "Parsley (Italian)",
        "log_id": "1c3d67f2-8a79-421b-bab6-fc9ae0b793f4",
        "photos": ["P2R5.0-8/P2R5.0-8_plant_001_parsley.jpg"],
        "plantnet_matches_species": True,
    },
    {
        "section": "P2R5.0-8",
        "species": "Wattle - Cootamundra (Baileyana)",
        "log_id": "a1f8ef71-c26e-464b-8690-e7c28562ac1e",
        "photos": ["P2R5.0-8/P2R5.0-8_plant_001_acacia.jpg"],
        "plantnet_matches_species": True,
    },
    {
        "section": "P2R5.0-8",
        "species": "Mulberry (White)",
        "log_id": "71ff17b7-81cf-44b2-b8db-bacd2711b686",
        "photos": ["P2R5.0-8/P2R5.0-8_plant_001_Mulberry.jpg"],
        "plantnet_matches_species": True,
    },
    {
        "section": "P2R5.0-8",
        "species": "Sunflower",
        "log_id": "f1c02440-1d61-4630-9148-a8fb7759c52c",
        "photos": [
            "P2R5.0-8/P2R5.0-8_plant_001_sunflower.jpg",
            "P2R5.0-8/P2R5.0-8_plant_002_sunflower.jpg",
            "P2R5.0-8/P2R5.0-8_plant_003_sunflower.jpg",
        ],
        "plantnet_matches_species": True,
    },
    {
        "section": "P2R5.0-8",
        "species": "Papaya",
        "log_id": "87322054-24b7-4c84-9125-5325a5a2e3ea",
        "photos": [
            "P2R5.0-8/P2R5.0-8_plant_001_papaya.jpg",
            "P2R5.0-8/P2R5.0-8_plant_002_papaya.jpg",
        ],
        "plantnet_matches_species": True,
    },
    {
        "section": "P2R5.0-8",
        "species": "Pumpkin",
        "log_id": "bab83082-8234-475b-ba9c-9293aca4e3d6",
        "photos": ["P2R5.0-8/P2R5.0-8_plant_001_multi-plant.jpg"],
        "plantnet_matches_species": False,  # multi-plant frame, not species-specific
    },
    # ── P2R5.29-38 (April 18 PlantNet server-side verification) ──
    {
        "section": "P2R5.29-38",
        "species": "Papaya",
        "log_id": "6054f8b3-e714-404b-a096-0e7a6669c3db",
        # The 06:19 submission (plant_001(4).jpg) was PlantNet-verified Papaya.
        # Its original log was rejected (count 4→3 dropped), so we attach it
        # to the surviving 06:21 Papaya log.
        "photos": ["P2R5.29-38/P2R5.29-38_plant_001(4).jpg"],
        "plantnet_matches_species": True,
    },
    {
        "section": "P2R5.29-38",
        "species": "Okra",
        # 2026-04-05 Maverick observation, count 11, pending James verification.
        # These 2 photos were originally in Leah's 06:21 "Papaya" submission
        # but PlantNet identified both as Okra (97.9% and 85.3%).
        "log_id": "c1aef2b5-fa3a-4d9d-93a9-4261c6f75e10",
        "photos": [
            "P2R5.29-38/P2R5.29-38_plant_001(3).jpg",
            "P2R5.29-38/P2R5.29-38_plant_002.jpg",
        ],
        "plantnet_matches_species": True,
    },
    {
        "section": "P2R5.29-38",
        "species": "Wattle - Cootamundra (Baileyana)",
        "log_id": "0b121911-b717-4728-8975-7d8d8a501196",
        "photos": ["P2R5.29-38/P2R5.29-38_plant_001(2).jpg"],
        # Low-confidence Mimosa match. Same legume clade but not exact
        # species. Attach, don't promote.
        "plantnet_matches_species": False,
    },
    {
        "section": "P2R5.29-38",
        "species": "Coriander",
        "log_id": "fc5f01ed-1dc7-4a6e-8eed-ca2996d396c2",
        "photos": ["P2R5.29-38/P2R5.29-38_plant_001(1).jpg"],
        # PlantNet top match was Conopodium majus (same Apiaceae family,
        # visually similar) with Coriander as #2. Young plant — no
        # reference promotion.
        "plantnet_matches_species": False,
    },
    {
        "section": "P2R5.29-38",
        "species": "Jacaranda",
        "log_id": "3d7da012-400f-4057-ba96-0833505c0c6f",
        "photos": ["P2R5.29-38/P2R5.29-38_plant_001.jpg"],
        # Young plant (~30 cm), PlantNet top match was Yellow Bird of
        # Paradise (also legume, feathery foliage). Jacaranda in top 3
        # but low confidence. Attach, don't promote.
        "plantnet_matches_species": False,
    },
]


def _mime_for(path: Path) -> str:
    mt, _ = mimetypes.guess_type(path.name)
    return mt or "image/jpeg"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the plan without uploading anything",
    )
    parser.add_argument(
        "--skip-reference",
        action="store_true",
        help="Attach to logs but skip plant_type reference-photo promotion",
    )
    parser.add_argument(
        "--references-only",
        action="store_true",
        help="Skip attach (already done) and only promote reference photos",
    )
    args = parser.parse_args()

    load_dotenv()

    # Pre-flight: every photo in the mapping must exist.
    missing = []
    for entry in MAPPING:
        for rel in entry["photos"]:
            p = PHOTO_BASE / rel
            if not p.exists():
                missing.append(str(p))
    if missing:
        print("ERROR: missing photo files:", file=sys.stderr)
        for m in missing:
            print(f"  {m}", file=sys.stderr)
        return 1

    # Totals for the plan
    total_photos = sum(len(e["photos"]) for e in MAPPING)
    ref_candidates = sum(1 for e in MAPPING if e["plantnet_matches_species"])
    print(
        f"Plan: attach {total_photos} photos across {len(MAPPING)} logs "
        f"(reference-photo promotion attempted for {ref_candidates} species)\n"
    )
    for e in MAPPING:
        tag = "→ promote" if e["plantnet_matches_species"] else "  attach only"
        print(
            f"  [{e['section']}] {e['species']:<35} "
            f"log {e['log_id'][:8]}…  {len(e['photos'])} photo(s)  {tag}"
        )

    if args.dry_run:
        print("\n(dry-run — no changes made)")
        return 0

    farmos = FarmOSClient()
    farmos.connect()
    botanical_lookup = build_botanical_lookup()
    api_key = os.environ.get("PLANTNET_API_KEY", "").strip()

    attached = 0
    attach_errors = 0
    references_set = 0
    references_rejected = 0
    references_skipped = 0
    plantnet_calls = 0

    if args.references_only:
        print("\n--- References-only mode (skipping attach) ---")
    else:
        print("\n--- Attaching photos ---")

    for entry in MAPPING:
        log_id = entry["log_id"]
        species = entry["species"]
        print(f"\n[{entry['section']}] {species} → log {log_id[:8]}…")

        uploaded_files: list[tuple[Path, bytes, str]] = []
        for rel in entry["photos"]:
            p = PHOTO_BASE / rel
            binary = p.read_bytes()
            mime = _mime_for(p)
            if not args.references_only:
                try:
                    farmos.upload_file(
                        entity_type="log/observation",
                        entity_id=log_id,
                        field_name="image",
                        filename=p.name,
                        binary_data=binary,
                        mime_type=mime,
                    )
                    attached += 1
                    print(f"    ✓ attached {p.name}")
                except Exception as e:
                    attach_errors += 1
                    print(f"    ! attach failed {p.name}: {e}")
            uploaded_files.append((p, binary, mime))

        if args.skip_reference or not entry["plantnet_matches_species"]:
            if uploaded_files and not args.skip_reference:
                references_skipped += 1
                print(f"    · reference promotion skipped (species not PlantNet-matched)")
            continue

        uuid = farmos.get_plant_type_uuid(species)
        if not uuid:
            print(f"    ! no plant_type UUID for {species}; cannot promote reference")
            continue

        promoted = False
        for path, binary, mime in uploaded_files:
            plantnet_calls += 1
            result = _plantnet_verify(binary, species, botanical_lookup, api_key)
            if result.get("verified"):
                try:
                    farmos.upload_file(
                        entity_type="taxonomy_term/plant_type",
                        entity_id=uuid,
                        field_name="image",
                        filename=path.name,
                        binary_data=binary,
                        mime_type=mime,
                    )
                    references_set += 1
                    print(f"    → reference photo set for {species} ({result.get('reason')})")
                    promoted = True
                    break
                except Exception as e:
                    print(f"    ! reference upload failed for {species}: {e}")
                    break
            else:
                references_rejected += 1
                print(f"    ✗ reference rejected for {path.name}: {result.get('reason')}")
        if not promoted and uploaded_files:
            print(f"    · no photo verified by PlantNet for {species}")

    print("\n" + "─" * 60)
    if not args.references_only:
        print(f"Photos attached:              {attached}")
        print(f"Attach errors:                {attach_errors}")
    print(f"Reference photos set:         {references_set}")
    print(f"Reference photos rejected:    {references_rejected}")
    print(f"Reference promotion skipped:  {references_skipped}")
    print(f"PlantNet API calls:           {plantnet_calls}")
    return 0 if attach_errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
