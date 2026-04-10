"""PlantNet species verification for the photo pipeline.

Calls the PlantNet Identify API to check whether a photo actually
depicts the claimed species before attaching it to a farmOS log or
setting it as a species reference photo.

Usage:
    lookup = build_botanical_lookup("knowledge/plant_types.csv")
    result = verify_species_photo(image_bytes, "Pigeon Pea", lookup)
    if result["verified"]:
        # proceed with upload
    else:
        # skip — photo doesn't match claimed species
"""

import csv
import os
import logging
from io import BytesIO
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Module-level call counter for quota awareness (500/day free tier).
_plantnet_calls = 0

PLANTNET_URL = "https://my-api.plantnet.org/v2/identify/all"
THUMB_MAX_DIM = 800  # PlantNet's recommended max for low-bandwidth
CONFIDENCE_THRESHOLD = 0.30


def build_botanical_lookup(csv_path: str = None) -> dict[str, str]:
    """Build {botanical_name_lower: farmos_name} from plant_types.csv.

    Also builds a reverse {farmos_name: botanical_name} for looking up
    the expected botanical name of a claimed species.
    """
    if csv_path is None:
        csv_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "knowledge", "plant_types.csv",
        )

    forward: dict[str, str] = {}   # botanical → farmos_name
    reverse: dict[str, str] = {}   # farmos_name → botanical

    if not os.path.exists(csv_path):
        logger.warning("plant_types.csv not found at %s", csv_path)
        return {}

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            farmos_name = (row.get("farmos_name") or "").strip()
            botanical = (row.get("botanical_name") or "").strip()
            if farmos_name and botanical:
                forward[botanical.lower()] = farmos_name
                reverse[farmos_name] = botanical.lower()

    # Store reverse lookup as an attribute so callers can access it.
    forward["__reverse__"] = reverse  # type: ignore[assignment]
    return forward


def _get_expected_botanical(claimed_species: str, lookup: dict) -> Optional[str]:
    """Get the expected botanical name for a farmos_name."""
    reverse = lookup.get("__reverse__", {})
    return reverse.get(claimed_species)


def _botanical_match(plantnet_name: str, expected: str) -> bool:
    """Bidirectional prefix match (same as observe.js findFarmosNameByBotanical).

    Examples:
        "Cajanus cajan" matches "Cajanus cajan" (exact)
        "Cajanus cajan" matches "Cajanus" (prefix)
        "Cajanus" matches "Cajanus cajan" (prefix)
    """
    a = plantnet_name.lower().strip()
    b = expected.lower().strip()
    return a == b or a.startswith(b) or b.startswith(a)


def _resize_for_plantnet(image_bytes: bytes) -> bytes:
    """Resize image to THUMB_MAX_DIM for PlantNet. Returns original on failure."""
    try:
        from PIL import Image
        img = Image.open(BytesIO(image_bytes))
        img = img.convert("RGB")
        img.thumbnail((THUMB_MAX_DIM, THUMB_MAX_DIM), Image.LANCZOS)
        buf = BytesIO()
        img.save(buf, "JPEG", quality=80)
        return buf.getvalue()
    except Exception:
        return image_bytes


def verify_species_photo(
    image_bytes: bytes,
    claimed_species: str,
    botanical_lookup: dict,
    api_key: str = None,
) -> dict:
    """Verify a photo matches the claimed species via PlantNet.

    Returns:
        {
            "verified": bool,       # True if photo matches species
            "plantnet_top": str,    # PlantNet's best match (botanical name)
            "confidence": float,    # Score of the matching result (0-1)
            "reason": str,          # Human-readable explanation
        }
    """
    global _plantnet_calls

    if api_key is None:
        api_key = os.environ.get("PLANTNET_API_KEY", "").strip()

    # No API key → can't verify, skip photo (safe default)
    if not api_key:
        return {
            "verified": False,
            "plantnet_top": "",
            "confidence": 0,
            "reason": "no_api_key",
        }

    # No claimed species → can't verify (section comments)
    if not claimed_species:
        return {
            "verified": True,
            "plantnet_top": "",
            "confidence": 0,
            "reason": "no_species_claim",
        }

    # Look up expected botanical name
    expected_botanical = _get_expected_botanical(claimed_species, botanical_lookup)
    if not expected_botanical:
        # Species has no botanical name in taxonomy → can't verify
        return {
            "verified": True,
            "plantnet_top": "",
            "confidence": 0,
            "reason": "no_botanical_name",
        }

    # Resize for API
    resized = _resize_for_plantnet(image_bytes)

    # Call PlantNet
    try:
        _plantnet_calls += 1
        resp = requests.post(
            f"{PLANTNET_URL}?api-key={api_key}&lang=en&nb-results=3",
            files={"images": ("photo.jpg", resized, "image/jpeg")},
            data={"organs": "auto"},
            timeout=15,
        )
        if not resp.ok:
            logger.warning("PlantNet HTTP %d: %s", resp.status_code, resp.text[:200])
            return {
                "verified": False,
                "plantnet_top": "",
                "confidence": 0,
                "reason": f"api_http_{resp.status_code}",
            }

        payload = resp.json()
    except Exception as e:
        logger.warning("PlantNet API error: %s", e)
        return {
            "verified": False,
            "plantnet_top": "",
            "confidence": 0,
            "reason": f"api_error: {e}",
        }

    # Check top-3 results
    results = payload.get("results") or []
    if not results:
        return {
            "verified": False,
            "plantnet_top": "",
            "confidence": 0,
            "reason": "no_plantnet_results",
        }

    top_species = (
        (results[0].get("species") or {}).get("scientificNameWithoutAuthor") or ""
    )
    top_score = results[0].get("score", 0)

    for match in results[:3]:
        species_info = match.get("species") or {}
        botanical = species_info.get("scientificNameWithoutAuthor") or ""
        score = match.get("score", 0)

        if _botanical_match(botanical, expected_botanical) and score >= CONFIDENCE_THRESHOLD:
            return {
                "verified": True,
                "plantnet_top": botanical,
                "confidence": score,
                "reason": f"match ({score:.0%})",
            }

    # No match found
    return {
        "verified": False,
        "plantnet_top": top_species,
        "confidence": top_score,
        "reason": f"mismatch — PlantNet says {top_species} ({top_score:.0%}), expected {expected_botanical}",
    }


def get_call_count() -> int:
    """Return total PlantNet API calls made in this process."""
    return _plantnet_calls
