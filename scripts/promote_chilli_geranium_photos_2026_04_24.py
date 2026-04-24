"""One-off: human-override promotion of Chilli (Jalapeño) + Geranium
reference photos after PlantNet rejected them on 2026-04-23 import.

Agnes reviewed the rejected photos and confirmed they are genuine, good-quality
field photos of the species. PlantNet is not sole authority (see memory
feedback_plantnet_verification_policy.md). This script promotes them to the
plant_type reference image via direct farmOS API PATCH.

Targets:
- Chilli (Jalapeño) <- log 013371a6-75e4-41f4-a3ac-f14d79fc342c (submission 6417e39b, P2R2.28-38)
- Geranium          <- log 3daa9802-f985-4fb1-bea3-611b50eb8acb (submission 7c115be1, P2R2.28-38)

Safe to re-run: idempotent PATCH.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

MCP = Path(__file__).resolve().parent.parent / "mcp-server"
sys.path.insert(0, str(MCP))

from dotenv import load_dotenv  # noqa: E402
from farmos_client import FarmOSClient  # noqa: E402

load_dotenv(Path("/Users/agnes/Repos/FireflyCorner/.env"))

TARGETS = [
    ("Chilli (Jalapeño)", "013371a6-75e4-41f4-a3ac-f14d79fc342c"),
    ("Geranium",          "3daa9802-f985-4fb1-bea3-611b50eb8acb"),
]


def get_log_first_image_fid(client: FarmOSClient, log_id: str) -> tuple[str, str] | None:
    url = f"{client.hostname}/api/log/observation/{log_id}?include=image"
    r = client.session.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()
    img_rel = data["data"]["relationships"].get("image", {}).get("data") or []
    if not img_rel:
        return None
    first_fid = img_rel[0]["id"]
    included = {f["id"]: f for f in data.get("included", []) if f["type"].startswith("file--")}
    fn = included.get(first_fid, {}).get("attributes", {}).get("filename", "")
    return first_fid, fn


def get_plant_type(client: FarmOSClient, name: str) -> dict | None:
    r = client.session.get(
        f"{client.hostname}/api/taxonomy_term/plant_type?filter[name]={name}",
        timeout=30,
    )
    r.raise_for_status()
    matches = r.json().get("data", [])
    return matches[0] if matches else None


def patch_image(client: FarmOSClient, pt_id: str, file_id: str) -> bool:
    patch_url = f"{client.hostname}/api/taxonomy_term/plant_type/{pt_id}/relationships/image"
    r = client.session.patch(
        patch_url,
        headers={
            "Content-Type": "application/vnd.api+json",
            "Accept": "application/vnd.api+json",
        },
        data=json.dumps({"data": [{"type": "file--file", "id": file_id}]}),
        timeout=30,
    )
    return r.status_code in (200, 204)


def main() -> int:
    c = FarmOSClient()
    c.connect()

    for species, log_id in TARGETS:
        print(f"\n--- {species} ---")
        img = get_log_first_image_fid(c, log_id)
        if not img:
            print(f"  SKIP: log {log_id} has no image")
            continue
        new_fid, new_fn = img
        print(f"  log image: {new_fid} ({new_fn})")

        pt = get_plant_type(c, species)
        if not pt:
            print(f"  SKIP: no plant_type named {species!r}")
            continue
        pt_id = pt["id"]
        cur_rel = pt["relationships"].get("image", {}).get("data") or []
        cur_fid = cur_rel[0]["id"] if cur_rel else None
        print(f"  plant_type id: {pt_id}")
        print(f"  current image file_id: {cur_fid}")

        if cur_fid == new_fid:
            print(f"  SKIP: already set to this file")
            continue

        ok = patch_image(c, pt_id, new_fid)
        if ok:
            print(f"  PATCHED ✓  {cur_fid or '(none)'} -> {new_fid}")
        else:
            print(f"  FAILED to patch")
            return 2

    print("\nDone. Remember to run generate_site.py to refresh the cached species photos on QR pages.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
