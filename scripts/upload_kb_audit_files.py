#!/usr/bin/env python3
"""
upload_kb_audit_files.py — Upload P2 reconciliation audit files to the
Knowledge Base Drive folder and create corresponding KB entries.

Requires KnowledgeBase.gs to include the `upload_file` and `list_folders`
actions (added April 15 2026).

Usage:
    source .env
    python scripts/upload_kb_audit_files.py               # upload + create entries
    python scripts/upload_kb_audit_files.py --dry-run     # plan only, no writes
    python scripts/upload_kb_audit_files.py --list-only   # just show folder state

Environment:
    KB_ENDPOINT must point at the deployed KnowledgeBase.gs Apps Script /exec URL.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from pathlib import Path
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

AUDITS = [
    ("P2R1", "fieldsheets/audits/P2R1-reconciliation.md"),
    ("P2R2", "fieldsheets/audits/P2R2-reconciliation.md"),
    ("P2R3", "fieldsheets/audits/P2R3-reconciliation.md"),
    ("P2R4", "fieldsheets/audits/P2R4-reconciliation.md"),
    ("P2R5", "fieldsheets/audits/P2R5-reconciliation.md"),
]

SUBFOLDER_NAME = "data-quality"

KB_ENTRY_CATEGORY = "reference"
KB_ENTRY_TOPICS = "paddock"
KB_ENTRY_TAGS = "data-audit,reconciliation,spreadsheet,farmOS,P2"
KB_ENTRY_AUTHOR = "Agnes"
KB_ENTRY_SOURCE_TYPE = "reference"


def post_json(endpoint: str, payload: dict) -> dict:
    req = urlrequest.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "text/plain"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
    except HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        print(f"HTTP error {e.code}: {raw}", file=sys.stderr)
        return {"success": False, "error": f"HTTP {e.code}: {raw[:200]}"}
    except URLError as e:
        print(f"URL error: {e}", file=sys.stderr)
        return {"success": False, "error": str(e)}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"success": False, "error": f"Non-JSON response: {raw[:200]}"}


def upload_file(endpoint: str, path: Path, subfolder: str) -> dict:
    content = path.read_bytes()
    b64 = base64.b64encode(content).decode("ascii")
    payload = {
        "action": "upload_file",
        "subfolder": subfolder,
        "filename": path.name,
        "content_base64": b64,
        "mime_type": "text/markdown",
        "overwrite": True,
    }
    return post_json(endpoint, payload)


def extract_summary(md_body: str) -> str:
    """Extract the key sections from an audit file for the KB entry content.

    Keeps: intro + structural findings + summary of findings + 🔴 punch list.
    Drops: per-section tables (too long for a KB entry — full file is on Drive).
    """
    lines = md_body.splitlines()
    out: list[str] = []
    mode = "intro"  # intro | findings | skip_sections | summary | red_list | done
    for line in lines:
        if mode == "intro":
            out.append(line)
            if line.startswith("## Section-by-section"):
                # Stop capturing until we hit the summary
                out.pop()
                mode = "skip_sections"
            continue
        if mode == "skip_sections":
            if line.startswith("## Summary of findings"):
                out.append("")
                out.append(line)
                mode = "summary"
            continue
        if mode == "summary":
            out.append(line)
            if line.startswith("### new Rows") or line.startswith("---"):
                mode = "done"
            continue
        if mode == "done":
            # Stop — don't include the "new" list
            break
    return "\n".join(out)


# Match an audit file bullet like:
#   "- **P2R3.2-9 — Jaboticaba** (Medium): all lost (was 5)"
# or the "missing" variant:
#   "- **P2R3.15-21 — Forest Red Gum** (Emergent): in sheet (1), missing..."
#
# We capture the species between the " — " and the closing "**" — whatever
# strata marker follows in "(...)" is not part of the species name.
_RED_ROW_RE = re.compile(
    r"^\s*-\s*\*\*(?P<section>[PR0-9.\-]+)\s+—\s+(?P<species>[^*]+?)\*\*"
)


def extract_red_species(md_body: str) -> list[str]:
    """Pull the unique species names from the 🔴 field-check list.

    Used to populate the `related_plants` field on the KB entry so species-
    scoped searches (e.g. "where have we lost Ice Cream Bean?") surface
    the audit entries that mention it.
    """
    species: list[str] = []
    seen: set[str] = set()
    in_red_section = False
    for line in md_body.splitlines():
        if line.startswith("### 🔴") or line.strip().startswith("### 🔴"):
            in_red_section = True
            continue
        if in_red_section:
            if line.startswith("### ") or line.startswith("## "):
                break
            m = _RED_ROW_RE.match(line)
            if m:
                name = m.group("species").strip()
                if name and name not in seen:
                    seen.add(name)
                    species.append(name)
    return species


def add_kb_entry(endpoint: str, row: str, file_url: str, md_body: str) -> dict:
    """Create a KB entry that points at the uploaded audit file."""
    title = f"{row} — Spreadsheet vs farmOS Reconciliation (April 2026)"
    summary = extract_summary(md_body)
    content = (
        f"Reconciliation audit comparing Claire's field spreadsheet for {row} "
        f"against the current farmOS state (generated 2026-04-15).\n\n"
        f"**📄 Full audit file on Drive:** {file_url}\n\n"
        f"Use this KB entry as a quick overview — the per-section tables with all species "
        f"comparisons are in the linked Drive file. This entry includes the structural "
        f"findings, the summary counts, and the 🔴 rows that need a field check.\n\n"
        f"---\n\n"
        f"{summary}"
    )
    if len(content) > 45000:
        content = content[:44900] + "\n\n… (truncated — see Drive file link above)"
    # Populate related_plants from the 🔴 field-check list so Claire's
    # Claude surfaces the audit entry when she asks about a specific
    # species (e.g. "where have we lost Ice Cream Bean?").
    red_species = extract_red_species(md_body)
    payload = {
        "action": "add",
        "title": title,
        "content": content,
        "category": KB_ENTRY_CATEGORY,
        "topics": KB_ENTRY_TOPICS,
        "tags": f"{KB_ENTRY_TAGS},{row.lower()}",
        "author": KB_ENTRY_AUTHOR,
        "source_type": KB_ENTRY_SOURCE_TYPE,
        "media_links": file_url,
        "related_sections": row,
        "related_plants": ",".join(red_species) if red_species else "",
    }
    return post_json(endpoint, payload)


def list_folders(endpoint: str) -> dict:
    return post_json(endpoint, {"action": "list_folders"})


def get_json(endpoint: str, params: dict) -> dict:
    """GET the KB endpoint with query params. Used for list/search actions."""
    from urllib.parse import urlencode
    url = f"{endpoint}?{urlencode(params)}"
    try:
        with urlrequest.urlopen(url, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        return {"success": False, "error": f"HTTP {e.code}"}
    except URLError as e:
        return {"success": False, "error": str(e)}


def find_entry_by_title(endpoint: str, title_prefix: str) -> dict | None:
    """Find a KB entry whose title starts with the given prefix.

    Uses the list action (GET) rather than search — search looks at
    content/tags as well and could match the wrong entry when the audit
    corpus is growing. Title-prefix match is exact enough for our
    known-title lookups.
    """
    result = get_json(endpoint, {
        "action": "list",
        "category": KB_ENTRY_CATEGORY,
        "limit": "200",
    })
    if not result.get("success"):
        return None
    for entry in result.get("entries") or []:
        if (entry.get("title") or "").startswith(title_prefix):
            return entry
    return None


def update_kb_entry(
    endpoint: str,
    entry_id: str,
    row: str,
    file_url: str,
    md_body: str,
) -> dict:
    """Update an existing KB entry in place (same content/structure as add,
    but targets the existing row via its entry_id). Used by --refresh mode
    to push fixes (new related_plants, cleaned content) without duplicating
    sheet rows."""
    title = f"{row} — Spreadsheet vs farmOS Reconciliation (April 2026)"
    summary = extract_summary(md_body)
    content = (
        f"Reconciliation audit comparing Claire's field spreadsheet for {row} "
        f"against the current farmOS state (generated 2026-04-15).\n\n"
        f"**📄 Full audit file on Drive:** {file_url}\n\n"
        f"Use this KB entry as a quick overview — the per-section tables with all species "
        f"comparisons are in the linked Drive file. This entry includes the structural "
        f"findings, the summary counts, and the 🔴 rows that need a field check.\n\n"
        f"---\n\n"
        f"{summary}"
    )
    if len(content) > 45000:
        content = content[:44900] + "\n\n… (truncated — see Drive file link above)"

    red_species = extract_red_species(md_body)
    payload = {
        "action": "update",
        "entry_id": entry_id,
        "title": title,
        "content": content,
        "category": KB_ENTRY_CATEGORY,
        "topics": KB_ENTRY_TOPICS,
        "tags": f"{KB_ENTRY_TAGS},{row.lower()}",
        "author": KB_ENTRY_AUTHOR,
        "source_type": KB_ENTRY_SOURCE_TYPE,
        "media_links": file_url,
        "related_sections": row,
        "related_plants": ",".join(red_species) if red_species else "",
    }
    return post_json(endpoint, payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Show the plan without writing to Drive or the KB")
    parser.add_argument("--list-only", action="store_true", help="Only list existing KB subfolders and exit")
    parser.add_argument("--skip-entries", action="store_true", help="Upload files but don't create KB sheet entries")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Update existing KB entries in place instead of adding new ones. "
             "Use this after editing audit files or fixing the uploader — "
             "it finds entries by title prefix and calls the update action. "
             "Drive files are overwritten as usual.",
    )
    args = parser.parse_args()

    endpoint = (
        os.environ.get("KNOWLEDGE_ENDPOINT", "")
        or os.environ.get("KB_ENDPOINT", "")
    ).strip()
    if not endpoint:
        print("ERROR: KNOWLEDGE_ENDPOINT env var is not set.", file=sys.stderr)
        print("Set it to the deployed KnowledgeBase.gs /exec URL.", file=sys.stderr)
        return 1

    print(f"Using KB endpoint: {endpoint[:60]}...")

    # Always show current folder state first
    print("\n── Existing KB Drive subfolders ──")
    folders = list_folders(endpoint)
    if folders.get("success"):
        for f in folders.get("folders", []):
            print(f"  • {f['name']}  ({f['id'][:12]}…)")
    else:
        print(f"  (could not list: {folders.get('error', 'unknown error')})")
        return 1

    if args.list_only:
        return 0

    # Upload each audit file
    print(f"\n── Uploading {len(AUDITS)} audit files to '{SUBFOLDER_NAME}/' ──")
    results: list[dict] = []
    for row, rel_path in AUDITS:
        path = Path(rel_path)
        if not path.exists():
            print(f"  ✗ {row}: file not found at {path}")
            continue
        size_kb = path.stat().st_size / 1024
        print(f"  • {row} ({path.name}, {size_kb:.1f} KB) ... ", end="", flush=True)
        if args.dry_run:
            print("dry-run")
            results.append({"row": row, "path": path, "skipped": True})
            continue
        result = upload_file(endpoint, path, SUBFOLDER_NAME)
        if result.get("success"):
            print(f"OK → {result['file_url']}")
            results.append({"row": row, "path": path, "file_url": result["file_url"]})
        else:
            print(f"FAIL: {result.get('error', 'unknown')}")
            results.append({"row": row, "path": path, "error": result.get("error")})

    if args.dry_run or args.skip_entries:
        return 0

    # Create or refresh KB entries that reference the uploaded files.
    # --refresh locates each entry by title prefix and calls the update
    # action; plain mode calls add and creates new rows.
    if args.refresh:
        print(f"\n── Refreshing existing KB sheet entries ──")
    else:
        print(f"\n── Creating KB sheet entries ──")

    for r in results:
        if "file_url" not in r:
            continue
        md_body = r["path"].read_text()
        print(f"  • {r['row']} ... ", end="", flush=True)

        if args.refresh:
            title_prefix = f"{r['row']} — Spreadsheet vs farmOS Reconciliation"
            existing = find_entry_by_title(endpoint, title_prefix)
            if not existing:
                print(f"NOT FOUND (falling back to add)")
                entry = add_kb_entry(endpoint, r["row"], r["file_url"], md_body)
            else:
                entry = update_kb_entry(
                    endpoint, existing["entry_id"], r["row"], r["file_url"], md_body,
                )
        else:
            entry = add_kb_entry(endpoint, r["row"], r["file_url"], md_body)

        if entry.get("success"):
            eid = entry.get("entry_id") or entry.get("updated_id") or "?"
            action = "updated" if args.refresh and "updated" in str(entry) else "ok"
            print(f"{action} (entry_id={eid[:8]}…)")
        else:
            print(f"FAIL: {entry.get('error', 'unknown')}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
