# Field-sheet vs farmOS reconciliation audits

This folder documents the **process and tooling** for reconciliation audits.
The generated audit `.md` files themselves live **outside the codebase**:

- **Local working copies**: `fieldsheets/audits/` (gitignored — regenerate
  on demand via `scripts/audit_row.py`)
- **Shared with Claire**: Google Drive folder "Firefly Corner -
  Knowledge Base" → subfolder `data-quality/`, plus KB sheet entries that
  her Claude session can read via `search_knowledge`

Audit files are **not** in the codebase by design. They're generated
outputs from committed tooling (`scripts/audit_row.py`) and committed
source data (`fieldsheets/*.xlsx`, also gitignored per existing convention).
Sharing with the team happens through the Knowledge Base, not through a git
pull.

This README holds the process doc. ADR 0003 in `claude-docs/adr/` holds
the design rationale for the audit tool and its storage choices.

## Intent

Give Agnes + James a concrete punch-list of discrepancies to verify on the
ground *before* looping Claire in — so she sees a curated set of confirmed
findings rather than raw noise.

## Workflow

1. **Generate** — `python scripts/audit_row.py <ROW> --sheet <xlsx> --farmos <json> --output <md>`.
   The sheet parser handles three schemas (A = 2026 Feb inventory,
   B = 2026 Mar 15 farmOS-snapshot, C = 2025 Spring renovation). The farmOS
   JSON is a one-time snapshot fetched via the MCP tools.
2. **Field verify** (Agnes or James) — walk each `🔴` row, confirm the
   plant state, and either:
   - archive the ghost asset in farmOS, or
   - correct the farmOS count, or
   - record a new planting/seeding log for missed entries.
3. **Hand to Claire** — once the 🔴 list is cleaned, Claire reads the audit
   in her Claude session and reviews the `new` / `⚠️` / `ℹ️` entries
   conversationally (no spreadsheet round-trip).

## Markers

| Marker | Meaning |
|---|---|
| **✓** | Sheet baseline matches farmOS current count exactly |
| **⚠️** | Small drift (±1 or ±2) — likely natural gain/loss since the sheet was written |
| **🔴** | Significant discrepancy — sheet shows plants that aren't in farmOS, or farmOS shows a count far below the sheet. These need a field check |
| **annual** | Sheet had plants, farmOS has 0 — expected end-of-cycle for annuals (tomato, zucchini, cabbage, etc.). Not a data issue |
| **ℹ️** | Claire listed the species without a count — either a placeholder row or a planning intention |
| **new** | Plant exists in farmOS but not in the sheet — added since the sheet was written (via QR observation, transcript import, or direct farmOS edit) |

## Current audit set (generated 2026-04-15)

| Row | Sheet file | Schema | Sections audited | ✓ | ⚠️ | 🔴 | Notes |
|---|---|---|---|---|---|---|---|
| **P2R1** | `fieldsheets/2025.SPRING.P2R1.0-22M-RENOVATION-v2.xlsx` | C (2025 renovation) | 4 | 8 | 3 | 0 | Clean — sheet is 6 months stale, many ℹ️ placeholder rows |
| **P2R2** | `fieldsheets/2026MAR15-P2R2-Inventory.xlsx` | B (farmOS-snapshot) | 7 | 66 | 23 | 11 | Good alignment; 11 🔴 to field-verify |
| **P2R3** | `fieldsheets/2026FEB-P2R3-Inventory-&-Next-Planting-v2.xlsx` | A (v2 inventory) | 8 | 48 | 52 | 22 | **CRITICAL:** tabs `P2R3.40-50` and `P2R3.50-62` are identical duplicates — "split from 41-63" never actually done. Many 🔴 rows in those two sections are false-positives |
| **P2R4** | `fieldsheets/2026FEB-P2R4-Inventory-&-Next-Planting.xlsx` | A (v2 inventory) | 11 | 83 | 2 | 16 | Cleanest match. 🔴 concentrated in end-of-row mass-death sections 52-62 / 62-72 / 72-77 |
| **P2R5** | (manually authored from April 13 session) | n/a | 9 | n/a | n/a | 4 key issues | Reference audit from prior session. 4 Koala Day native species never imported; P2R5.8-14 and .22-29 "invisible" gap sections with 93 unregistered plants; 5 unlogged transplants in .8-14; untracked tree die-off in .55-66/.66-77 |

## Known parser caveats

1. **Sheet baselines are historical snapshots.** P2R1 sheet is Spring 2025
   (7 months old), P2R3 sheet is Nov 2025 (5 months old), P2R4 sheet is
   Feb 2026 (2 months old), P2R2 sheet is March 15 2026 (1 month old).
   Long-baseline rows will naturally show drift that isn't a data bug.

2. **Species naming across schemas is not harmonised.** The script uses a
   small `SPECIES_ALIASES` dict to map variants (e.g. "Basil (Thai)" →
   "Basil - Perennial (Thai)"). When a new alias surfaces, add it to the
   dict in `scripts/audit_row.py` and re-run the audit.

3. **P2R3.40-50 / P2R3.50-62 false positives.** See the CRITICAL flag
   above. Any 🔴 in these two sections should be re-verified against the
   combined 40-62 range before action.

4. **Gap sections with no spreadsheet tab** (e.g. P2R5.8-14, P2R2.26-28,
   P2R3.21-26, P2R4.2-6 / 14-20 / 49-52) exist in farmOS because an older
   row layout had an "under 2m" open-cultivation section between the tree
   sections. These are surfaced in the structural findings at the top of
   each audit.

## Next action

Agnes + James: walk the 🔴 rows section by section, starting with P2R2
(smallest 🔴 list, strongest baseline match). For each row, confirm on the
ground and either archive, correct, or log. When the 🔴 counts drop to
zero, the audits are ready for Claire.
