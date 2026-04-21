# Session 2026-04-21 — P2R4 empty-page bug reconciliation

## One-line summary

Three P2R4 QR pages (`.52-62`, `.62-72`, `.72-77`) were showing "0 plants counted" while the sections contained 31/11/11 real plants. Root cause: a year-typo (`2026-12-18` vs `2025-12-18`) on 24 farmOS inventory logs silently made them future-dated, so farmOS ignored their `reset` adjustments and the computed `asset.inventory` field stayed at 0. Fixed by reconciling against Claire's 2026FEB-P2R4 spreadsheet — 38 farmOS writes total.

## Timeline

1. **Discovery** — Agnes asked which P2 rows had no recorded plants. First pass said 4 empty sections; Agnes countered from field observation that P2R4.62-72 / .72-77 / .52-62 were also empty. Investigation showed farmOS listed 5/7/12 plants in those sections with `inventory_count: 0` on every asset — contradiction between "plants exist" and "inventory is zero".

2. **Evidence hunt** — `query_logs` returned 24 inventory observation logs, all timestamped `2026-12-18T14:00:00Z` (~8 months in the future), all `inventory_adjustment: reset` with positive counts summing to 31/11/11. No transplanting/seeding logs. Team memory empty for the sections. Kacper submitted 3 pending observations on those sections today (2026-04-21) mentioning upright cow-pea plants → live field confirmation.

3. **Raw JSON:API dive** — confirmed the `2026-12-18` timestamp is literally stored (not a display bug). All 24 logs created in a 72-second batch on Sat 7 March 2026 at 22:37–22:38 AEDT — single-shot import. Root cause: farmOS only applies `reset` adjustments when `timestamp <= now`; future dates are silently skipped.

4. **Spreadsheet cross-check** — Claire's 2026FEB-P2R4 Excel has col E header `2026-12-19` (Last Inventory) and col I header `2026-03-06` (New TOTAL). All 24 farmOS log *values* match the Mar 6 "New TOTAL" column exactly. The Mar 7 importer took values from col I but timestamp from col E header — and Claire's col E header was a year typo for `2025-12-19`. Two-layer bug: typo in spreadsheet, importer picking wrong column for the date.

5. **Reconciliation strategy** — Agnes chose the split approach: Dec 18 2025 inventory = baseline (what was there ~2.5 months post-Oct-planting), Mar 6 2026 transplanting = the 6 March additions, Mar 6 2026 post-planting inventory = new total. Preserves plant-maturity integrity (old plants dated Dec, new plants dated Mar).

6. **Execution** — 24 log PATCHes + 9 new transplanting logs + 5 new post-planting inventory logs = 38 writes. Rollback plan captured in `/tmp/p2r4_rollback.json`.

7. **Secondary bug surfaced mid-fix** — new `quantity--standard` records created via JSON:API were missing `inventory_asset` and `units` relationships on the qty itself. Without them, farmOS inventory computation can't walk back from qty to asset. PATCHed 5 qty records to add the relationships + taxonomy term, then PATCHed the 5 affected plant assets with a no-op to force computed-field refresh. All 24 assets then showed correct inventory.

8. **Regenerated pages** — `export_farmos.py --sections-json` → `generate_site.py` → committed + pushed. Commit [`9e61f62`](https://github.com/agnesfa/firefly-farm-ai/commit/9e61f62). GitHub Pages auto-deploy will pick it up.

## What landed

- 38 farmOS writes — see `/tmp/p2r4_fix_plan.json` and `/tmp/p2r4_rollback.json`
- 3 QR section pages now render correct counts: 31/11/11 plants across 12/5/7 species
- 38 log-detail HTML pages regenerated (new transplanting + inventory logs)
- Memory: `reference_farmos_inventory_quirks.md` — the three gotchas
- Memory: `MEMORY.md` hard-won lesson #11 added
- Follow-up task chip spawned: MCP inventory-write audit (running async, separate session)

## What's still pending

- The spawned audit (Python + TS MCP tools × 3 quirks: inventory_asset, future-ts guard, asset-touch)
- Cheap one-time audit: grep farmOS for other logs with `timestamp > 2026-04-21` (possible copies of this bug in other sections / other imports)
- Kacper's 3 pending observations on P2R4.52-62/.62-72/.72-77 still need review → imports
- 2026FEB-P2R4 spreadsheet has the year typo in its col E header — needs fixing at source to prevent repeat if re-imported

## Not done today (carry-over from 2026-04-20 anchor)

- Pre-governance review of James's 8 logs from 2026-04-20 AM
- Governance session itself (ADR 0006 / 0007 / 0008+amendment ratification)
- Everything else on the 2026-04-20 priorities list

Today was consumed by this discovery — planned work deferred.

## Refs

- Claire's spreadsheet: `~/Downloads/2026FEB-P2R4-Inventory-&-Next-Planting (2).xlsx`
- Fix plan + rollback: `/tmp/p2r4_fix_plan.json`, `/tmp/p2r4_rollback.json`
- Site commit: `9e61f62`
- Memory file on the quirks: `~/.claude/projects/-Users-agnes-Repos-FireflyCorner/memory/reference_farmos_inventory_quirks.md`
