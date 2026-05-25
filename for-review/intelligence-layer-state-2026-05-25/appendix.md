# FireflyCorner → Foundry: extended appendix to the 2026-05-25 memo

**Author:** Agnes / Claude (FireflyCorner session)
**Companion to:** [`memo.md`](memo.md)
**Status:** broader intelligence-layer surface for Foundry consideration

The original memo focused tightly on the five field-walk issues from
2026-05-25. This appendix pulls in:

1. The root-cause analysis Agnes asked for on the duplicate
   InteractionStamp bug surfaced while merging the Geranium duplicate.
2. A consolidated view of related issues across the last ~10 sessions —
   from `claude-docs/`, ADRs 0001–0011, `MEMORY.md` resume anchors, the
   open backlog, and pinned project memories.

The aim is to give the Foundry a complete picture of the intelligence
layer's actual operating envelope, not just the slice of it that
surfaced this morning. Many backlog items are not direct intelligence-
layer issues — but most are *indirectly* gated by the same architectural
gaps. Where an item is orthogonal we say so explicitly.

A compact backlog inventory at the end maps each known item to its
intelligence-layer relevance (direct / indirect / orthogonal).

---

## Part I — Root cause: duplicate InteractionStamp on `update_inventory` logs

### Symptom

The Geranium-merge inventory log [`7a176508`](https://margregen.farmos.net/log/7a176508)
created via `update_inventory` carries **two** stacked InteractionStamps:

```
Inventory update: Asset merge 2026-05-25: subsumed duplicate asset…
[ontology:InteractionStamp] initiator=Claude_user | role=manager | channel=claude_session
  | executor=farmos_api | action=updated | target=observation | outcome=success
  | ts=2026-05-25T05:12:54.890Z | related=25 APR 2025 - Geranium - P2R3.2-9
[ontology:InteractionStamp] initiator=Claude_user | role=manager | channel=claude_session
  | executor=farmos_api | action=created | target=observation | outcome=success
  | ts=2026-05-25T05:12:56.380Z | related=Geranium,P2R3.2-9
```

Note: the two stamps differ on `action` (`updated` vs `created`) and on
`related` granularity (full asset name vs `species,section`). Same outcome,
same actor, ~1.5 s apart.

### Root cause

The bug is in the **tool-delegation pattern**. In `mcp-server-ts/plugins/farm-plugin/src/tools/`:

[`update-inventory.ts` lines 17–25](../../mcp-server-ts/plugins/farm-plugin/src/tools/update-inventory.ts#L17-L25):

```typescript
const stamp = buildMcpStamp('updated', 'observation', { relatedEntities: [params.plant_name] });
const updateNotes = appendStamp(rawNotes, stamp);     // ← stamps once
return createObservationTool.handler(
  { plant_name: params.plant_name, count: params.new_count, notes: updateNotes, date: today },
  extra,
);
```

[`create-observation.ts` lines 43–44](../../mcp-server-ts/plugins/farm-plugin/src/tools/create-observation.ts#L43-L44):

```typescript
const stamp = buildMcpStamp('created', 'observation', { relatedEntities: [formatted.species, sectionId].filter(Boolean) });
const stampedNotes = appendStamp(params.notes ?? '', stamp);    // ← stamps again, unconditionally
```

`create_observation` calls `appendStamp` on its input notes without
checking whether the notes already contain a stamp. The
[`hasStamp(notes)` helper](../../mcp-server-ts/plugins/farm-plugin/src/helpers/interaction-stamp.ts#L118)
exists and would catch this — it's just not used as a guard.

The pattern is a generic delegation hazard: any wrapper tool that
stamps before calling an inner tool will end up with two stamps on the
output. Today `update_inventory` is the only known caller, but the
same pattern would bite any future wrapper.

### Severity

**Cosmetic to the data, real for the intelligence layer.**

- Cosmetic: the second stamp doesn't change behaviour. Both record
  the same actor / channel / executor / outcome. The log is still
  unambiguously "created by Claude on 2026-05-25 via MCP".
- Real: `provenance_coverage` metric (defined in
  [`interaction-stamp.ts countStampsInLogs`](../../mcp-server-ts/plugins/farm-plugin/src/helpers/interaction-stamp.ts#L173))
  counts a single boolean per log — it would not catch double-stamping.
  But:
  - `parseStamp` (the same file, line 125) takes the **first** stamp it
    encounters and returns it. So when the intelligence layer reads
    `update_inventory` logs, it sees `action=updated`. The `action=created`
    stamp underneath is invisible. If any consumer cares about the
    distinction (e.g. an audit tool that wants to verify a log was a
    genuine creation versus a reset), it gets the wrong answer.
  - More fundamentally: the InteractionStamp model claims each log has
    *one* stamp recording its provenance. Two stamps violates this
    contract. The model's reliability is already eroded by the
    text-not-triple encoding (memo Q3); duplicate stamping erodes it
    further.

### Proposed fixes

**Tactical (one PR, all servers):**

1. `appendStamp` becomes idempotent: if the input already contains
   `STAMP_PREFIX`, replace the existing stamp with the new one rather
   than appending. This is the safest default — the inner tool's stamp
   wins because it's closer to the actual write.
2. Add a contract test: every write tool's output log notes must
   contain *exactly one* InteractionStamp. Enforce via the existing
   test harness.

**Structural (post-Foundry decision on Q3):**

Per the memo's Question 3, InteractionStamp should probably move from
comment-line text to first-class typed fields on the log. When that
happens this whole class of bug disappears — there's no "append" path
for a typed field, only a single setter. Until then the tactical fix
above keeps the contract honest.

**Related cosmetic issue worth fixing alongside:** the `related=` fields
are inconsistent across tools:

| Tool | `related=` format |
|---|---|
| `update_inventory` | `<full asset name>` |
| `create_observation` | `<species>,<section>` |
| `create_activity` | `<section>` |
| `archive_plant` | `<plant name>` |

These should normalise to a single shape (e.g. always `<entity_type>:<id>`
once stamps become typed). For now, document the variation so consumers
parsing `related=` know what to expect.

---

## Part II — Broader intelligence-layer surface

The five issues in the original memo all reduce to *the pipeline does
not interpret its own logs*. The broader corpus reveals six more
clusters of issues, all related to the same architectural gap at
different scales.

### Cluster A — Response contract / silent-failure family

**The single most-frequent class of bug in this codebase.** Catalogued in
[`claude-docs/observation-pipeline-issues-2026-04-29.md`](../../claude-docs/observation-pipeline-issues-2026-04-29.md).
Seven distinct silent-failure modes documented; the connecting theme
is that the pipeline returns shape-identical "success" responses for
materially different outcomes.

| Sub-issue | Symptom | Class |
|---|---|---|
| A1 | Truncated UUID silent no-op — `update_observation_status_batch` returns `rows_updated: 0` with no distinction between "no match" and "already done" | API contract gap |
| A2 | **7 sheet rows physically deleted between Apr 28-29 with no traceable cause** — root cause still unknown despite code review | Data loss, mechanism unexplained |
| A3 | Silent species drop on multi-plant submission — 13 of 15 plants imported, `errors: null`, `total_actions: 14` | Per-iteration error swallowing |
| A4 | MCP 60s timeout with server-side completion — operator can't tell if retry is needed | Transport contract gap |
| A5 | P2R4.6-14 missing transplant (Mar 24) — James's team memory claimed `farmos_changes` with `create_plant` entries; farmOS shows nothing | Cross-system claim vs reality |
| A6 | Duplicate InteractionStamp on `update_inventory` logs (Part I above) | Stamp/provenance contract gap |
| A7 | PlantNet "configured but never called" false alarm noise | Response semantics |
| A8 | Drive transient errors undifferentiated from genuine media loss | Response semantics |

**Intelligence-layer relevance — direct.** Each of these is an
InteractionStamp / response-contract failure. The Foundry's
`semantic-layer-not-thresholds` position says the semantic layer
models *what things mean and how they change*. The shape of a
mutation response — "intended N actions, completed M, skipped K with
reasons" — is itself a semantic claim about an event. Today the
response shape is informal and per-tool. A formal mutation-receipt
schema (with required fields: `intended`, `completed`, `skipped[]`,
`requires_followup`, `idempotency_receipt`) would:

- Make A1 unambiguous (response distinguishes no-match from no-op).
- Make A3 catchable (response refuses success unless completed == intended).
- Make A4 safer (response carries a `job_id` for retry-vs-poll).
- Make A6 impossible (single typed stamp field, no append path).
- Probably catch A2 by surfacing every row-deletion event with actor + timestamp.

**Foundry input wanted on top of the memo's Q3:** does the mutation
receipt belong in the InteractionStamp (one stamp = one mutation event)
or as a sibling structure? Implementing the right one prevents most of
this cluster from ever happening again.

### Cluster B — Processes that have no asset representation (green-manure family)

The memo's Issue 5 (green manure) is the canonical instance. The same
gap appears across multiple workflows, all documented:

- **Cover crops / green manure** —
  [`project_green_manure_categorisation.md`](../../../.claude/projects/-Users-agnes-Repos-FireflyCorner/memory/project_green_manure_categorisation.md).
  Winter Market Garden Mix, Sunn Hemp, Cowpea, Millet — sown as mixes,
  no individual plant assets, chopped at end of cycle. Today modelled
  as `asset/plant` with stale counts. Plant_type stays useful for mix
  design; asset semantics need a category dimension.
- **Direct paddock sowing** — Winter Mix has 1.7 kg of seed bank
  withdrawals with no plant asset and no `Seeding` log target
  ([`project_seedbank_holistic_review_needed.md`](../../../.claude/projects/-Users-agnes-Repos-FireflyCorner/memory/project_seedbank_holistic_review_needed.md)).
- **Invasive species / volunteers** —
  [`project_invasive_species_handling.md`](../../../.claude/projects/-Users-agnes-Repos-FireflyCorner/memory/project_invasive_species_handling.md).
  4 distinct invasive encounters in 7 days (Cuban Jute, Periwinkle ×2,
  Fierce Thornapple). Wwoofers see them, need to know what to do, but
  there's no model: "we didn't plant it, we want it gone, but it's
  here." Today: section-note-only with no actionable surface.
- **Multi-stage harvest** —
  [`project_cowpea_harvest_workflow.md`](../../../.claude/projects/-Users-agnes-Repos-FireflyCorner/memory/project_cowpea_harvest_workflow.md).
  Field harvest → pod processing → weighing → seed bank deposit. Four
  events spanning days/weeks, with lineage. Today each event is an
  isolated activity log with no link. I13 invariant + `create_harvest`
  tool designed but not shipped.
- **Activity timeline visibility** —
  [`project_activity_log_design.md`](../../../.claude/projects/-Users-agnes-Repos-FireflyCorner/memory/project_activity_log_design.md).
  Activity logs are captured but not surfaced as actionable. James
  needs "what needs doing this week, prioritised by plant succession
  stage + section last-activity recency."
- **Nursery propagation** —
  [`claude-docs/ux-review-deferred-2026-04-23.md` §1](../../claude-docs/ux-review-deferred-2026-04-23.md).
  Cutting-take, division, transplant-in have no first-class
  representation — propagation chain (cutting → potted plant → field
  plant) is lost.

**Intelligence-layer relevance — direct, single root cause.** All of
these reduce to one missing primitive: **the ontology has no
first-class Event/Process entity.** Today everything is modelled as
either a noun (Plant, Section) or an unstructured log (free-text
notes). Cover-crop cycles, harvest pipelines, invasive-management
actions, propagation chains, transplant lineages are all *processes
that span multiple events over time with typed relationships between
them*.

This is exactly the question Q1 in the memo asks. The Foundry's
answer will resolve at least 6 backlog items simultaneously. The
sub-questions on top of the memo:

- Is the process entity one class (`FarmProcess`) with subclasses
  (`CoverCropCycle`, `HarvestPipeline`, `PropagationChain`,
  `InvasiveManagement`), or many parallel classes?
- Where does a process *live* in farmOS terms? Native farmOS has
  Activity / Observation / Transplanting / Harvest / Seeding log
  types — could `CoverCropCycle` be a *virtual* entity computed from a
  sequence of these, or does it need a backing record?
- How does a process render on a QR landing page? Today the page is
  asset-centric. A process-centric view (e.g. "this section's current
  cycles") may be a different page type entirely.

### Cluster C — Lineage / derivation / evidence-source triples

Six concrete instances where information about *where a fact came from*
is captured in text and lost to the intelligence layer:

| Instance | Today | Should be |
|---|---|---|
| Geranium duplicate (memo Issue 2) | New asset created; lineage to nursery is in free-text asset notes | `transplanted_from=nursery_plant_id` typed edge |
| Cowpea harvest stages | Field activity log → seed bank entry; link is reporter memory + free-text | `derived_from=harvest_log_id` on seed bank entry |
| Seed bank → sowing | Sheet withdrawal, then sowing event — no link | `consumed_by=sowing_log_id` on withdrawal |
| Photo provenance (memo Issues 1, 4) | Plant_type ref photo: latest-wins, source forgotten | `evidence_source=log_id|drive_url|plantnet_match` |
| Plant identification | `species=Walnut (Placentia)` — but who verified? PlantNet? Agnes? | `identified_by=actor, verification_source=plantnet_match\|field_id` |
| Submission-to-log derivation | Apps Script writes ~10 logs per submission; link via `submission=` in stamp text | `derived_from_submission=uuid` typed edge |
| Sheet-row-to-log derivation | Sheet row gets deleted after successful import (cluster A); lineage lost | Lineage in the InteractionStamp, but stamp is text not triple |
| Drive folder photos (memo Issue 4a) | Photos curated outside farmOS; no link | `external_source=drive_folder_id\|drive_file_id` |

**Intelligence-layer relevance — direct.** This is the memo's Q3
(InteractionStamp as triples) and Q5 (external evidence sources)
together, but the surface is broader than the memo conveys. The
fix once Foundry locks Q3 + Q5: every farmOS entity acquires a
`provenance` block with `derived_from`, `identified_by`,
`evidence_source`, `cited_by` typed edges.

This is also the seed of the **Context Graph** Foundation Capital's
thesis describes — accumulating decision provenance. FireflyCorner has
been writing one in text form ("InteractionStamp on every log") for 3
months; promoting it to triples would make it queryable.

### Cluster D — Read-side semantic gaps

The MCP server's read tools embed assumptions about the data model
that don't match reality. The pattern: a new entity or relationship is
created that the read tools don't know to look for, and they silently
return the wrong answer.

Known instances:

| Read tool | What it misses | When discovered |
|---|---|---|
| `query_sections` (pre-ADR 0011) | Row + paddock assets (regex filter `^P\dR\d\.\d+-\d+$`) | 2026-05-24, nearly caused duplicate P1R2/P1R4 |
| `query_logs(section_id=...)` (pre-ADR 0011) | Logs attached via `location` relationship — only matched log name substring | 2026-05-24, same incident |
| `get_inventory(section_prefix="NURS")` | `asset/seed` records (NURS.FRDG/FRZR return 0; only queries `asset/plant`) | 2026-04-02, [`project_data_integrity_issues.md`](../../../.claude/projects/-Users-agnes-Repos-FireflyCorner/memory/project_data_integrity_issues.md) |
| `export_farmos.py` photo fetch | Asset-level `image` relationship (only fetches `plant_type.image` + `log.image`) | 2026-05-25 *(this session)*, surfaced on Walnut |
| `system_health` | 51 s timeout — uses `fetchAllPaginated('asset/plant')` over 716 plants instead of `meta.count` from `page[limit]=0` | 2026-05-04, top frustration |
| Section page generator | Activity log photos surfaced if attached; section logs with no photos but cited evidence on another log don't link (memo Issue 3) | 2026-05-25 *(this session)*, surfaced on TODO logs |
| Page generator | Green-manure box driven by static `green_manure[]` array; ignores activity logs that mention cover-crop verbs (memo Issue 5) | 2026-05-25 *(this session)* |

**Intelligence-layer relevance — direct.** Every read tool is a
*projection* of the underlying graph. Today projections are written in
imperative code and break silently when the graph evolves. If the
ontology had a formal schema (Foundry Q1's process entity, Q3's
typed stamps), read tools could be regenerated mechanically — or
better, projections could be expressed as SPARQL/Cypher queries that
get the schema for free.

This cluster is also the strongest case for the Foundry's
**shape-contract projection** position (queued for later). A
plant-asset projection that ignores `asset/seed` should fail loudly
when first asked, not silently return zero.

### Cluster E — Tests miss the bug classes that actually ship

Documented in
[`project_sdlc_with_ai_thinking.md`](../../../.claude/projects/-Users-agnes-Repos-FireflyCorner/memory/project_sdlc_with_ai_thinking.md)
and
[`claude-docs/sdlc-with-ai-design-thinking-2026-04-22.md`](../../claude-docs/sdlc-with-ai-design-thinking-2026-04-22.md).

Facts:

- **716 tests passing** in CI (376 Python + 340 TS).
- **At least 4 bug classes shipped to live data in one Apr-22 evening:**
  gate-on-flag, farmOS response-shape variance (dict vs list), same-name
  log collision between submissions, section_notes duplication on
  inventory expansion. All in code paths that had tests. None caught.
- The Apr-29 deletion incident (cluster A2) — root cause still unknown
  despite full code review.
- The May-5 section-observe form ghost-row bug — 3 separate layers had
  to be patched; tests had not caught any layer.

**Agnes's framing (May 5 lessons #12, #13):** the tests are tautological
(they assert what the code does, not what it should do). The system
needs *invariant-driven scenario tests* that bind to ADR 0008's I1-I12
and the missing response-contract invariant (cluster A).

**Intelligence-layer relevance — direct.** The Foundry's stated position
"SHACL is a type system, `sh:Rule` is a transformation engine" maps
exactly here. ADR 0008's invariant validator is *already* a
SHACL-shape-checker in disguise. If invariants were formal SHACL
shapes, the same shape would run at write time (importer) and audit
time (validator) and test time (scenario harness) — no drift between
the three. Today they're three different implementations of the same
intent.

This is also where the SDLC-with-AI rethink and the Foundry's canon
intersect most cleanly: formal contracts give Claude something
load-bearing to check before writing, instead of having to guess from
code patterns.

### Cluster F — UX-as-data-quality (interfaces are first-time use, every time)

Per [`feedback_ux_must_be_bulletproof.md`](../../../.claude/projects/-Users-agnes-Repos-FireflyCorner/memory/feedback_ux_must_be_bulletproof.md):
Firefly Corner runs on continuous WWOOFer turnover (~every 2 weeks)
plus rotating Hipcamp / Landcare visitors. Every interface is
effectively first-time use. UX bugs become data bugs.

Concrete instances:

- **Form prefill silently masquerades as edit** (May 5 lesson #12) —
  observe form prefilled `data-current` into the "Now" field as
  anti-zeroing safety; submit logic used `value !== ""` as edit
  signal, which was always true. Every section-note-only submission
  carried 15 ghost observation rows. Fixed in three layers (`observe.js`
  + TS importer + Python importer).
- **"Always-present headers" can't be used as edit signals** (May 5
  lesson #13) — importer gate `countChanged || combinedNotes` was
  effectively unconditional because `buildImportNotes` always emits
  Reporter / Submitted / Mode / InteractionStamp headers.
- **Claire-attribution default bug** —
  [`feedback_claire_attribution_default_bug.md`](../../../.claude/projects/-Users-agnes-Repos-FireflyCorner/memory/feedback_claire_attribution_default_bug.md).
  Observe form pre-fills last observer name in localStorage. Three
  known instances of submissions imported under Claire's name that
  were actually Agnes. The Geranium-duplicate root cause we discovered
  today (memo Issue 2) was Kacper's submission for the same reason.
- **Wwoofers can't add new species** — Kacper's submission section_note
  on 2026-04-28: *"Unable to add species to the list"*. The exact
  Fierce Thornapple instance that triggered the invasive-handling
  design re-flag.
- **10 deferred UX items** in
  [`claude-docs/ux-review-deferred-2026-04-23.md`](../../claude-docs/ux-review-deferred-2026-04-23.md),
  including the nursery add-plant flow (no equivalent of `new_plant`
  mode on nursery), missing nursery observe page parity, no photo
  capture on nursery inline form, no identity confirmation prompt.

**Intelligence-layer relevance — indirect but pivotal.** UX bugs land
as malformed `submission` records that the importer then has to
interpret. If the import path treated the submission as a typed
event with a validation shape (Q3 / Q5), most of these bugs would
fail loudly at the submission boundary instead of silently being
imported as wrong data.

There's also a direct intelligence-layer angle: the
InteractionStamp's `confidence` field exists in the type definition
but is not populated by any tool. UX-friction signals (prefilled
defaults, no edit since prefill, no photo, classifier flagged
ambiguous) should populate it.

### Cluster G — Inter-system trust + integration

External systems FireflyCorner depends on, each with its own trust
profile + failure modes:

| System | Trust today | Known issues |
|---|---|---|
| farmOS / margregen | Source of truth | v4 migration complete; 51s system_health (cluster D); some 403s on direct GET as some accounts; future Phase 4 farm_syntropic Drupal module deferred |
| Apps Script backends (6 of them) | Reliable when they work | Sheet-reading endpoints scale linearly + time out under MCP; the Apr-29 sheet-deletion mystery (cluster A2); auto-deletion of imported rows breaks audit trail (Pattern A from MEMORY.md May 24) |
| Google Drive | Evidence store, manual | Curated photo folders (memo Issue 4); transient fetch errors (cluster A8); no API ingestion path |
| Google Sheets (Observations, SeedBank, Harvest, KB, TeamMemory, PlantTypes) | Operational state | 7 rows vanished Apr 28-29 mechanism unknown (cluster A2); rejected accumulate forever (cluster A5); imported rows auto-deleted = audit gap |
| PlantNet | Supporting evidence only ([`feedback_plantnet_verification_policy.md`](../../../.claude/projects/-Users-agnes-Repos-FireflyCorner/memory/feedback_plantnet_verification_policy.md)) | CORS allowlist quirk ([`reference_plantnet_cors.md`](../../../.claude/projects/-Users-agnes-Repos-FireflyCorner/memory/reference_plantnet_cors.md)); occasional misidentifications |
| GitHub Pages | Generated artefacts | Whole pipeline depends on `export_farmos.py` + `generate_site.py` not crashing |
| GHL (Go High Level) for volunteer onboarding | External CMS | Vue parser quirks ([`reference_ghl_custom_code_constraints.md`](../../../.claude/projects/-Users-agnes-Repos-FireflyCorner/memory/reference_ghl_custom_code_constraints.md)) |
| Railway | Hosting | Container sleeps, mcp-remote stale-session loop |

**Intelligence-layer relevance — indirect but extends the Foundry's
LLM-as-noisy-sensor position.** Each external system is a different
noisy sensor with a different trust profile. The current
`farm_ontology.yaml` Trust Hierarchy ranks them coarsely but the
operational reality is more nuanced (PlantNet is "supporting evidence
only" for some species but trusted for others; Apps Script is reliable
for writes but lossy on Sheet-row deletes; etc.). A typed
`source_quality` annotation per entity edge would let the intelligence
layer reason about confidence at query time.

---

## Part III — Cross-cutting observation

Folding the seven clusters into the original memo's framing:

> The pipeline records and displays its data; it does not interpret it.

Now reads as:

> **The pipeline records and displays its data. The intelligence layer's
> job is to interpret it. The intelligence layer doesn't yet exist
> formally — only its components (ontology YAML, semantics YAML, validator
> code, InteractionStamp text, classifier rules) exist in scattered
> implementations that drift from each other.**

Six implementations of the same intent (from highest to lowest formality):

1. **`knowledge/farm_ontology.yaml`** — Layer 1, declarative, ~400 lines
2. **`knowledge/farm_semantics.yaml`** — Layer 3, declarative, ~250 lines, metrics + thresholds only
3. **`mcp-server-ts/.../helpers/interaction-stamp.ts`** — typed InteractionStamp fields, but emitted as comment text
4. **`mcp-server-ts/.../tools/import-observations.ts`** — I1–I12 invariants enforced procedurally at write time
5. **`scripts/validate_observations.py`** — same I1–I12 invariants enforced procedurally at audit time
6. **`scripts/generate_site.py`** — projection rules embedded in HTML rendering

Each implements part of the intelligence layer; none knows about the
others. When the ontology gains a new entity type, code paths 3-6 don't
notice. When a test asserts an invariant differently from the validator,
neither knows. When the validator finds a violation, the importer
doesn't learn how to prevent it next time.

**This is the gap the Foundry can close most directly.** Locking
positions on Q1–Q5 (memo) + the duplicate-stamp contract fix (Part I)
+ the response-contract invariant (cluster A) gives FireflyCorner a
single load-bearing specification that all six implementations can
derive from instead of independently restating.

---

## Part IV — Backlog inventory with intelligence-layer mapping

Compact table. **Direct** = the item *is* an intelligence-layer issue.
**Indirect** = the item is gated by an intelligence-layer decision.
**Orthogonal** = the item is a system-ops / DevOps / pure-UX issue
the Foundry should be aware of but doesn't need to position on.

| Item | Source | Cluster | IL relevance |
|---|---|---|---|
| Duplicate InteractionStamp on `update_inventory` | Part I above | A | **Direct** |
| Truncated UUID silent no-op | obs-pipeline-issues-Apr29 #1 | A | **Direct** |
| 7-row Apr 29 deletion incident | project_observation_deletion_incident | A | **Direct** + Orthogonal (Apps Script bug) |
| Silent species drop on multi-plant import | obs-pipeline-issues-Apr29 #3 | A | **Direct** |
| MCP 60s timeout silent completion | obs-pipeline-issues-Apr29 #4 | A | **Direct** + Orthogonal |
| P2R4.6-14 missing transplant (Mar 24) | project_data_integrity_issues | A | **Direct** |
| PlantNet false-alarm warning | obs-pipeline-issues-Apr29 #6 | A | Orthogonal |
| Drive transient-error response shape | obs-pipeline-issues-Apr29 #7 | A | Orthogonal |
| Green-manure data model | project_green_manure_categorisation | B | **Direct** (memo Q1) |
| Seed bank holistic review | project_seedbank_holistic_review_needed | B | **Direct** (memo Q1) |
| Invasive species handling | project_invasive_species_handling | B | **Direct** (memo Q1) |
| Cowpea harvest I13 | project_cowpea_harvest_workflow | B | **Direct** (memo Q1) |
| Activity log visibility + priority query | project_activity_log_design | B + D | **Indirect** |
| Nursery propagation model | ux-review-deferred #1 | B + F | **Direct** + Indirect |
| Geranium duplicate (memo Issue 2) | memo Q2 | C | **Direct** |
| Photo provenance (memo Issues 1, 4) | memo Q4 | C | **Direct** |
| Plant identification provenance | this appendix | C | **Direct** |
| Sheet-row → log derivation | this appendix | C | **Direct** |
| `query_sections` regex gap (FIXED) | ADR 0011 | D | **Direct** (validation of fix) |
| `query_logs(section_id)` name-substring (FIXED) | ADR 0011 | D | **Direct** (validation of fix) |
| `get_inventory` ignores `asset/seed` | project_data_integrity_issues #1 | D | **Direct** |
| `export_farmos.py` no asset-image fetch | this session | D | **Direct** (memo Q4) |
| `system_health` 51s timeout | MEMORY.md open backlog | D | Orthogonal |
| Section page generator photo-traversal (FIXED today) | memo Issue 3 | D | **Direct** |
| Tests don't catch the bugs that ship | project_sdlc_with_ai_thinking | E | **Direct** |
| Eleven invariants → SHACL shapes? | ADR 0008 | E | **Direct** |
| Form prefill silently masquerades as edit (FIXED May 5) | MEMORY.md lesson #12 | F | **Indirect** |
| "Always-present headers" can't be edit signals (FIXED May 5) | MEMORY.md lesson #13 | F | **Indirect** |
| Claire-attribution default bug | feedback_claire_attribution_default_bug | F | **Indirect** |
| Wwoofers can't add new species | project_invasive_species_handling | F | **Indirect** |
| 10 deferred UX items | ux-review-deferred-2026-04-23 | F | Mixed (4 direct, 6 orthogonal) |
| InteractionStamp `confidence` field unused | this appendix | F | **Direct** |
| Apps Script sheet-deletion auto-clean | MEMORY.md Pattern A | G | **Indirect** |
| Drive folder ingest path | memo Q5 | G | **Direct** |
| Trust hierarchy needs per-edge confidence | this appendix | G | **Direct** |
| `mcp-remote` stale-session loop | MEMORY.md open backlog | G | Orthogonal |
| Apps Script timeouts on Sheet reads | MEMORY.md open backlog | G | Orthogonal |
| Railway container sleep | MEMORY.md open backlog | G | Orthogonal |
| v3 cleanup PR | MEMORY.md open backlog | — | Orthogonal |
| FASF skill library seeding | MEMORY.md open backlog | — | Indirect (skill = projection consumer) |
| Per-tool telemetry / `get_usage_metrics` | MEMORY.md open backlog | A + D | **Direct** |
| I11 type mismatches (59 legacy logs) | MEMORY.md open backlog | E | Indirect (cleanup) |
| I1 activity-language in observations (28 legacy) | MEMORY.md open backlog | E | Indirect (cleanup) |
| I4 duplicate photos (12 legacy) | MEMORY.md open backlog | E | Indirect (cleanup) |
| 903 pre-Apr-1 logs as "pre-invariant era" | MEMORY.md open backlog | E | Indirect (cleanup) |
| 16 species stuck tier-1 with no stock | MEMORY.md open backlog | — | Orthogonal (operational) |
| P1R2 / P1R4 section structure pending | MEMORY.md open backlog | — | Orthogonal (data entry) |
| Three invasive flags pending James field-verification | MEMORY.md open backlog | B | Indirect |
| Pattern B Apr 29 deletion investigation | MEMORY.md open backlog | A | **Direct** (root cause of A2) |
| Volunteer onboarding pages (Vue parser, full-bleed) | reference_volunteer_onboarding_pages + reference_ghl_custom_code_constraints | G | Orthogonal |

**Counts by relevance:**

- **Direct intelligence-layer issues:** ~24 of 48 items
- **Indirectly gated:** ~12 of 48
- **Orthogonal (Foundry context only):** ~12 of 48

---

## Part V — Suggested expansion to Foundry's normative-position queue

Based on the broader surface, the original memo's Q1–Q5 cover most of the
direct items. Two additional positions would close the remaining gaps:

### Q6 (new) — Mutation receipt contract

**Question:** What does a write tool's successful response promise? Today
"success" can mean any of: completed all intended actions; completed
some; completed all but request-side connection dropped; matched zero
rows because the input was malformed; matched zero rows because the
work was already done.

**Why now:** cluster A. Eight known instances of silent-failure
ambiguity in this codebase alone. Likely much higher across sibling
projects.

**Connects to:** Q3 (InteractionStamp triples) — the mutation receipt
is structurally a *self-stamp* the response carries back.

**Affected canon location:** could be a sub-position under
`semantic-layer-not-thresholds` or a new
`mutation-receipt-contract.md`.

### Q7 (new) — Per-edge source quality / confidence

**Question:** When a Plant entity has a `species` edge derived from
PlantNet at 0.84 confidence vs an `identified_by=Claire` edge from a
field walk, both edges exist in the graph. How does the intelligence
layer reason about which to trust at query time?

**Why now:** cluster G + `farm_ontology.yaml`'s Trust Hierarchy is too
coarse. Photo promotion (memo Q4) needs per-instance confidence, not
per-source-class.

**Connects to:** the LLM-as-noisy-sensor position landing Tue. LLMs are
not the only noisy sensor — PlantNet, automated batch imports, and even
field workers under time pressure are also noisy sensors with
quantifiable confidence.

---

## Pointers for the Foundry session

- **Memo:** [`for-review/intelligence-layer-state-2026-05-25/memo.md`](memo.md)
- **This appendix:** [`for-review/intelligence-layer-state-2026-05-25/appendix.md`](appendix.md)
- **Primary corpus consulted:**
  - [`claude-docs/session-history.md`](../../claude-docs/session-history.md)
  - [`claude-docs/observation-pipeline-issues-2026-04-29.md`](../../claude-docs/observation-pipeline-issues-2026-04-29.md)
  - [`claude-docs/sdlc-with-ai-design-thinking-2026-04-22.md`](../../claude-docs/sdlc-with-ai-design-thinking-2026-04-22.md)
  - [`claude-docs/ux-review-deferred-2026-04-23.md`](../../claude-docs/ux-review-deferred-2026-04-23.md)
  - [`claude-docs/adr/0008-observation-record-invariant.md`](../../claude-docs/adr/0008-observation-record-invariant.md)
  - [`claude-docs/adr/0011-read-side-tool-surface.md`](../../claude-docs/adr/0011-read-side-tool-surface.md)
  - `~/.claude/projects/-Users-agnes-Repos-FireflyCorner/memory/MEMORY.md` (current resume anchor + open backlog)
  - 11 pinned `project_*.md` memory files
- **Live intelligence-layer artefacts:**
  - [`knowledge/farm_ontology.yaml`](../../knowledge/farm_ontology.yaml)
  - [`knowledge/farm_semantics.yaml`](../../knowledge/farm_semantics.yaml)
  - [`mcp-server-ts/plugins/farm-plugin/src/helpers/interaction-stamp.ts`](../../mcp-server-ts/plugins/farm-plugin/src/helpers/interaction-stamp.ts)

---

*Drafted 2026-05-25 to extend the morning memo. Hand off to Foundry by
referencing this appendix alongside the primary memo in the Foundry
session.*
