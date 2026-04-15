# 0003 — Field-sheet reconciliation audit tool and storage

- **Status:** accepted
- **Date:** 2026-04-15
- **Authors:** Agnes, Claude
- **Related:** ADR 0002 (KB file upload), `scripts/audit_row.py`,
  `claude-docs/audits/README.md`,
  April 12 Claire meeting notes
  (Downloads/Amélioration Farm Intelligence Transcript.txt)

## Context

During the April 12 meeting, Claire expressed clear frustration with
farmOS data quality. Her exact example: she asked her Claude session
"what's in Row 5?" and got an answer that included an avocado. She
was certain no avocado was planted in Row 5 (only one Hass exists on
the whole farm, and it's somewhere else). She concluded — reasonably
— that the underlying data was wrong, and that the rest of the farm
intelligence layer built on top of it was also suspect.

Agnes's commitment in that meeting: Claire should be able to
interact with Claude at the same level as Agnes, with a data layer
she can trust. The path she offered was a photo campaign plus a
visual navigator — but before either of those is useful, Claire
needs to see that the base data **matches her own records**.

A prior session (April 13) produced a manual P2R5 comparison that
confirmed Claire's Row 5 avocado suspicion was correct (two
different "Avocado" plant_type terms in farmOS, one of them a bulk
import phantom) and found four more structural issues in the row.
The comparison was written as free-form markdown and shared with
Claire directly. That document is the P2R5 reference in
`fieldsheets/audits/P2R5-reconciliation.md`.

This session extends that pattern from P2R5 to the rest of Paddock 2
(P2R1, P2R2, P2R3, P2R4) and turns the one-off manual comparison
into a reusable tool.

## Decision

Build `scripts/audit_row.py`, a Python tool that takes a row id,
a field-sheet .xlsx path, and a farmOS JSON snapshot, and produces
a reconciliation markdown file in the P2R5 format. The tool is
schema-aware (parses three different Excel layouts Claire has used
across rows), normalizes species names against a
`SPECIES_ALIASES` dict, aggregates duplicates, handles annual
lifecycle cases, and flags structural issues (duplicated tabs,
gap sections, boundary shifts).

Generated audit files are stored in **three** places with three
different purposes:

1. **`fieldsheets/audits/`** — local working copies on Agnes's
   machine. **Gitignored.** Regenerate on demand via
   `audit_row.py`. Not shared anywhere.

2. **Google Drive `Knowledge Base / data-quality/`** — canonical
   shared storage. Uploaded via `scripts/upload_kb_audit_files.py`
   which uses the new `upload_file` action on KnowledgeBase.gs
   (see ADR 0002). Claire and James access audits from here.

3. **KB sheet entries** — one entry per row audit, category
   `reference`, topic `paddock`, tags including `data-audit` and
   the row id. The entry `content` field holds the summary
   (structural findings + 🔴 field-check list), the `media_links`
   field holds the Drive URL to the full file. Claire's Claude
   finds these via `search_knowledge`.

The workflow is:

1. Agnes runs `audit_row.py` locally to generate the .md file.
2. Agnes + James walk the 🔴 rows in the field to verify each
   discrepancy and commit corrective actions in farmOS (archive
   phantom plants, correct counts, record missed plantings).
3. Once the 🔴 list is cleaned, Agnes runs
   `upload_kb_audit_files.py` to push the reviewed audit files
   to the KB.
4. Claire opens her Claude session, asks "what do we know about
   P2R3?", and her Claude uses `search_knowledge` to find the
   audit entry + Drive link.

This matches the direction Agnes set on April 12 — Claire should
work with Claude using live KB data, not by reading spreadsheets
offline.

## Rationale

The audit tool is intentionally a script, not an MCP tool. Two
reasons:

1. **Schema-heavy parsing.** The three Excel layouts (schema A:
   2026 Feb inventory, schema B: 2026 Mar farmOS-snapshot, schema C:
   2025 Spring renovation) have different column orders, different
   baseline semantics (new_total vs last_inventory vs planted), and
   different species naming conventions. Parser state is easier to
   develop and test as a standalone Python script than as a remote
   MCP tool. The parser runs once per row per session, not per
   chat turn.

2. **Data residency.** The .xlsx files are on Agnes's machine and
   in her Drive. Putting the parser on the Railway MCP server
   would require uploading the xlsx files there, which creates a
   second synchronization problem. Running the parser locally and
   uploading only the output .md to the KB puts exactly what needs
   to be shared in exactly the place it should live.

The three-storage-locations choice is deliberate:

- **Local (fieldsheets/audits/)** is where the tool writes. It's
  also where Agnes iterates — running the tool repeatedly as she
  refines species aliases, fixes baseline detection, etc. Not
  gitignored previously; we gitignore it now because these files
  are outputs, not source.

- **Drive (data-quality/)** is where the human team reads. Claire
  opens the Drive file directly when she wants the full per-section
  tables; her Claude reads the KB entry summary for quick lookups.

- **KB sheet** is where Claude reads. The content field is what
  `search_knowledge` returns, so it holds the summary. The full
  file is one click away via `media_links`.

### Alternatives considered

- **Inline the full audit in KB entry content.** Rejected: audit
  files are up to 26 KB of markdown and the sheet cell limit
  (50 KB) is tight. Summary + Drive link is cleaner.

- **Commit audit files to the codebase.** Rejected per Agnes's
  April 15 direction — audits are generated outputs that don't
  belong in the source tree, and they're Claire-facing artifacts
  that shouldn't require a git pull to access.

- **Single unified audit schema.** Rejected: rewriting Claire's
  historical spreadsheets into a single schema would discard
  context (lifecycle brackets in the renovation sheet, farmOS
  count snapshots in the mid-2026 sheet). Schema-aware parsing
  preserves the source data as-is.

- **Run the audit tool on every commit as CI.** Rejected for
  now: running against live farmOS data on CI would couple our
  repo to farmOS availability and leak production data into CI
  logs. Manual runs are fine at this phase.

## Consequences

### Positive

- **Reusable tool.** Adding row 6 is a one-line change. Fixing the
  species alias dict fixes all audits at once.

- **Clear ownership of each storage location.** Agnes iterates in
  `fieldsheets/audits/`. Claire reads from KB Drive. Claude reads
  from KB sheet entries. No ambiguity about where the canonical
  version lives.

- **Critical findings surface clearly.** The P2R3.40-50 /
  P2R3.50-62 duplicated-tab bug was invisible in Claire's sheet
  itself (she created the tabs by "split from 41-63" intent) but
  the tool detects identical-row tabs and flags them with a
  🔴 structural warning. Same for phantom bulk-import species.

- **Path forward for the visual navigator.** The same diff
  machinery + summary format can be rendered as HTML in the
  future navigator design. ADR 0003 doesn't build the
  navigator — just produces the first datasets it will consume.

### Negative

- **Schema-aware parsing is brittle.** New Excel schemas Claire
  invents will need a new parser arm. The current three-schema
  tree works but is at the limit of readability; a fourth schema
  would justify refactoring.

- **Species alias dict is maintained by hand.** Every mismatch we
  find adds an entry. This is a "toil tax" that grows slowly
  over time. Acceptable for the current ~30-entry dict; would
  want a more principled synonym system at 100+ entries.

- **Two manual steps per audit.** Generate → field-verify → upload.
  We could automate generate + upload but the field verification
  step is inherently human. Keeping the two halves manual matches
  the operational reality.

### Neutral

- **Audit files are inputs to farmOS cleanup work, not end-products.**
  A successful audit cycle produces zero 🔴 rows. The files
  themselves become less useful as data quality improves; they
  should eventually be archived in a `claude-docs/audits/archive/`
  or similar once a row is clean.

## Implementation

Files changed/created:

- `scripts/audit_row.py` (848 lines) — schema-aware parser,
  diff engine, markdown renderer. Three schema detectors
  (A/B/C), `SPECIES_ALIASES` dict, `ANNUAL_SPECIES` set,
  `DEAD_MARKERS` set, duplicate-tab detection,
  boundary-shift detection, section-by-section comparison
  with ✓/⚠️/🔴/annual/ℹ️/new markers, summary + field-check
  list + new-rows list.

- `scripts/upload_kb_audit_files.py` (226 lines) — Python
  helper that reads 5 audit files, uploads them to the KB
  Drive folder via the new `upload_file` action, creates KB
  sheet entries with summaries. Flags: `--dry-run`,
  `--list-only`, `--skip-entries`.

- `claude-docs/audits/README.md` — process doc explaining
  the three-storage-locations design and pointing at this
  ADR for rationale.

- `.gitignore` — adds `fieldsheets/audits/` so audit outputs
  are never committed.

Ran once against each P2 row:

| Row | ✓ | ⚠️ | 🔴 | ℹ️ | new | Notes |
|---|---|---|---|---|---|---|
| P2R1 | 8 | 3 | 0 | 29 | 31 | Clean — 6-month stale sheet |
| P2R2 | 66 | 23 | 11 | 2 | 8 | Strong baseline, 11 🔴 to verify |
| P2R3 | 48 | 52 | 22 | 34 | 7 | CRITICAL duplicated-tab issue |
| P2R4 | 83 | 2 | 16 | 95 | 1 | End-of-row mass death sections |
| P2R5 | — | — | — | — | — | Reference from prior session |

Commit SHA at time of writing: _filled in when committed_

## Open questions

- **Claire-facing skill for her Claude** — Agnes mentioned wanting
  a dedicated skill that loads when Claire opens an audit,
  prompts her to review each 🔴 row, and calls `archive_plant` /
  `update_inventory` / `create_plant` on confirmation, then
  writes an acknowledgement back into the audit file. Scoped
  but not built in this session. Will need its own ADR once
  the first Claire-with-Claude audit review happens and we see
  what the conversational pattern looks like.

- **P1 row audits** — Paddock 1 uses yet another schema (the
  2025 SPRING.P1 sheets) and a different species mix (mostly
  annuals). Requires a schema D extension to `audit_row.py`.
  Deferred.

- **Audit re-run cadence** — once the 🔴 list is cleaned for a
  row, how do we re-audit to confirm? Monthly? After every
  farmOS import? We don't know the right cadence yet. Agnes
  to decide after first full cleanup cycle completes.
