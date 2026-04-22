"""One-off: sweep all plant_types and replace stale reference photos with
tier-3 field photos from recent observation logs.

Context: 2026-04-22 audit found that tonight's import pipeline reported
`species_reference_photos_updated: 1` for at least 8 species (probably all
~15 that claimed promotion), yet the plant_type.image relationship was NOT
actually replaced. Silent write bug in photo-pipeline.ts. Coriander fixed
manually; this sweep does the rest.

Strategy:
1. Build a map species → best tier-3 file_id by walking recent observation
   logs (Apr 20 onwards) and their image relationships. Tier-3 = filename
   starts with 8-char submission_id prefix then underscore.
2. For each plant_type, fetch current image filename.
   - If missing OR old-format (no UUID prefix): PATCH to the tier-3 file.
   - If already tier-3: leave alone.
3. Report every change made.

Safe to re-run: patches are idempotent (PATCH with same data = no-op).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

MCP = Path(__file__).resolve().parent.parent / "mcp-server"
sys.path.insert(0, str(MCP))

from dotenv import load_dotenv  # noqa: E402
from farmos_client import FarmOSClient  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent.parent.parent.parent / ".env")
if not __import__("os").getenv("FARMOS_URL"):
    load_dotenv("/Users/agnes/Repos/FireflyCorner/.env")

TIER3_RE = re.compile(r"^[0-9a-f]{8}_")  # 8-char hex prefix + underscore


def filename_tier(fn: str) -> int:
    """0 = stock/old, 3 = tier-3 (submission_id prefix + _plant_)."""
    if not fn:
        return 0
    if TIER3_RE.match(fn):
        if "_plant_" in fn:
            return 3
        if "_section_" in fn:
            return 1  # multi-plant section photo — never promote
        return 2
    return 0


def main() -> int:
    c = FarmOSClient()
    c.connect()

    # Step 1: build species → best tier-3 file_id via recent observation logs
    print("Step 1: scanning recent observation logs for tier-3 photos...")
    # Fetch observation logs since 2026-04-18 (covers tonight + recovery runs)
    since = "1713398400"  # 2026-04-18 00:00 UTC unix
    page = 0
    species_best: dict[str, tuple[int, str, str]] = {}  # species → (timestamp, filename, file_id)
    while True:
        url = (
            f"{c.hostname}/api/log/observation"
            f"?filter[timestamp][value]={since}&filter[timestamp][operator]=>"
            f"&include=image&page[limit]=50&page[offset]={page*50}"
            f"&sort=-timestamp"
        )
        r = c.session.get(url, timeout=60)
        r.raise_for_status()
        data = r.json()
        logs = data.get("data", [])
        included = {f["id"]: f for f in data.get("included", []) if f["type"].startswith("file--")}
        if not logs:
            break
        for log in logs:
            name = log["attributes"].get("name", "")
            # Extract species from log name (pattern: "Observation {section} — {species} — {date}" or "Inventory {section} — {species}")
            m = re.search(r"— (.+?) —", name) or re.search(r"— (.+)$", name)
            if not m:
                continue
            species = m.group(1).strip()
            img_ids = [e["id"] for e in (log["relationships"].get("image", {}).get("data") or [])]
            # timestamp may be ISO string or unix seconds
            ts_raw = log["attributes"].get("timestamp", 0) or 0
            if isinstance(ts_raw, str):
                from datetime import datetime
                ts = int(datetime.fromisoformat(ts_raw.replace("Z", "+00:00")).timestamp())
            else:
                ts = int(ts_raw)
            for fid in img_ids:
                f = included.get(fid)
                if not f:
                    continue
                fn = f["attributes"].get("filename", "")
                tier = filename_tier(fn)
                if tier < 2:
                    continue  # only tier-2 or tier-3 qualify as reference
                prev = species_best.get(species)
                if prev is None or ts > prev[0] or (ts == prev[0] and tier == 3 and prev[1] != 3):
                    species_best[species] = (ts, fn, fid)
        page += 1
        if page > 10:  # safety
            break

    print(f"  found {len(species_best)} species with recent tier-2+ field photos")

    # Step 2: for each species, fetch current plant_type image + compare
    print("\nStep 2: patching plant_types where current image is stale or old-format...")
    patched: list[tuple[str, str, str]] = []
    skipped: list[tuple[str, str, str]] = []
    for species, (ts, new_fn, new_fid) in sorted(species_best.items()):
        # Find plant_type by name
        r = c.session.get(
            f"{c.hostname}/api/taxonomy_term/plant_type?filter[name]={species}",
            timeout=30,
        )
        if r.status_code != 200:
            print(f"  {species}: ERR_HTTP_{r.status_code} looking up plant_type")
            continue
        matches = r.json().get("data", [])
        if not matches:
            print(f"  {species}: NO plant_type found (name mismatch?)")
            continue
        pt_id = matches[0]["id"]
        img_rel = matches[0]["relationships"].get("image", {}).get("data") or []
        current_fid = img_rel[0]["id"] if img_rel else None

        if current_fid == new_fid:
            skipped.append((species, new_fn, "already_tier3"))
            continue

        # Fetch current filename for reporting
        current_fn = None
        if current_fid:
            r2 = c.session.get(f"{c.hostname}/api/file/file/{current_fid}", timeout=20)
            if r2.status_code == 200:
                current_fn = r2.json().get("data", {}).get("attributes", {}).get("filename")

        current_tier = filename_tier(current_fn or "")
        new_tier = filename_tier(new_fn)
        if current_tier >= new_tier and current_tier >= 2:
            skipped.append((species, new_fn, f"current_already_tier{current_tier}_{current_fn}"))
            continue

        # PATCH to the new file
        patch_url = f"{c.hostname}/api/taxonomy_term/plant_type/{pt_id}/relationships/image"
        patch_resp = c.session.patch(
            patch_url,
            headers={"Content-Type": "application/vnd.api+json", "Accept": "application/vnd.api+json"},
            data=json.dumps({"data": [{"type": "file--file", "id": new_fid}]}),
            timeout=30,
        )
        if patch_resp.status_code in (204, 200):
            patched.append((species, current_fn or "(none)", new_fn))
            print(f"  PATCHED {species}: {current_fn or '(none)'} -> {new_fn}")
        else:
            print(f"  FAILED {species}: HTTP {patch_resp.status_code}")

    # Step 3: report
    print(f"\n=== SUMMARY ===")
    print(f"  Species with recent tier-2+ photos: {len(species_best)}")
    print(f"  Patched: {len(patched)}")
    print(f"  Skipped (already correct or better): {len(skipped)}")
    print(f"\nPatched detail:")
    for s, old, new in patched:
        print(f"  {s:35} {old[:40]:40} -> {new}")

    out = Path(__file__).parent / "fix_species_reference_photos_2026_04_22.results.json"
    out.write_text(json.dumps({
        "patched": [{"species": s, "old": old, "new": new} for s, old, new in patched],
        "skipped": [{"species": s, "new": new, "reason": r} for s, new, r in skipped],
    }, indent=2))
    print(f"\nDetails: {out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
