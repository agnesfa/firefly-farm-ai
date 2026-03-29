# farmOS Pagination Bulletproof Fix — Implementation Plan

> Created: March 29, 2026
> Status: Planned (ready for implementation)
> Priority: HIGH — this has caused data corruption in 3 separate incidents

---

## 1. DIAGNOSIS

farmOS JSON:API pagination has a hidden ~250 result ceiling. When using CONTAINS filters, `links.next` disappears after ~5 pages of 50. Archived records consume pagination slots even with `status=active` filter.

### Three Pagination Patterns in Use

| Pattern | Method | Approach | Vulnerable? |
|---------|--------|----------|-------------|
| **A: Offset-based** | `fetchAllPaginated` | Explicit `page[offset]` stepping, stops on empty page | **Mostly safe** (but archived slots can cause undercounts) |
| **B: links.next (plants)** | `fetchPlantsContains` | Follows `links.next` only | **VULNERABLE** — silently truncates at ~250 |
| **C: links.next (logs)** | `fetchLogsContains` | Follows `links.next` only | **VULNERABLE** — silently truncates at ~250 |

### Incident History

1. **fix_taxonomy.py** — `iterate()` missed terms with 200+ entries
2. **export_farmos.py** — Missing logs when exporting 900+ entries
3. **cleanup_nursery.py** — CONTAINS filter returned 85/90 assets, causing duplicate creation

### High-Risk Callers

| Caller | Risk | Why |
|--------|------|-----|
| `query_sections` (all plants fetch) | **HIGH** | 635+ active plants, growing |
| `getPlantAssets(species)` | **HIGH** | Common species across all sections |
| `getLogs(sectionId)` | **HIGH** | Busy sections with many log types |
| `getAllPlantTypesCached` | **HIGH** | 272 terms, approaching cap |
| `reconcile_plant_types` | **HIGH** | Fetches all taxonomy terms |

### Write Safety Assessment

Good news: all write tools that check existence before creating use `fetchByName` (direct name query), which is **unaffected by pagination**. The vulnerability is in **read completeness** — inventory counts, log queries, and import_observations Case C plant lookups.

---

## 2. STRATEGY: Two-Tier Approach

### Tier 1: Fix CONTAINS methods to use offset-based pagination

Switch `fetchPlantsContains` and `fetchLogsContains` from `links.next` to explicit `page[offset]` stepping (matching the pattern `fetchAllPaginated` already uses). Keep CONTAINS filter parameters but don't depend on `links.next`.

### Tier 2: Add stable sort + safety caps

- Add explicit `sort=name` to plant queries, `sort=-timestamp,name` to log queries
- Add `maxPages` safety parameter (default 20 = 1000 items) to prevent infinite loops
- Log warnings when result sets exceed 200 items

---

## 3. IMPLEMENTATION STEPS

### Step 1: Extract common offset-pagination helper

Both clients (Python + TypeScript) need a shared `_fetchPaginatedOffset(baseUrl, mergePerPage?)` method that:
1. Builds URL with `page[offset]=N&page[limit]=50`
2. Increments offset by 50 each page
3. Stops when empty page returned
4. Deduplicates by UUID
5. Respects `maxPages` safety cap

**TypeScript** (`farmos-client.ts`): Extract from `fetchAllPaginated` (lines 174-213)
**Python** (`farmos_client.py`): Extract from `fetch_all_paginated` (lines 175-246)

### Step 2: Rewrite CONTAINS methods to use offset pagination

**`fetchPlantsContains` / `_fetch_plants_contains`:**
- Keep the CONTAINS filter URL construction
- Replace `links.next` loop with offset stepping via the new helper
- Add `&sort=name` for stable ordering

**`fetchLogsContains` / `_fetch_logs_contains`:**
- Same offset approach
- Keep the quantity merge step (runs per-page)
- Add `&sort=-timestamp,name` for stable ordering

### Step 3: Add fetchByName fallback in import_observations

For Case C (inventory update), when `getPlantAssets(section, species)` returns 0 results, try a direct `fetchByName('asset/plant', expectedName)` before reporting "not found". Catches edge cases where CONTAINS still fails.

### Step 4: Optimize query_sections

When `row` filter is provided, use per-row CONTAINS instead of fetching ALL 635+ plants. For unfiltered case, the full fetch is unavoidable but safe with offset pagination.

### Step 5: Increase page size for taxonomy

`getAllPlantTypesCached`: use `page[limit]=100` instead of 50 for taxonomy fetches (272 terms = 3 pages instead of 6).

---

## 4. FILES TO CHANGE

| File | Changes |
|------|---------|
| `mcp-server-ts/.../farmos-client.ts` | Extract `_fetchPaginatedOffset`, rewrite `fetchPlantsContains` + `fetchLogsContains` |
| `mcp-server/farmos_client.py` | Same refactor in Python |
| `mcp-server-ts/.../import-observations.ts` | Add `fetchByName` fallback for Case C |
| `mcp-server-ts/.../query-sections.ts` | Optimize per-row CONTAINS |
| `mcp-server-ts/.../farmos-client.test.ts` | Add offset-based CONTAINS tests |
| `mcp-server/tests/test_farmos_client.py` | Same tests in Python |

---

## 5. NEW TESTS

### Python (`test_farmos_client.py`):
1. `test_fetch_plants_contains_uses_offset_pagination` — Mock 3 pages, no `links.next` after page 1, verify all returned
2. `test_fetch_logs_contains_uses_offset_pagination` — Same with quantity merge
3. `test_fetch_plants_contains_stable_sort` — Verify URL includes `&sort=name`
4. `test_fetch_logs_contains_stable_sort` — Verify `&sort=-timestamp,name`
5. `test_fetch_contains_maxpages_safety` — Verify stops at maxPages

### TypeScript (`farmos-client.test.ts`):
Same 5 tests.

### Import workflow (`import-observations.test.ts`):
1. `test_case_c_fallback_on_empty_contains` — Verify fetchByName fires

---

## 6. DOCUMENTATION UPDATES

### CLAUDE.md — Architecture Decision #16:
> **Pagination: offset-based for all collection fetches.** farmOS JSON:API `links.next` is unreliable beyond ~250 results. All CONTAINS and full-collection queries use explicit `page[offset]` with stable `sort` ordering. Write tools use `fetchByName` (direct name query, unaffected by pagination) for existence checks.

### MEMORY.md — Key Technical Patterns:
> ### Pagination safety (March 29)
> - All CONTAINS fetchers use offset-based pagination (not links.next)
> - Explicit sort ordering for stable pagination (name for assets, -timestamp,name for logs)
> - Write existence checks always use fetchByName (direct, never paginated)
> - import_observations Case C has fetchByName fallback
> - query_sections uses per-row CONTAINS when row filter provided
> - maxPages=20 safety cap on all paginated fetchers

---

## 7. GOLDEN RULE

> **Never trust a CONTAINS query result set for completeness. Use it for reads. Use `fetchByName` for existence checks before any write operation.**
