"""
farmOS API client wrapper for the MCP server.

Uses raw HTTP requests (not farmOS.py) to avoid the pydantic v1 vs v2 conflict.
farmOS.py requires pydantic v1, FastMCP requires pydantic v2.

This client implements OAuth2 password-grant authentication and JSON:API operations
directly with the requests library, replicating the reliable patterns from
scripts/import_fieldsheets.py and scripts/fix_taxonomy.py.
"""

import os
import re
import urllib.parse
from typing import Optional

import requests
from dotenv import load_dotenv


PLANT_UNIT_UUID = "2371b79e-a87b-4152-b6e4-ea6a9ed37fd0"


class FarmOSClient:
    """Direct HTTP client for farmOS JSON:API.

    Replaces farmOS.py to avoid pydantic version conflicts.
    Uses OAuth2 password grant for authentication, then raw HTTP
    for all API operations.
    """

    def __init__(self):
        self.hostname = None
        self.session = None  # requests.Session with auth headers
        self._plant_type_cache = {}   # farmos_name → UUID
        self._section_cache = {}      # section_id → UUID
        self._connected = False

    def connect(self) -> bool:
        """Load config from .env and authenticate with farmOS via OAuth2."""
        load_dotenv()

        self.hostname = os.getenv("FARMOS_URL", "").rstrip("/")
        username = os.getenv("FARMOS_USERNAME")
        password = os.getenv("FARMOS_PASSWORD")
        client_id = os.getenv("FARMOS_CLIENT_ID", "farm")
        scope = os.getenv("FARMOS_SCOPE", "farm_manager")

        missing = []
        if not self.hostname:
            missing.append("FARMOS_URL")
        if not username:
            missing.append("FARMOS_USERNAME")
        if not password:
            missing.append("FARMOS_PASSWORD")

        if missing:
            raise ValueError(f"Missing environment variables: {', '.join(missing)}")

        # OAuth2 password grant
        token_url = f"{self.hostname}/oauth/token"
        token_data = {
            "grant_type": "password",
            "username": username,
            "password": password,
            "client_id": client_id,
            "scope": scope,
        }

        try:
            resp = requests.post(token_url, data=token_data, timeout=30)
            resp.raise_for_status()
            token_info = resp.json()
            access_token = token_info["access_token"]
        except Exception as e:
            raise ConnectionError(f"farmOS OAuth2 authentication failed: {e}")

        # Create authenticated session
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/vnd.api+json",
            "Accept": "application/vnd.api+json",
        })

        self._connected = True
        return True

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ── Low-level HTTP helpers ──────────────────────────────────

    def _get(self, path: str) -> dict:
        """GET request to farmOS API. Returns parsed JSON or raises on error."""
        if not self._connected:
            raise ConnectionError("Not connected to farmOS. Check credentials.")
        url = f"{self.hostname}{path}"
        resp = self.session.get(url, timeout=30)
        if resp.status_code in (401, 403):
            self._connected = False
            raise ConnectionError(
                f"farmOS authentication expired (HTTP {resp.status_code}). "
                "Restart the MCP server to reconnect."
            )
        if resp.status_code != 200:
            raise RuntimeError(f"farmOS API error: HTTP {resp.status_code} for {path}")
        return resp.json()

    def _post(self, path: str, payload: dict) -> dict:
        """POST request to farmOS API. Returns parsed JSON."""
        url = f"{self.hostname}{path}"
        resp = self.session.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _patch(self, path: str, payload: dict) -> dict:
        """PATCH request to farmOS API. Returns parsed JSON."""
        if not self._connected:
            raise ConnectionError("Not connected to farmOS. Check credentials.")
        url = f"{self.hostname}{path}"
        resp = self.session.patch(url, json=payload, timeout=30)
        if resp.status_code in (401, 403):
            self._connected = False
            raise ConnectionError(
                f"farmOS authentication expired (HTTP {resp.status_code}). "
                "Restart the MCP server to reconnect."
            )
        resp.raise_for_status()
        return resp.json()

    # ── Reliable query methods ──────────────────────────────────

    def fetch_by_name(self, api_path: str, name: str) -> list:
        """Per-name API query — reliable, not affected by pagination limits.

        This is the ONLY reliable method for existence checks with 200+ records.

        Args:
            api_path: e.g., "taxonomy_term/plant_type", "asset/plant", "asset/land"
            name: The exact name to search for
        """
        encoded = urllib.parse.quote(name)
        path = f"/api/{api_path}?filter[name]={encoded}&page[limit]=50"
        data = self._get(path)
        return data.get("data", [])

    def fetch_all_paginated(self, api_path: str, filters: Optional[dict] = None,
                            sort: Optional[str] = None, limit: int = 50) -> list:
        """Raw HTTP pagination for complete enumeration.

        Follows links.next to get ALL records, handling the farmOS pagination
        quirk where link URLs include the full hostname.

        Args:
            api_path: e.g., "taxonomy_term/plant_type", "asset/plant"
            filters: Optional filter params, e.g. {"status": "active"}
            sort: Optional sort field, e.g. "-changed" for newest first
            limit: Page size (default 50)
        """
        all_items = []
        seen_ids = set()

        # Build initial URL
        path = f"/api/{api_path}?page[limit]={limit}"
        if filters:
            for key, value in filters.items():
                path += f"&filter[{key}]={urllib.parse.quote(str(value))}"
        if sort:
            path += f"&sort={sort}"

        url = f"{self.hostname}{path}"

        if not self._connected:
            raise ConnectionError("Not connected to farmOS. Check credentials.")

        while url:
            resp = self.session.get(url, timeout=30)
            if resp.status_code in (401, 403):
                self._connected = False
                raise ConnectionError(
                    f"farmOS authentication expired (HTTP {resp.status_code}). "
                    "Restart the MCP server to reconnect."
                )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"farmOS API error: HTTP {resp.status_code} fetching {api_path}"
                )

            data = resp.json()
            items = data.get("data", [])

            for item in items:
                item_id = item.get("id", "")
                if item_id and item_id not in seen_ids:
                    seen_ids.add(item_id)
                    all_items.append(item)

            # Follow pagination
            next_link = data.get("links", {}).get("next", {})
            if isinstance(next_link, dict):
                url = next_link.get("href", "")
            elif isinstance(next_link, str):
                url = next_link
            else:
                url = ""

            if not url:
                break

        return all_items

    def fetch_filtered(self, api_path: str, filters: Optional[dict] = None,
                       sort: Optional[str] = None, max_results: int = 50,
                       include: Optional[str] = None) -> list:
        """Fetch with filters, limited to max_results (single page)."""
        path = f"/api/{api_path}?page[limit]={min(max_results, 50)}"
        if filters:
            for key, value in filters.items():
                path += f"&filter[{key}]={urllib.parse.quote(str(value))}"
        if sort:
            path += f"&sort={sort}"
        if include:
            path += f"&include={include}"

        data = self._get(path)
        items = data.get("data", [])

        # Merge included entities if present (e.g., quantity on logs)
        if include and "included" in data:
            self._merge_included_quantities(data, items)

        return items

    # ── Cached lookups ──────────────────────────────────────────

    def get_plant_type_uuid(self, farmos_name: str) -> Optional[str]:
        """Get plant_type taxonomy term UUID by name (cached)."""
        if farmos_name in self._plant_type_cache:
            return self._plant_type_cache[farmos_name]
        terms = self.fetch_by_name("taxonomy_term/plant_type", farmos_name)
        if terms:
            uuid = terms[0]["id"]
            self._plant_type_cache[farmos_name] = uuid
            return uuid
        return None

    def get_section_uuid(self, section_id: str) -> Optional[str]:
        """Get section land asset UUID by name (cached)."""
        if section_id in self._section_cache:
            return self._section_cache[section_id]
        assets = self.fetch_by_name("asset/land", section_id)
        if assets:
            uuid = assets[0]["id"]
            self._section_cache[section_id] = uuid
            return uuid
        return None

    def plant_asset_exists(self, asset_name: str) -> Optional[str]:
        """Check if a plant asset with this name exists. Returns UUID or None."""
        assets = self.fetch_by_name("asset/plant", asset_name)
        return assets[0]["id"] if assets else None

    def log_exists(self, log_name: str, log_type: str = "observation") -> Optional[str]:
        """Check if a log with this name exists. Returns UUID or None."""
        logs = self.fetch_by_name(f"log/{log_type}", log_name)
        return logs[0]["id"] if logs else None

    # ── Entity creation ─────────────────────────────────────────

    def create_quantity(self, plant_id: str, count: int,
                        adjustment: str = "reset") -> Optional[str]:
        """Create a quantity entity for inventory count tracking."""
        payload = {
            "data": {
                "type": "quantity--standard",
                "attributes": {
                    "value": {"decimal": str(count)},
                    "measure": "count",
                    "label": "plants",
                    "inventory_adjustment": adjustment,
                },
                "relationships": {
                    "units": {
                        "data": {
                            "type": "taxonomy_term--unit",
                            "id": PLANT_UNIT_UUID,
                        }
                    },
                    "inventory_asset": {
                        "data": {
                            "type": "asset--plant",
                            "id": plant_id,
                        }
                    },
                },
            }
        }
        result = self._post("/api/quantity/standard", payload)
        return result.get("data", {}).get("id")

    def create_observation_log(self, plant_id: str, section_uuid: str,
                                quantity_id: Optional[str], timestamp: int,
                                name: str, notes: str = "") -> Optional[str]:
        """Create an observation log with optional inventory count and movement."""
        log_data = {
            "attributes": {
                "name": name,
                "timestamp": str(timestamp),
                "status": "done",
                "is_movement": True,
            },
            "relationships": {
                "asset": {
                    "data": [{"type": "asset--plant", "id": plant_id}]
                },
                "location": {
                    "data": [{"type": "asset--land", "id": section_uuid}]
                },
            },
        }
        if notes:
            log_data["attributes"]["notes"] = {"value": notes, "format": "default"}
        if quantity_id:
            log_data["relationships"]["quantity"] = {
                "data": [{"type": "quantity--standard", "id": quantity_id}]
            }

        payload = {"data": {"type": "log--observation", **log_data}}
        result = self._post("/api/log/observation", payload)
        return result.get("data", {}).get("id")

    def create_activity_log(self, section_uuid: str, timestamp: int,
                             name: str, notes: str = "",
                             asset_ids: Optional[list] = None) -> Optional[str]:
        """Create an activity log for a field activity."""
        log_data = {
            "attributes": {
                "name": name,
                "timestamp": str(timestamp),
                "status": "done",
            },
            "relationships": {
                "location": {
                    "data": [{"type": "asset--land", "id": section_uuid}]
                },
            },
        }
        if notes:
            log_data["attributes"]["notes"] = {"value": notes, "format": "default"}
        if asset_ids:
            log_data["relationships"]["asset"] = {
                "data": [{"type": "asset--plant", "id": aid} for aid in asset_ids]
            }

        payload = {"data": {"type": "log--activity", **log_data}}
        result = self._post("/api/log/activity", payload)
        return result.get("data", {}).get("id")

    def create_plant_asset(self, name: str, plant_type_uuid: str,
                            notes: str = "") -> Optional[str]:
        """Create a Plant asset in farmOS."""
        data = {
            "attributes": {
                "name": name,
                "status": "active",
            },
            "relationships": {
                "plant_type": {
                    "data": [{"type": "taxonomy_term--plant_type", "id": plant_type_uuid}]
                },
            },
        }
        if notes:
            data["attributes"]["notes"] = {"value": notes, "format": "default"}

        payload = {"data": {"type": "asset--plant", **data}}
        result = self._post("/api/asset/plant", payload)
        return result.get("data", {}).get("id")

    # ── Query helpers for tools ─────────────────────────────────

    def _fetch_plants_contains(self, name_contains: str, status: str = "active") -> list:
        """Fetch plant assets using farmOS CONTAINS filter on name.

        Like _fetch_logs_contains, this pushes filtering to the server side,
        avoiding the need to fetch all 400+ plants and filter in Python.
        """
        if not self._connected:
            raise ConnectionError("Not connected to farmOS. Check credentials.")

        encoded = urllib.parse.quote(name_contains)
        path = (f"/api/asset/plant"
                f"?filter[name][operator]=CONTAINS"
                f"&filter[name][value]={encoded}"
                f"&filter[status]={status}"
                f"&page[limit]=50")

        all_items = []
        seen_ids = set()
        url = f"{self.hostname}{path}"

        while url:
            resp = self.session.get(url, timeout=30)
            if resp.status_code in (401, 403):
                self._connected = False
                raise ConnectionError(
                    f"farmOS authentication expired (HTTP {resp.status_code}). "
                    "Restart the MCP server to reconnect."
                )
            if resp.status_code != 200:
                raise RuntimeError(f"farmOS API error: HTTP {resp.status_code}")
            data = resp.json()
            for item in data.get("data", []):
                item_id = item.get("id", "")
                if item_id and item_id not in seen_ids:
                    seen_ids.add(item_id)
                    all_items.append(item)
            next_link = data.get("links", {}).get("next", {})
            if isinstance(next_link, dict):
                url = next_link.get("href", "")
            elif isinstance(next_link, str):
                url = next_link
            else:
                url = ""
            if not url:
                break

        return all_items

    def get_plant_assets(self, section_id: Optional[str] = None,
                          species: Optional[str] = None,
                          status: str = "active") -> list:
        """Get plant assets with optional section/species filtering.

        Uses server-side CONTAINS filter when possible to avoid fetching
        all 400+ plant assets.
        """
        if species and section_id:
            # Use section_id as the server filter (more specific), then filter by species
            plants = self._fetch_plants_contains(section_id, status)
            return [
                p for p in plants
                if species.lower() in p.get("attributes", {}).get("name", "").lower()
            ]

        if species:
            return self._fetch_plants_contains(species, status)

        if section_id:
            return self._fetch_plants_contains(section_id, status)

        return self.fetch_all_paginated(
            "asset/plant", filters={"status": status}
        )

    def get_section_assets(self, row_filter: Optional[str] = None) -> list:
        """Get land assets (sections) with optional row filter."""
        all_sections = self.fetch_all_paginated("asset/land")
        section_pattern = re.compile(r"^P\dR\d\.\d+-\d+$")

        if row_filter:
            return [
                s for s in all_sections
                if s.get("attributes", {}).get("name", "").startswith(row_filter + ".")
            ]

        return [
            s for s in all_sections
            if section_pattern.match(s.get("attributes", {}).get("name", ""))
        ]

    @staticmethod
    def _merge_included_quantities(data: dict, items: list) -> list:
        """Merge included quantity entities into their parent log objects.

        When logs are fetched with ?include=quantity, the JSON:API response
        puts quantity entities in the top-level 'included' array. This method
        matches them to logs via relationship IDs and attaches them as
        '_quantities' on each log dict.
        """
        included = data.get("included", [])
        if not included:
            return items

        # Build lookup: quantity UUID → quantity entity
        qty_lookup = {}
        for inc in included:
            if inc.get("type", "").startswith("quantity--"):
                qty_lookup[inc.get("id", "")] = inc

        # Attach quantities to each log
        for item in items:
            qty_rels = item.get("relationships", {}).get("quantity", {}).get("data", [])
            if qty_rels:
                quantities = []
                for qr in qty_rels:
                    qid = qr.get("id", "")
                    if qid in qty_lookup:
                        quantities.append(qty_lookup[qid])
                item["_quantities"] = quantities

        return items

    def _fetch_logs_contains(self, log_type: str, name_contains: str,
                              include_quantity: bool = True) -> list:
        """Fetch logs using farmOS CONTAINS filter on name.

        This is far more reliable than fetch_all_paginated + Python filter,
        because farmOS pagination caps at ~250 entries (5 pages of 50).
        The CONTAINS filter pushes the search to the server side.
        """
        if not self._connected:
            raise ConnectionError("Not connected to farmOS. Check credentials.")

        encoded = urllib.parse.quote(name_contains)
        path = (f"/api/log/{log_type}"
                f"?filter[name][operator]=CONTAINS"
                f"&filter[name][value]={encoded}"
                f"&page[limit]=50"
                f"&sort=-timestamp")
        if include_quantity:
            path += "&include=quantity"

        all_items = []
        seen_ids = set()
        url = f"{self.hostname}{path}"

        while url:
            resp = self.session.get(url, timeout=30)
            if resp.status_code in (401, 403):
                self._connected = False
                raise ConnectionError(
                    f"farmOS authentication expired (HTTP {resp.status_code}). "
                    "Restart the MCP server to reconnect."
                )
            if resp.status_code != 200:
                raise RuntimeError(f"farmOS API error: HTTP {resp.status_code}")

            data = resp.json()
            page_items = data.get("data", [])

            # Merge included quantity data into log objects
            if include_quantity:
                self._merge_included_quantities(data, page_items)

            for item in page_items:
                item_id = item.get("id", "")
                if item_id and item_id not in seen_ids:
                    seen_ids.add(item_id)
                    all_items.append(item)

            next_link = data.get("links", {}).get("next", {})
            if isinstance(next_link, dict):
                url = next_link.get("href", "")
            elif isinstance(next_link, str):
                url = next_link
            else:
                url = ""

            if not url:
                break

        return all_items

    def get_logs(self, log_type: Optional[str] = None,
                  section_id: Optional[str] = None,
                  species: Optional[str] = None,
                  max_results: int = 50) -> list:
        """Get logs with optional filtering.

        Uses farmOS CONTAINS filter on name when section_id or species
        is provided. This avoids the pagination cap (~250 entries) that
        makes fetch_all_paginated unreliable for 400+ logs.
        """
        log_types = [log_type] if log_type else [
            "observation", "activity", "transplanting", "harvest", "seeding"
        ]

        # Determine the name filter to use at the API level
        # Prefer section_id (more specific) if both are provided
        name_filter = section_id or species

        all_logs = []
        for lt in log_types:
            try:
                if name_filter:
                    logs = self._fetch_logs_contains(lt, name_filter, include_quantity=True)
                else:
                    logs = self.fetch_filtered(
                        f"log/{lt}",
                        sort="-timestamp",
                        max_results=max_results,
                        include="quantity",
                    )
                all_logs.extend(logs)
            except Exception:
                continue

        # Apply additional Python-side filter if both section_id AND species
        filtered = all_logs
        if section_id and species:
            # API already filtered by section_id, now also filter by species
            filtered = [
                l for l in filtered
                if species.lower() in l.get("attributes", {}).get("name", "").lower()
            ]

        # Sort by timestamp descending
        filtered.sort(
            key=lambda l: l.get("attributes", {}).get("timestamp", ""),
            reverse=True
        )

        return filtered[:max_results]

    def get_plant_type_details(self, name: Optional[str] = None) -> list:
        """Get plant type taxonomy terms, optionally filtered by name."""
        if name:
            return self.fetch_by_name("taxonomy_term/plant_type", name)
        return self.fetch_all_paginated("taxonomy_term/plant_type")

    def get_recent_logs(self, count: int = 20) -> list:
        """Get the most recent logs across all types."""
        return self.get_logs(max_results=count)

    # ── Plant type taxonomy management ─────────────────────────

    def create_plant_type(self, name: str, description: str,
                          maturity_days: Optional[int] = None,
                          transplant_days: Optional[int] = None) -> Optional[str]:
        """Create a plant_type taxonomy term. Returns UUID.

        Note: harvest_days is NOT a valid farmOS field and causes 422 errors.
        Only maturity_days and transplant_days are supported.
        """
        data = {
            "attributes": {
                "name": name,
                "description": {"value": description, "format": "default"},
            }
        }
        if maturity_days and maturity_days > 0:
            data["attributes"]["maturity_days"] = maturity_days
        if transplant_days and transplant_days > 0:
            data["attributes"]["transplant_days"] = transplant_days

        payload = {"data": {"type": "taxonomy_term--plant_type", **data}}
        result = self._post("/api/taxonomy_term/plant_type", payload)
        return result.get("data", {}).get("id")

    def update_plant_type(self, uuid: str, attributes: dict) -> dict:
        """PATCH a plant_type taxonomy term with updated attributes."""
        payload = {
            "data": {
                "type": "taxonomy_term--plant_type",
                "id": uuid,
                "attributes": attributes,
            }
        }
        return self._patch(f"/api/taxonomy_term/plant_type/{uuid}", payload)

    # ── Plant asset management ─────────────────────────────────

    def archive_plant(self, name_or_uuid: str) -> dict:
        """Archive a plant asset (set status to 'archived').

        Args:
            name_or_uuid: Exact plant asset name or UUID.

        Returns:
            The updated plant asset dict from farmOS.

        Raises:
            ValueError: If the plant asset is not found.
        """
        # Determine if this is a UUID (36 chars with dashes) or a name
        is_uuid = (len(name_or_uuid) == 36 and name_or_uuid.count("-") == 4)

        if is_uuid:
            plant_uuid = name_or_uuid
        else:
            assets = self.fetch_by_name("asset/plant", name_or_uuid)
            if not assets:
                raise ValueError(f"Plant asset '{name_or_uuid}' not found in farmOS")
            plant_uuid = assets[0]["id"]

        payload = {
            "data": {
                "type": "asset--plant",
                "id": plant_uuid,
                "attributes": {
                    "status": "archived",
                },
            }
        }
        result = self._patch(f"/api/asset/plant/{plant_uuid}", payload)
        return result.get("data", {})

    # ── File upload ────────────────────────────────────────────

    def upload_file(self, entity_type: str, entity_id: str,
                    field_name: str, filename: str, binary_data: bytes,
                    mime_type: str = "image/jpeg") -> Optional[str]:
        """Upload a file to a farmOS entity's image/file field.

        Uses binary POST (not the session's JSON content-type).

        Args:
            entity_type: e.g., "log/observation", "asset/plant"
            entity_id: UUID of the entity
            field_name: "image" or "file"
            filename: e.g., "photo.jpg"
            binary_data: raw file bytes
            mime_type: MIME type (default "image/jpeg")
        """
        if not self._connected:
            raise ConnectionError("Not connected to farmOS. Check credentials.")

        url = f"{self.hostname}/api/{entity_type}/{entity_id}/{field_name}"
        headers = {
            "Authorization": self.session.headers["Authorization"],
            "Content-Type": "application/octet-stream",
            "Content-Disposition": f'file; filename="{filename}"',
        }
        resp = requests.post(url, data=binary_data, headers=headers, timeout=60)
        if resp.status_code in (401, 403):
            self._connected = False
            raise ConnectionError(
                f"farmOS authentication expired (HTTP {resp.status_code}). "
                "Restart the MCP server to reconnect."
            )
        resp.raise_for_status()
        return resp.json().get("data", {}).get("id")
