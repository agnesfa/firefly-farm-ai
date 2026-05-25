"""One-off: promote Davidson Plum + Walnut field photos.

Davidson Plum (P2R2.38-46): observation dec49d60 (Agnes 2026-05-17, mode=quick,
note "Taking a photo of the Davidson plum") carries a field photo that should
replace the stock reference photo. Promote to plant_type + asset.

Walnut Placentia (P2R5.66-77): asset notes mention "Photo evidence on section
activity log of 2026-04-25 (submission 133b8e16)". Find that activity log,
pull its image, attach to the Walnut asset.

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


DAVIDSON_PLUM = {
    "species": "Davidson Plum",
    "log_id": "dec49d60-cea2-4e88-a5c4-b40b8aa5a346",
    "log_type": "observation",
    "asset_id": "736dcaf5-55b8-494d-805e-d5d2973ef361",
    "promote_to_plant_type": True,
    "promote_to_asset": True,
}

WALNUT = {
    "species": "Walnut (Placentia)",
    "submission": "133b8e16",
    "asset_id": "06bf9f2b-e59f-469d-b895-7200167092e2",
    "promote_to_plant_type": False,  # Drive photo will fill this separately
    "promote_to_asset": True,
}


def get_log_image_fids(client: FarmOSClient, log_type: str, log_id: str) -> list[str]:
    url = f"{client.hostname}/api/log/{log_type}/{log_id}?include=image"
    r = client.session.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()
    img_rel = data["data"]["relationships"].get("image", {}).get("data") or []
    return [x["id"] for x in img_rel]


def find_log_by_submission(client: FarmOSClient, submission_id: str) -> tuple[str, str] | None:
    """Find first log whose notes contain submission=<prefix>. Returns (type, id)."""
    for log_type in ("activity", "observation"):
        url = (
            f"{client.hostname}/api/log/{log_type}"
            f"?filter[notes.value][operator]=CONTAINS"
            f"&filter[notes.value][value]={submission_id}"
            f"&include=image"
        )
        r = client.session.get(url, timeout=30)
        r.raise_for_status()
        data = r.json().get("data", [])
        # Prefer logs that actually have an image attached
        with_img = [d for d in data if d.get("relationships", {}).get("image", {}).get("data")]
        candidates = with_img or data
        if candidates:
            d = candidates[0]
            return log_type, d["id"]
    return None


def get_plant_type(client: FarmOSClient, name: str) -> dict | None:
    r = client.session.get(
        f"{client.hostname}/api/taxonomy_term/plant_type?filter[name]={name}",
        timeout=30,
    )
    r.raise_for_status()
    matches = r.json().get("data", [])
    return matches[0] if matches else None


def get_asset(client: FarmOSClient, asset_id: str) -> dict | None:
    r = client.session.get(
        f"{client.hostname}/api/asset/plant/{asset_id}?include=image", timeout=30
    )
    if r.status_code != 200:
        return None
    return r.json().get("data")


def patch_image_rel(
    client: FarmOSClient, base: str, file_ids: list[str]
) -> bool:
    """PATCH a JSON:API to-many image relationship with the given file IDs."""
    payload = {"data": [{"type": "file--file", "id": fid} for fid in file_ids]}
    r = client.session.patch(
        base,
        headers={
            "Content-Type": "application/vnd.api+json",
            "Accept": "application/vnd.api+json",
        },
        data=json.dumps(payload),
        timeout=30,
    )
    if r.status_code not in (200, 204):
        print(f"  HTTP {r.status_code}: {r.text[:200]}")
        return False
    return True


def promote(client: FarmOSClient, spec: dict, fids: list[str]) -> int:
    species = spec["species"]
    asset_id = spec["asset_id"]
    rc = 0
    if spec["promote_to_plant_type"]:
        pt = get_plant_type(client, species)
        if not pt:
            print(f"  SKIP plant_type: no taxonomy term named {species!r}")
        else:
            cur = pt["relationships"].get("image", {}).get("data") or []
            cur_ids = [x["id"] for x in cur]
            if cur_ids == fids:
                print("  plant_type: already set")
            else:
                ok = patch_image_rel(
                    client,
                    f"{client.hostname}/api/taxonomy_term/plant_type/{pt['id']}/relationships/image",
                    fids,
                )
                print(f"  plant_type {pt['id']}: {'PATCHED' if ok else 'FAILED'} → {fids}")
                rc = 0 if ok else 2

    if spec["promote_to_asset"]:
        asset = get_asset(client, asset_id)
        if not asset:
            print(f"  SKIP asset: cannot fetch {asset_id}")
            return rc or 2
        cur = asset["relationships"].get("image", {}).get("data") or []
        cur_ids = [x["id"] for x in cur]
        if cur_ids == fids:
            print("  asset: already set")
        else:
            ok = patch_image_rel(
                client,
                f"{client.hostname}/api/asset/plant/{asset_id}/relationships/image",
                fids,
            )
            print(f"  asset {asset_id}: {'PATCHED' if ok else 'FAILED'} → {fids}")
            rc = 0 if ok else 2
    return rc


def main() -> int:
    c = FarmOSClient()
    c.connect()

    rc = 0

    print(f"\n=== {DAVIDSON_PLUM['species']} ===")
    fids = get_log_image_fids(c, DAVIDSON_PLUM["log_type"], DAVIDSON_PLUM["log_id"])
    if not fids:
        print(f"  SKIP: log {DAVIDSON_PLUM['log_id']} has no images")
    else:
        print(f"  log images: {fids}")
        rc |= promote(c, DAVIDSON_PLUM, fids)

    print(f"\n=== {WALNUT['species']} ===")
    found = find_log_by_submission(c, WALNUT["submission"])
    if not found:
        print(f"  SKIP: no log found with submission={WALNUT['submission']!r}")
    else:
        log_type, log_id = found
        print(f"  matched log: {log_type}/{log_id}")
        fids = get_log_image_fids(c, log_type, log_id)
        if not fids:
            print(f"  SKIP: matched log has no images")
        else:
            print(f"  log images: {fids}")
            rc |= promote(c, WALNUT, fids)

    print("\nDone. Run scripts/export_farmos.py + scripts/generate_site.py to refresh QR pages.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
