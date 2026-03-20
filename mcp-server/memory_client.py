"""
Team Memory client for the MCP server.

Talks to a Google Apps Script endpoint that manages shared session
summaries in the "Firefly Corner - Team Memory" Google Sheet.

Enables cross-user knowledge sharing: each Claude writes session summaries,
all Claudes can read what the team has been doing.

Follows the same pattern as observe_client.py.
"""

import json
import os
from typing import Optional

import requests
from dotenv import load_dotenv


class MemoryClient:
    """HTTP client for the Google Apps Script team memory endpoint.

    The endpoint supports:
      GET  ?action=list[&days=...&user=...&limit=...]
      GET  ?action=search&query=...&days=...
      POST {action: "write_summary", user: ..., topics: ..., ...}
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

        self.endpoint = os.getenv("MEMORY_ENDPOINT", "").rstrip("/")
        if not self.endpoint:
            raise ValueError(
                "Missing MEMORY_ENDPOINT environment variable. "
                "Set it to the Google Apps Script deployment URL for Team Memory."
            )
        self._connected = True
        return True

    def write_summary(
        self,
        user: str,
        topics: str = "",
        decisions: str = "",
        farmos_changes: str = "",
        questions: str = "",
        summary: str = "",
        skip: bool = False,
    ) -> dict:
        """Write a session summary to the shared Team Memory sheet.

        Args:
            user: Who this summary is from (e.g., "Claire", "Agnes")
            topics: Comma-separated topic keywords
            decisions: Key decisions made in this session
            farmos_changes: JSON string of [{type, id, name}] farmOS changes
            questions: Open questions or things to follow up
            summary: Free-text session summary
            skip: If True, mark as skipped (not shared with team)

        Returns dict with keys: success, message.
        """
        payload = json.dumps({
            "action": "write_summary",
            "user": user,
            "topics": topics,
            "decisions": decisions,
            "farmos_changes": farmos_changes,
            "questions": questions,
            "summary": summary,
            "skip": skip,
        })
        resp = requests.post(
            self.endpoint,
            data=payload,
            headers={"Content-Type": "text/plain"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def read_activity(
        self,
        days: int = 7,
        user: Optional[str] = None,
        limit: int = 20,
        only_fresh_for: Optional[str] = None,
    ) -> dict:
        """Fetch recent team session summaries.

        Args:
            days: How many days back to look (default 7)
            user: Filter by user name (optional)
            limit: Max results to return (default 20)
            only_fresh_for: If set, exclude entries already acknowledged
                by this user (e.g., "Claire"). Enables fresh-only filtering.

        Returns dict with keys: success, summaries (list), count (int).
        """
        params = {"action": "list", "days": str(days), "limit": str(limit)}
        if user:
            params["user"] = user
        if only_fresh_for:
            params["only_fresh_for"] = only_fresh_for

        resp = requests.get(self.endpoint, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def search_memory(
        self,
        query: str,
        days: int = 30,
    ) -> dict:
        """Search team memory for matching summaries.

        Server-side text search across Topics, Decisions, Questions,
        and Summary columns.

        Args:
            query: Text to search for
            days: How many days back to search (default 30)

        Returns dict with keys: success, results (list), count (int).
        """
        params = {"action": "search", "query": query, "days": str(days)}

        resp = requests.get(self.endpoint, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def acknowledge_memory(
        self,
        summary_id: str,
        user: str,
    ) -> dict:
        """Mark a team memory entry as acknowledged by a user.

        After a Claude reads and processes a team memory entry, call this
        to mark it as seen. Future read_team_activity calls with
        only_fresh_for=user will exclude acknowledged entries.

        Args:
            summary_id: The row/entry ID to acknowledge
            user: Who is acknowledging (e.g., "Claire", "Agnes")

        Returns dict with keys: success, message.
        """
        payload = json.dumps({
            "action": "acknowledge",
            "summary_id": summary_id,
            "user": user,
        })
        resp = requests.post(
            self.endpoint,
            data=payload,
            headers={"Content-Type": "text/plain"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
