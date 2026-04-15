# 0002 — Knowledge Base file upload via KnowledgeBase.gs

- **Status:** accepted
- **Date:** 2026-04-15
- **Authors:** Agnes, Claude
- **Related:** ADR 0003 (audit tool), `scripts/google-apps-script/KnowledgeBase.gs`

## Context

The Knowledge Base has historically been text-only: KB entries are rows
in a Google Sheet with a `content` column for the markdown body and a
`media_links` column for Drive URLs that had to be populated manually.
There was no way to upload files to the KB Drive folder
programmatically — every photo, PDF, or markdown attachment had to be
dragged into the right folder by hand.

This became a blocker for the P2 reconciliation audit work (ADR 0003):
the per-row audit files are 10–26 KB of markdown each, too big to
comfortably inline as KB entry content, and they need to live on Drive
so Claire can open them directly from her Claude session via
`search_knowledge` + the `media_links` field.

Adjacent pressure: Agnes has indicated she wants a disciplined
architecture decision record process going forward, and file-upload
capability on the KB is a natural fit for future ADRs and design docs
that currently have no good shared storage.

## Decision

Extend `scripts/google-apps-script/KnowledgeBase.gs` with two new
POST actions:

1. **`upload_file`** — takes `{subfolder, filename, content_base64,
   mime_type, overwrite}`, creates the subfolder under the KB root if
   it doesn't exist, uploads the file, and returns
   `{file_id, file_url, subfolder_id, subfolder_url}`. The KB root
   folder id is hardcoded as `KB_DRIVE_FOLDER_ID` in the script.

2. **`list_folders`** — returns the immediate subfolders of the KB
   root. Used by clients to discover whether a subfolder exists
   before uploading.

A companion Python helper `scripts/upload_kb_audit_files.py`
drives the endpoint from a local shell: it reads each audit `.md`
file, base64-encodes it, POSTs it to `KNOWLEDGE_ENDPOINT` as
`upload_file`, and then creates a corresponding KB sheet entry via
the existing `add` action with the Drive URL in `media_links` and a
concise summary (structural findings + red-flag list) in the
`content` field.

The python helper extracts the summary section of each audit file
rather than inlining the full 10–26 KB body, so the sheet cell stays
well under the 50 KB limit and Claire's Claude can ingest the entry
quickly via `search_knowledge` without pulling the entire file.

## Rationale

Apps Script is the existing pattern for Google-side integration in
this project (Observations.gs, SeedBank.gs, TeamMemory.gs, PlantTypes.gs
all use the same pattern). Extending KnowledgeBase.gs keeps the
infrastructure cost near zero: no new service account, no gcloud CLI,
no credentials file, just a script the owner already deploys.

### Alternatives considered

- **Google Drive API with service account.** Cleaner from a "one tool
  one job" perspective and avoids deploy friction. Rejected because
  (1) service account setup requires IAM config Agnes hasn't done,
  (2) the Drive files are owned by Agnes's personal account and
  sharing rules would need to be rewritten, (3) it introduces a
  second auth path alongside the existing Apps Script one, and
  (4) James's previous "silent write failures" (MEMORY.md) were all
  Apps Script deploy issues, so we already have the operational
  experience to debug this path.

- **Upload files as base64-in-content directly to the sheet.** Fits
  in the existing schema but wastes rows on binary data that can't
  be searched, loaded, or rendered. Rejected.

- **Rclone / gdrive CLI.** Requires tooling the user doesn't have
  installed. We checked — no `gcloud`, `clasp`, `gdrive`, or `rclone`
  is available on Agnes's machine. Rejected.

- **Manual drag-and-drop.** The fallback that's worked until now.
  Rejected for this ADR because we're at volume (5 audit files now,
  more audits + design docs coming as the ADR process takes hold).
  We'd drop files manually once; we'd regret it every subsequent
  time.

## Consequences

### Positive

- KB entries can now carry real Drive file attachments via the
  `media_links` field. Claire's Claude can read the entry, find the
  link, and open the file in-browser.

- Subfolders are created on demand. The existing KB folder layout
  (`tutorials/`, `sop/`, `guides/`, `reference/`) extends naturally —
  the audit work creates `data-quality/` as a fifth category without
  hardcoding it anywhere except in the upload call's `subfolder`
  argument.

- Any future ADR that produces long-form artifacts (design docs,
  test results, photo galleries, transcripts) has a canonical
  shared storage path: `upload_file` into the appropriate KB
  subfolder, then `add` a KB entry pointing at it.

- Builds on the established Apps Script deploy pattern instead of
  introducing a parallel integration mechanism.

### Negative

- **Deploy friction.** Adding the two new actions requires Agnes to
  paste the updated KnowledgeBase.gs into the Apps Script editor and
  redeploy the web app. James's prior "silent write failures" with
  KB.gs deploys (MEMORY.md April 10) are an operational risk
  specifically for this kind of change. Mitigation: the commit
  message and team memory entry both call out that the deploy is
  required and what the failure mode looks like.

- **Single Drive account owner.** Files uploaded via the script are
  owned by the Apps Script's execute-as identity
  (Agnes on fireflyagents.com). That's fine for now but becomes a
  single point of failure if Agnes's account is unavailable.
  Acceptable for this phase; flagged for a future multi-user ADR.

- **Apps Script quotas.** Each upload counts against the script's
  execution time and UrlFetch quota. For the audit files (5 × 26 KB)
  this is trivial, but a large photo-upload workload would hit the
  6-minute execution limit per request. Not a near-term concern.

### Neutral

- The KB root folder id is hardcoded in the .gs script. If the
  folder is moved or replaced, the id must be updated in source.
  This is the same brittleness pattern the other Apps Scripts use.

## Implementation

Files changed:

- `scripts/google-apps-script/KnowledgeBase.gs`:
  - Added `KB_DRIVE_FOLDER_ID` constant at the top.
  - Extended `doPost` action dispatch to accept `upload_file` and
    `list_folders`.
  - Added `handleUploadFile` (creates subfolder if needed, handles
    overwrite, returns full file metadata).
  - Added `handleListFolders` (enumerates KB root subfolders).

- `scripts/upload_kb_audit_files.py`:
  - Reads 5 audit files from `fieldsheets/audits/`.
  - Uploads each to the KB Drive subfolder `data-quality/`.
  - Creates a KB sheet entry per row with title
    "{ROW} — Spreadsheet vs farmOS Reconciliation (April 2026)",
    category `reference`, topic `paddock`, tags including `data-audit`
    and the row id.
  - `extract_summary()` keeps only the intro + structural findings +
    summary + 🔴 field-check list (drops the per-section tables so
    the content fits comfortably in a sheet cell).
  - Supports `--list-only`, `--dry-run`, `--skip-entries` flags.
  - Reads `KNOWLEDGE_ENDPOINT` from env (with `KB_ENDPOINT` as
    backward-compat alias).

Commit SHA at time of writing: _filled in when committed_

Deferred:

- Deployment of the updated KnowledgeBase.gs to the Apps Script
  editor. Script is committed; the deployed endpoint must be
  refreshed manually by Agnes. Until then, `upload_file` and
  `list_folders` return "Unknown action".

## Open questions

- **TypeScript MCP server wrapper** — should we expose `upload_file`
  as a first-class MCP tool so Claude sessions can add files to the
  KB without running `upload_kb_audit_files.py` from a shell? The
  current pattern forces any KB file operation through Agnes's local
  machine. Agnes to decide.

- **Versioning of uploaded files** — `overwrite: true` is the
  default, which means re-uploading an audit replaces the previous
  version with no history. For reconciliation audits that re-run as
  the ground-truth drifts, we may want version-suffix filenames or
  a separate `archive/` subfolder. Deferred.

- **Authorization** — the current design has the KB Drive root
  open for Apps-Script-write from anyone with the endpoint URL.
  The endpoint URL is essentially a shared secret. We should
  consider adding a simple bearer check or per-action whitelist
  before exposing KB file upload to automated triggers.
