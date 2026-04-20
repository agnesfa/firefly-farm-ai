# Session Audit — 2026-04-18 → 2026-04-20

**Purpose:** single source of truth for what happened in this 3-day
session (Agnes's P2R2 walk → WWOOFer onboarding → cycle-breaking
infrastructure). Read this to resume cleanly in the next session.

**Span:** Saturday 2026-04-18 (Agnes's field walk import) → Monday
2026-04-20 (Phase 3a/3b write-time enforcement).

**Commits (all pushed to `main`):**

| Commit | Date | Purpose |
|---|---|---|
| `1dc79b9` | 04-18 | Clean-slate pass + governance package (ADRs 0006/0007, James protocol) |
| `8fd3062` | 04-18 | Re-regen with all 27 field photos |
| `d8881c4` | 04-19 | `plantnet_verify` Origin header + import idempotency (ADR 0007 Fix 2) |
| `cac22f3` | 04-20 | ADR 0008 Phase 2A cleanup (I3 + I4 + I5) |
| `08a901c` | 04-20 | `export_farmos.py` plant_type pagination fix (Rose Apple unblock) |
| `2626c82` | 04-20 | Repo-wide pagination migration + tier-aware I5 re-run |
| `fe8989d` | 04-20 | Revert 17 species tier-1 → stock |
| `ec3184b` | 04-20 | **URGENT** OBSERVE_ENDPOINT regression fix (Kacper unblock) |
| `f9d2d6e` | 04-20 | Post-gen assertion guards against OBSERVE_ENDPOINT regression |
| `7b07a5b` | 04-20 | Phase 3a + 3b write-time enforcement (I4 dedup + I5 tier gate) |

---

## 1. Session summary (one paragraph)

Agnes did the P2R2 field walk herself (24 observations + photos) after
Leah left. Discovered PlantNet's QR-page integration was silently
broken (trailing slash in CORS allowlist), fixed it, then re-attached
Leah's 2026-04-14 photos to their farmOS logs. During import, found
the Railway batch importer "lied" about failures — it actually
completed writes but timed out the MCP response, causing duplicates on
retry. That triggered a deeper audit which exposed systemic defects:
section_notes fanned onto every plant log, section-level multi-plant
photos promoted as species references, and a pagination bug silently
dropping 36+ plant_types from every site regen. We wrote three ADRs
(0006 FASF, 0007 Import Reliability, 0008 Observation Record
Invariant) and a repo-wide pagination helper, ran a full P2 audit
(1145 violations), and cleaned up 160 errors in Phase 2A. Then shipped
Phase 3a + 3b — write-time dedup + tier-aware species-reference
promotion in both TS and Python MCP servers. Fixed two urgent
regressions along the way (OBSERVE_ENDPOINT blanked for Kacper, Rose
Apple thumbnail missing). Phase 3c/3d deferred with full design
documented.

## 2. What shipped (done + deployed)

### 2.1 Code changes in the MCP servers

| Component | Change | Tests |
|---|---|---|
| `mcp-server/plantnet_verify.py` | Origin header on every PlantNet request | 22/22 pass |
| `mcp-server-ts/.../plantnet-verify.ts` | Origin header + regression test | 3 new tests |
| `mcp-server/server.py` (import) | ADR 0007 Fix 2 idempotency | 278/278 pass |
| `mcp-server-ts/.../import-observations.ts` | ADR 0007 Fix 2 idempotency | 222/222 pass |
| `mcp-server/server.py` (photo) | Phase 3a dedup + Phase 3b tier gate | 278/278 pass |
| `mcp-server-ts/.../photo-pipeline.ts` | Phase 3a dedup + Phase 3b tier gate | 222/222 pass |
| `mcp-server-ts/.../farmos-client.ts` | `getRaw()` + `patchRelationship()` helpers | — |

### 2.2 Scripts in `scripts/` — reusable automation

| File | Purpose |
|---|---|
| `scripts/_paginate.py` | **Shared pagination helper.** Offset-based, stable-sort. All new scripts must use this instead of `links.next`. |
| `scripts/validate_observations.py` | ADR 0008 validator + audit tool. Run: `--scope P2` or `--section X`. |
| `scripts/cleanup/cleanup_i5_plant_type_references.py` | Tier-aware reference photo promotion. |
| `scripts/cleanup/cleanup_i3_section_notes.py` | Strip fanned-out section_notes + create section-level logs. |
| `scripts/cleanup/cleanup_i4_photo_duplicates.py` | Dedup same-content photo refs on logs. |
| `scripts/cleanup/revert_tier1_to_stock.py` | Move tier-1 section-level photos back to stock. |
| `scripts/attach_leah_photos.py` | One-off — re-attached Leah's 2026-04-14 photos (done). |

### 2.3 Scripts retrofitted to use `_paginate.py`

All 9 scripts that previously paginated via `links.next`:
`export_farmos.py`, `validate_observations.py`, all 3 cleanup scripts,
`audit_species_photos.py`, `fix_taxonomy.py`,
`generate_nursery_pages.py`, `cleanup_nursery.py`.

### 2.4 Other script fixes

| File | Change |
|---|---|
| `scripts/generate_site.py` | Loads `.env` at import; `--observe-endpoint` defaults to `$OBSERVE_ENDPOINT`; post-gen assertion fails loud if any observe page has empty endpoint. |
| `scripts/export_farmos.py` | Two pagination fixes: `fetch_species_photo_urls` inline + `_fetch_contains` offset-based. |

### 2.5 Data cleanups (applied to live farmOS)

| Action | Count | Notes |
|---|---:|---|
| Plant-logs stripped of leaked section_notes | 114 | Agnes's + Claire's historical inventories |
| Section-level logs created (no asset_ids) | 7 | Not yet rendered on QR pages (needs Phase 3c) |
| plant_type references patched (collapse/promote) | 48 | 28 upgraded to field photo, 20 collapsed to single |
| Tier-1 section-level photos reverted to stock | 17 | Per Agnes decision — misleading shared photos |
| Duplicate photo refs removed | 9 | Across 8 logs |
| Ghost plants archived | 1 | P2R2.9-16 Ginger |
| Pending logs closed in clean-slate | 17 | 9 review + 8 transplant |
| Observations imported (Agnes's walk) | 24 of 24 | 1 rejected as duplicate; all confirmed in farmOS |
| Photos attached from Agnes's walk | 27 | All on matching logs / plant assets |
| Leah photo re-attachments (from 2026-04-14) | 18 | Split P2R5.0-8 + P2R5.29-38 |
| Reference photos promoted from Leah's walk | 7 | Parsley, Sunflower, Okra, Mulberry, Papaya, Thai Basil, Wattle-Cootamundra, Jacaranda |

### 2.6 Governance documentation

| Document | Status |
|---|---|
| `claude-docs/cross-agent-consistency-2026-04-18.md` | Written, ratified in spirit |
| `claude-docs/adr/0006-agent-skill-framework.md` | **Status: proposed** — awaits governance session |
| `claude-docs/adr/0007-import-pipeline-reliability.md` | **Status: proposed** — Fix 2 shipped, others queued |
| `claude-docs/adr/0008-observation-record-invariant.md` | **Status: proposed** — validator built, Phase 2A done |
| `claude-docs/adr/0008-addendum-phase-3-write-time.md` | **Status: implementation in progress** |
| `claude-docs/james-claude-session-protocol.md` | Written — **not yet pasted into James's Claude Desktop** |
| `claude-docs/skills/review_observations.md` | Skill spec drafted — not yet a KB entry |

### 2.7 Live state for WWOOFers

- 2 WWOOFers started 2026-04-19 (Kacper + 1 other)
- Kacper's submission was blocked by OBSERVE_ENDPOINT regression on 04-20 → fixed same day
- QR pages deployed, GitHub Pages live at `https://agnesfa.github.io/firefly-farm-ai/`
- 477 active plants in P2 across 39 sections
- Pending queue: 0 logs

### 2.8 Memory files saved (all under `~/.claude/.../memory/`)

| File | Content |
|---|---|
| `reference_plantnet_cors.md` | PlantNet API key allowlist — no trailing slash |
| `feedback_reference_photo_highest_quality.md` | Field beats stock; human-in-loop decides |
| `feedback_plantnet_verification_policy.md` | Not sole authority; threshold tune first |

---

## 3. What's queued / deferred (must NOT be lost)

### 3.1 ADRs awaiting ratification

Three ADRs are in `proposed` state. Ratify at the **governance
session** (originally scheduled per Agnes's Apr 15 priorities):

- **ADR 0006 — Firefly Agent Skill Framework (FASF)** —
  shared-behaviour layer via KB entries. Day-one skills:
  `session_open`, `ingest_knowledge`, `review_assignment`,
  `record_fieldwork`, `per_row_review`. Status: designed,
  not yet implemented.
- **ADR 0007 — Import Pipeline Reliability** — 6-fix stack.
  Fix 2 (idempotency) shipped. Fix 1 (Apps Script server-side filter),
  Fix 3 (async job queue), Fix 4 (post-write verify), Fix 5 (duplicate
  detection), Fix 6 (batch-size limit) still pending.
- **ADR 0008 — Observation Record Invariant** — seven invariants
  (I1–I7) + validator. Validator built; Phase 2A cleanup done; Phase
  3a/3b enforcement shipped; Phase 3c/3d deferred (see below).

### 3.2 Phase 3c — section vs plant log routing (ADR 0008)

**Problem:** inventory-mode submissions with `section_notes` still
get fanned out by the import pipeline (one log per species in the
inventory, each carrying the section_notes text).

**Required fix** (full spec in
`claude-docs/adr/0008-addendum-phase-3-write-time.md`):

1. `import-observations.ts` + `server.py`: on inventory submissions,
   create ONE section-level log carrying the section_notes
   (`asset_ids=[]`, `location_ids=[section_uuid]`) plus per-plant logs
   without section_notes text.
2. `generate_site.py`: render section-level observations in a
   dedicated block on the section QR page so they're visible.

**Estimated scope:** 1 session (half-day). Schema design + atomic
implementation + tests.

### 3.3 Phase 3d — post-write validator integration (ADR 0007 Fix 4 proper)

**Problem:** the validator runs on demand via a script. ADR 0008
specifies it should run after every log-creating write.

**Required fix:**

1. Extract invariant-check functions from
   `scripts/validate_observations.py` into a library
   (`mcp-server/observation_invariants.py`) + TS mirror.
2. Integrate into `import_observations`, `create_plant`,
   `create_observation`, `create_activity`, `archive_plant`: after
   each write, re-read + validate. Auto-correct or flag.
3. Expose as MCP tools: `audit_observation_records(scope) → report`,
   `validate_observation_record(log_id) → violations`.

**Estimated scope:** 1 session. Best done AFTER Phase 3c so we
encode correct log shape, not the current wrong one.

### 3.4 Phase 2B — remaining audit backlog from ADR 0008

Errors still in the audit report but lower-priority:

- **I6 missing InteractionStamp** on 71 post-Apr-1 logs — mechanical
  backfill.
- **I1 log-type mis-classification** — 28 observation logs contain
  activity-language (`seeded`, `chop and drop`, `transplanted`,
  `harvested`). Needs human case-by-case review.
- **16 species stuck at tier-1** multi-plant section photos (no stock
  available, no plant-specific photo yet): Achiote, Curry Leaf,
  Dianella, Sunn Hemp + 2 archived. Will resolve when field photos
  are taken during WWOOFer walks.
- **14 species stock-only, no field photo yet** (different set —
  Amaranth, Amla, Arrowroot, Blackberry, Borage, Capsicum (Red),
  Chilli, Citrus (Yuzu), Eggplant, Eucalypt-Gum (Generic), Jaboticaba,
  Kumquat, Mango, Raspberry, Strawberry, Yarrow (White)). Same —
  resolve via field photography.
- **Pear (Nashi)** multi-valued image — collapsed during I5 re-run.
  **Resolved.**

### 3.5 Live data quality flags

These were surfaced during cleanup and need a human field check at
some point:

- **Coriander log `fc5f01ed` in P2R5.29-38** — Agnes flagged the
  attached photo as NOT coriander. Plant asset retained pending
  field re-ID.
- **Duplicate chop-and-drop activities in P2R3.50-62** — sessions 82
  (Mar 21) and 84 (Mar 22) both wrote the same seeding + chop-and-drop
  activities. Needs merge.
- **James's pre-Apr-1 logs** — 838 "info" violations in audit,
  mostly missing InteractionStamps. Legacy — accept as historical
  unless we decide otherwise.

### 3.6 Team-coordination items

- **James needs to paste `claude-docs/james-claude-session-protocol.md`
  into his Claude Desktop config.** Until he does, his Claude won't
  check pending logs or cite KB entry_ids in session memory.
- **Agnes to check** that the ADR 0006 FASF skill library (KB entries
  with `category = "agent_skill"`) should be seeded as soon as FASF is
  ratified.
- **Governance session** — originally scheduled per Apr 15 priorities.
  Now has three ADRs waiting: 0006, 0007, 0008.

### 3.7 Carried from previous sessions (still open)

From the 2026-04-15 priorities list:

- `system_health()` optimisation — 51.6s (close to MCP 60s timeout).
  Target <20s. Not touched this session.
- Report stale session issue to `mcp-remote` maintainers.
- Wire `mcp_reliability` from TS server connection stats.
- Migrate farmOS auth to framework `PlatformAuthHandler` (per
  Lesley's recommendation).

---

## 4. How to resume next session

**Start by running these three:**

```
# 1. Live state snapshot
system_health()
get_farm_overview()
read_team_activity(days=7, only_fresh_for="Agnes")

# 2. Invariant health (ADR 0008)
python scripts/validate_observations.py --scope P2 --out /tmp/audit.md
# Compare to the Apr 20 baseline (72 errors post-Phase-2A).
```

**Decide priority** among:

1. Phase 3c (section log routing) — blocks Phase 3d, ~half-day.
2. Governance session (ratify ADR 0006/0007/0008) — Agnes-driven,
   pre-reading already written.
3. FASF skill library seeding in KB — can start once 0006 ratified.
4. I1/I6 backlog cleanup — low urgency, mechanical.
5. `system_health()` optimisation — pre-existing priority.
6. WWOOFer walk data review — run validator, check for new
   violations, cleanup if needed.

**Key files / pointers the next session needs:**

- This document (session audit).
- `claude-docs/adr/0008-addendum-phase-3-write-time.md` — Phase 3c/3d
  design.
- `claude-docs/cross-agent-consistency-2026-04-18.md` — the "why" for
  ADR 0006/0008.
- `scripts/_paginate.py` docstring — mandatory pagination pattern.
- `scripts/validate_observations.py` — run any time to check
  invariant health.
- Memory: `reference_plantnet_cors.md`,
  `feedback_reference_photo_highest_quality.md`,
  `feedback_plantnet_verification_policy.md`.

---

## 5. Hard-won lessons worth re-reading

1. **Every `links.next` pagination in the repo is a time bomb** if the
   collection can exceed ~250 items. Default to offset + stable sort.
   Shipped: repo-wide migration via `scripts/_paginate.py`.
2. **Config defaults must fail loud.** An env-backed flag defaulting
   to `""` silently broke every QR submission (OBSERVE_ENDPOINT). Fix:
   read env by default AND assert populated at end of generation.
3. **Retries must be idempotent.** A silent success + client retry
   produced 9 duplicate photo refs. Fix: `import_observations` now
   treats already-imported as success not error (Fix 2). Dedup at
   photo upload (Phase 3a).
4. **Classifier granularity matters.** Treating `{section}_plant_` and
   `{section}_section_` as equally "field photos" caused section-level
   multi-plant photos to pollute species pages. Fix: four-tier
   classifier in `photo-pipeline.ts` + `_field_photo_tier` in
   `server.py`.
5. **Cleanup without enforcement = Groundhog Day.** ADR 0008 Phase 2A
   cleaned up 160 errors; Phase 3a/3b writes the gate so they don't
   come back. The 114 I3 errors, 9 I4 duplicates, and 38 I5 multi-
   valued references we fixed were all downstream of write-path
   defects. Fixing them without fixing the write path = same defects
   next week.
6. **Human-in-loop on reference photos.** Don't let the agent pick a
   species reference from ambiguous options silently. Phase 3b now
   refuses tier ≤ 1 automatically — escalation to human review is the
   correct behaviour.

---

*Session end. Next chapter: governance session or Phase 3c — Agnes's call.*
