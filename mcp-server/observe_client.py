"""
Observation Sheet client for the MCP server.

Talks to the Google Apps Script endpoint that manages field observations
in the "Firefly Corner - Field Observations" Google Sheet.

Keeps separation of concerns: farmos_client.py talks to farmOS,
observe_client.py talks to the observation sheet.
"""

import json
import os
from typing import Optional

import requests
from dotenv import load_dotenv


class ObservationClient:
    """HTTP client for the Google Apps Script observation endpoint.

    The endpoint supports:
      GET  ?action=list[&status=...&section=...&observer=...&date=...&submission_id=...]
      POST {action: "update_status", updates: [{submission_id, status, reviewer, notes}]}
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

        self.endpoint = os.getenv("OBSERVE_ENDPOINT", "").rstrip("/")
        if not self.endpoint:
            raise ValueError(
                "Missing OBSERVE_ENDPOINT environment variable. "
                "Set it to the Google Apps Script deployment URL."
            )
        self._connected = True
        return True

    def list_observations(
        self,
        status: Optional[str] = None,
        section: Optional[str] = None,
        observer: Optional[str] = None,
        date: Optional[str] = None,
        submission_id: Optional[str] = None,
    ) -> dict:
        """Fetch observations from the Sheet with optional filters.

        Returns dict with keys: success, observations (list), count (int).
        """
        params = {"action": "list"}
        if status:
            params["status"] = status
        if section:
            params["section"] = section
        if observer:
            params["observer"] = observer
        if date:
            params["date"] = date
        if submission_id:
            params["submission_id"] = submission_id

        resp = requests.get(self.endpoint, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def update_status(self, updates: list) -> dict:
        """Update review status of observation rows.

        Args:
            updates: List of dicts, each with:
                - submission_id (str): Target submission
                - status (str): New status (reviewed/approved/imported/rejected)
                - reviewer (str): Who is making the change
                - notes (str, optional): Review notes

        Returns dict with keys: success, updated (int), errors (list).
        """
        payload = json.dumps({
            "action": "update_status",
            "updates": updates,
        })
        # Content-Type: text/plain avoids CORS preflight (matching observe.js pattern).
        # Apps Script returns 302 redirect — requests follows as GET, which works.
        resp = requests.post(
            self.endpoint,
            data=payload,
            headers={"Content-Type": "text/plain"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
