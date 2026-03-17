"""
Knowledge Base client for the MCP server.

Talks to a Google Apps Script endpoint that manages the
"Firefly Corner - Knowledge Base" Google Sheet and linked Drive folder.

The knowledge base stores farm tutorials, SOPs, agronomic guides, and
links to media files (photos, PDFs, audio recordings).

Follows the same pattern as observe_client.py, memory_client.py, and plant_types_client.py.
"""

import json
import os
from typing import Optional

import requests
from dotenv import load_dotenv


class KnowledgeClient:
    """HTTP client for the Google Apps Script knowledge base endpoint.

    The endpoint supports:
      GET  ?action=list[&category=...&limit=...&offset=...]  — list entries
      GET  ?action=search&query=...[&category=...]           — full-text search
      GET  ?action=categories                                — list all categories
      POST {action: "add", ...fields}                        — add a new entry
      POST {action: "update", entry_id, ...fields}           — update existing entry
      POST {action: "archive", entry_id}                     — archive (soft delete)
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

        self.endpoint = os.getenv("KNOWLEDGE_ENDPOINT", "").rstrip("/")
        if not self.endpoint:
            raise ValueError(
                "Missing KNOWLEDGE_ENDPOINT environment variable. "
                "Set it to the Google Apps Script deployment URL for the Knowledge Base sheet."
            )
        self._connected = True
        return True

    def list_entries(
        self,
        category: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """Fetch knowledge base entries, optionally filtered by category.

        Returns dict with keys: success, entries (list), count (int), total (int).
        """
        params = {"action": "list", "limit": str(limit), "offset": str(offset)}
        if category:
            params["category"] = category

        resp = requests.get(self.endpoint, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def search(self, query: str, category: Optional[str] = None) -> dict:
        """Search knowledge base by text (partial match on title, content, tags).

        Args:
            query: Text to search for.
            category: Optional category filter.

        Returns dict with keys: success, results (list), count (int).
        """
        params = {"action": "search", "query": query}
        if category:
            params["category"] = category

        resp = requests.get(self.endpoint, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_categories(self) -> dict:
        """Fetch all distinct categories used in the knowledge base.

        Returns dict with keys: success, categories (list of str).
        """
        params = {"action": "categories"}
        resp = requests.get(self.endpoint, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def add(self, fields: dict) -> dict:
        """Add a new knowledge base entry.

        Args:
            fields: Dict with entry fields:
                - title (required): Article/guide title
                - content (required): Full text content
                - category (required): Category tag (e.g., "syntropic", "composting",
                  "irrigation", "nursery", "pests", "harvest", "equipment", "general")
                - tags: Comma-separated tags for searchability
                - author: Who wrote this (e.g., "Claire", "Olivier")
                - source_type: Type of source material ("tutorial", "sop", "guide",
                  "observation", "recipe", "reference")
                - media_links: Comma-separated Drive file IDs or URLs
                - related_plants: Comma-separated farmos_names of related plant types
                - related_sections: Comma-separated section IDs (e.g., "P2R3.15-21")

        Returns dict with keys: success, message, entry_id, row.
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

    def update(self, entry_id: str, fields: dict) -> dict:
        """Update an existing knowledge base entry.

        Only updates fields that are provided — doesn't overwrite others.

        Args:
            entry_id: The entry ID (row number as string) to update.
            fields: Dict of fields to update.

        Returns dict with keys: success, message, updated_fields.
        """
        payload = json.dumps({
            **fields,
            "action": "update",
            "entry_id": entry_id,
        })
        resp = requests.post(
            self.endpoint,
            data=payload,
            headers={"Content-Type": "text/plain"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def archive(self, entry_id: str, reason: str = "") -> dict:
        """Archive (soft-delete) a knowledge base entry.

        Args:
            entry_id: The entry ID to archive.
            reason: Optional reason for archiving.

        Returns dict with keys: success, message.
        """
        payload = json.dumps({
            "action": "archive",
            "entry_id": entry_id,
            "reason": reason,
        })
        resp = requests.post(
            self.endpoint,
            data=payload,
            headers={"Content-Type": "text/plain"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
