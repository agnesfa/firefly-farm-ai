"""
Plant Types Google Sheet client for the MCP server.

Talks to a Google Apps Script endpoint that manages the
"Firefly Corner - Plant Types" Google Sheet — Claire's live view
of the plant type taxonomy.

Follows the same pattern as observe_client.py and memory_client.py.
"""

import json
import os
from typing import Optional

import requests
from dotenv import load_dotenv


class PlantTypesClient:
    """HTTP client for the Google Apps Script plant types endpoint.

    The endpoint supports:
      GET  ?action=list                     — list all plant types
      GET  ?action=search&query=...         — search by name (partial match)
      GET  ?action=reconcile               — get sheet data for drift detection
      POST {action: "add", ...fields}       — add a new plant type row
      POST {action: "update", farmos_name, ...fields} — update existing row
    """

    def __init__(self):
        self.endpoint = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> bool:
        """Load endpoint URL from environment."""
        load_dotenv()

        self.endpoint = os.getenv("PLANT_TYPES_ENDPOINT", "").rstrip("/")
        if not self.endpoint:
            raise ValueError(
                "Missing PLANT_TYPES_ENDPOINT environment variable. "
                "Set it to the Google Apps Script deployment URL for the Plant Types sheet."
            )
        self._connected = True
        return True

    def list_all(self) -> dict:
        """Fetch all plant types from the Google Sheet.

        Returns dict with keys: success, plant_types (list), count (int).
        """
        params = {"action": "list"}
        resp = requests.get(self.endpoint, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def search(self, query: str) -> dict:
        """Search plant types by name (partial match on farmos_name,
        common_name, or botanical_name).

        Returns dict with keys: success, results (list), count (int).
        """
        params = {"action": "search", "query": query}
        resp = requests.get(self.endpoint, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def add(self, fields: dict) -> dict:
        """Add a new plant type row to the Sheet.

        Args:
            fields: Dict with plant type fields. Must include 'farmos_name'.
                    Other fields: common_name, variety, botanical_name,
                    crop_family, origin, description, lifespan_years,
                    lifecycle_years, maturity_days, strata, succession_stage,
                    plant_functions, harvest_days, germination_time,
                    transplant_days, source.

        Returns dict with keys: success, message, row.
        """
        payload = json.dumps({**fields, "action": "add"})
        resp = requests.post(
            self.endpoint,
            data=payload,
            headers={"Content-Type": "text/plain"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def update(self, farmos_name: str, fields: dict) -> dict:
        """Update an existing plant type row in the Sheet.

        Only updates fields that are provided — doesn't overwrite others.

        Args:
            farmos_name: The exact farmos_name to find and update.
            fields: Dict of fields to update (excluding farmos_name).

        Returns dict with keys: success, message, row, updated_fields.
        """
        payload = json.dumps({
            **fields,
            "action": "update",
            "farmos_name": farmos_name,
        })
        resp = requests.post(
            self.endpoint,
            data=payload,
            headers={"Content-Type": "text/plain"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def get_reconcile_data(self) -> dict:
        """Fetch sheet data for reconciliation against farmOS.

        Returns key fields (farmos_name, strata, succession_stage,
        botanical_name, crop_family, plant_functions) with row numbers
        for drift detection.

        Returns dict with keys: success, plant_types (list), count (int).
        """
        params = {"action": "reconcile"}
        resp = requests.get(self.endpoint, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
