# FireflyCorner → Foundry: intelligence-layer state, 2026-05-25

**Author:** Agnes / Claude (FireflyCorner session)
**Audience:** fa-intelligence-foundry reviewer-of-record
**Status:** Request for normative positions

This memo collects five concrete failure modes observed on the QR landing pages
this morning (2026-05-25) after yesterday's 69-submission Hollis P2 backlog
import. The five issues are different surface symptoms of the **same**
underlying gap: the FireflyCorner pipeline has no semantic layer between its
observation logs and its downstream artefacts. It reads, stores, and renders
text + UUIDs verbatim; it does not interpret its own data.

This memo:

1. Restates the five issues with root cause.
2. Inventories the current intelligence-layer artefacts in this repo
   (`knowledge/farm_ontology.yaml`, `knowledge/farm_semantics.yaml`) against
   the gaps surfaced.
3. Surfaces **five normative-position questions** for Foundry to answer before
   FireflyCorner begins the deeper redesign.

The immediate-impact fixes for the five issues have already shipped this
session (photo promotion script, generator patches for related-evidence
surfacing and green-manure activity stream). They are tactical and do not
constitute the redesign — they buy time while Foundry positions land Tue–Wed.

---

## 1. The five issues

### Issue 1 — Field photo orphaned (Davidson Plum, P2R2.38-46)

Agnes uploaded a clear field photo with note *"Taking a photo of the Davidson
plum"* (mode=`quick`, log `dec49d60`, 2026-05-17). The photo sat on the log; the
asset and the plant_type kept the stock reference image.

**Root cause:** no projection from observation-log photos → plant-asset image →
plant_type reference image. Promotion is hand-coded per incident (three
precedent one-off scripts in `scripts/`). The classifier had no "photo-promote
intent" class. The policy is documented in
[`memory/feedback_reference_photo_highest_quality.md`](../../../.claude/projects/-Users-agnes-Repos-FireflyCorner/memory/feedback_reference_photo_highest_quality.md)
but no workflow enforces it.

### Issue 2 — Duplicate plant assets for same (section, plant_type) (Geranium, P2R3.2-9)

Two active assets share the Geranium plant_type in the same section:

| Asset | Created | Count | Notes |
|---|---|---|---|
| `e4eab78a` | 25 APR 2025 | 4 | "cuttings" |
| `8aab834a` | 24 APR 2026 | 5 | "Well developed geranium added… in the Nursery for a long time before being transplanted" |

The Apr-2026 submission was semantically a **nursery → paddock transplanting**
event but the importer's `mode=new_plant` branch unconditionally created a new
asset. No I1–I12 invariant checks for in-section plant_type duplication.

### Issue 3 — TODO log doesn't surface the photo it cites (P2R5.22-29, log `d76d0689`)

A TODO activity log Claude created on 2026-05-24 reads *"Verify Papaya species
ID for asset created from submission 7a793b7c… inspect the photo on the
imported observation log"*. The log itself has no photo (none was uploaded with
it). The cited photo lives on observation `c35ac14f` (same submission). The
page generator builds one detail page per log UUID and renders only photos
**directly** attached to that log. No relationship traversal — InteractionStamp
`related=` and `submission=` are encoded as comment-line text, not as
dereferenceable triples.

### Issue 4 — Plant asset notes cite photo location in plain English (Walnut Placentia, P2R5.66-77)

Asset notes literally read: *"Photo evidence on section activity log of
2026-04-25 (submission 133b8e16)"*. The asset image was never patched. Same
shape as issue 1 but with the intent captured in natural language inside asset
notes instead of an observation log. There's also a separate
[Drive folder](https://drive.google.com/drive/u/0/folders/1pjOpy2pMtCp2Fn6MfXsL6DyFnzbf9TiB)
with curated reference photos — completely outside the farmOS asset graph, no
ingestion path.

### Issue 5 — Green-manure section state stale across the entire farm

Examples (sampled this session):

- **P2R2.38-46**: `green_manure` array still lists Sunn Hemp + 10 others, while
  Claire's 2026-05-18 log says *"completed chop & dropped on the senescent
  sunn hemp"* and Agnes's TODO log says *"Sow Winter Market Garden Mix +
  mulch"*. Neither change reached the green-manure block.
- **P1R5.0-10**: `green_manure=[]` in `sections.json`. Section log
  "150g Winter mix seeded in this section plus mulched" (2026-04-30) rendered as
  text but never reached the green-manure block.
- **P2R5.66-77**: `green_manure=[]` despite history.

**Root cause** — compound failure across three layers:

1. `export_farmos.py:811-813` **preserves** the `green_manure` array from
   existing `sections.json`; it never **regenerates** it. The data is
   hand-curated JSON and has drifted for months.
2. `is_green_manure()` in `generate_site.py:116` fires only when a *plant
   asset* with a `green_manure`-tagged species exists. Cover crops are
   captured as **activity logs only** — no plant asset is ever created. The
   asset-driven path produces empty results for every section.
3. The pipeline has **no semantic interpretation** of activity-log
   section_notes. It treats "completed chop & dropped on the senescent sunn
   hemp" as opaque display text, not as a state-transition event. Green manure
   is a **process** (sow → grow → chop & drop → cycle), not a static
   membership of an array, and the data model can't represent processes.

---

## 2. The common pattern

All five symptoms share one shape:

> **The pipeline records and displays its data; it does not interpret it.**

| Issue | Interpretation step that is missing |
|---|---|
| 1 — Davidson Plum | "An observation note 'Taking a photo' implies promote-photo intent" |
| 2 — Geranium duplicate | "An observation with `mode=new_plant` + species already present in section implies merge, not create" |
| 3 — TODO log photo | "A log that references another log's submission_id should inherit its evidence" |
| 4 — Walnut | "Asset notes that cite a photo location should drive auto-attachment" |
| 5 — Green manure | "Activity log 'sow winter mix' implies cover-crop-cycle state transition; 'chop and drop' implies cycle complete" |

These all reduce to the same architectural ask: **the importer / pipeline
should READ AND INTERPRET its own logs**, not just pass them through verbatim.
That is the LLM-as-noisy-sensor pattern (Foundry's first normative position
landing Tue 2026-05-27) — except here the LLM (Claude) writes the logs, and a
downstream classifier / SHACL-rule layer should validate and act on them.

This is also the **semantic-layer-is-not-a-thresholds-table** position landing
Tue: today this repo's "semantic layer" (`farm_semantics.yaml`) is a metrics
+ thresholds file. It does not model processes (cover-crop cycles, nursery →
paddock transitions, photo provenance), it scores end states. The five issues
all need *process* modelling.

---

## 3. Current state of the local intelligence-layer artefacts

### `knowledge/farm_ontology.yaml` (Layer 1 — "what exists")

- Defines entity types (Species, Section, Strata, Succession, etc.) and the
  InteractionStamp pattern (mandatory on every entity change) — strong
  governance principle, sound trust hierarchy.
- Trust hierarchy hard-coded: farmOS direct entry > QR observation > audio
  transcript > PlantNet > automated batch. Good for resolving conflicts.
- **Gap vs the five issues:** entities are nouns (Plant, Section, Log); there
  is no first-class **process** entity (CoverCropCycle, TransplantEvent,
  PhotoPromotion). No formal relationship between an observation and a
  follow-up activity log that references it. InteractionStamp is required but
  its `related=` and `submission=` fields are textual, not typed.

### `knowledge/farm_semantics.yaml` (Layer 3 — "what things mean")

- Encodes metrics: `strata_coverage`, `survival_rate`, `activity_recency`,
  `succession_balance`, etc., each with calculation + thresholds.
- **Gap vs the five issues:** this is a thresholds table, not a model of state
  transitions. There is no semantic rule saying "an observation note containing
  $X$ implies state change $Y$ on entity $Z$" — yet that is what every one of
  the five issues needs.

### What's missing (Layer 2?)

Between Layer 1 (entity types) and Layer 3 (metrics) there is no formal
**state-transition / event-model** layer. Today every state change is implicit
in natural-language log notes. The redesign needs to introduce this layer
formally, and the choice of formalism (event subclass on an ontology, shape
projection in SHACL, procedural classifier in the importer) is the canonical
question for Foundry.

---

## 4. Questions for normative Foundry positions

These are the questions FireflyCorner needs answered before the deeper redesign
begins. Each is grounded in one or more of the five issues above.

### Q1 — Process modelling: cover-crop cycles

**Issue:** 5. **Implications:** also relevant to transplant tracking, harvest
events, succession changes.

What's the canonical entity for an event that *transitions* the state of a
section? Candidates:

- **(a) Event subclass on the ontology** — `CoverCropEvent` with subtypes
  `Sowing`, `Growing`, `ChopAndDrop`, `Cycle`. Each event has a timestamp,
  reporter, species set, and a `transitions_state_to` property. The section's
  current state is the most recent event of each subtype.
- **(b) Shape-projection** — section's current cover-crop state is a SHACL
  shape over the set of recent activity logs. No new entity type; the state is
  always computed.
- **(c) Workflow-rule in the importer** — when classifier identifies a cover-
  crop verb, it writes a typed log + updates a `green_manure` field on the
  section asset. Procedural, no formal model.

Foundry input wanted: which formalism (with what scope), and where does this
sit relative to the Layer 1 / Layer 2 / Layer 3 split?

### Q2 — Uniqueness invariant for in-section assets

**Issue:** 2.

Is "one active plant asset per `(section, plant_type)`" formally:

- a SHACL constraint (`sh:maxCount=1` on a `(section, plant_type)` projection)
- an OWL functional-property axiom
- a procedural importer rule (no formal constraint, the classifier just routes
  to merge instead of create)

The choice has implications for legitimately distinct same-species cohorts
(e.g. an early planting and a late planting kept separately for harvest
tracking). If we adopt the constraint, what's the explicit affordance for
multi-cohort cases?

### Q3 — InteractionStamp `related=` and `submission=` as triples

**Issue:** 3 (and underpins much of issue 1, 2, 4).

InteractionStamp is the cornerstone of the trust hierarchy
(`farm_ontology.yaml` §Trust hierarchy). Today it is a single-line text comment
on every log:

```
[ontology:InteractionStamp] initiator=Hollis | role=farmhand | channel=automated |
  executor=farmos_api | action=created | target=observation | outcome=success |
  ts=2026-05-24T08:49:35.981Z | related=Pigeon Pea,P2R5.22-29 |
  submission=da9183d8-3e9f-4e57-bb11-d0f5e544dca9
```

Should `related=` and `submission=` be promoted from comment text to
first-class RDF triples (`prov:wasDerivedFrom`, `prov:wasInformedBy`,
`firefly:submission`)? If so:

- What's the migration path for the ~5000 logs already written in text form?
- Does the InteractionStamp get rewritten as RDF on the asset/log itself, or
  emitted as a separate provenance graph?
- Does this become the seed of a **Context Graph** (per Foundation Capital's
  thesis, captured in `canon/sources/context-graphs/`)?

### Q4 — Photo provenance as a projection

**Issue:** 1, 4.

The rule "field photo beats stock photo when present" is recorded in this
repo's memory but not enforced anywhere. Options:

- **Projection:** plant_type reference image = "the most recent verified field
  photo of the species, falling back to PlantNet/Wikimedia stock". Computed by
  the pipeline on every regeneration.
- **Manual promotion workflow:** human review queue surfaces (asset with stock
  photo, candidate field photo) pairs; one-click promotion writes the rel.
- **Hybrid:** projection writes a *candidate* on every regen; manual workflow
  ratifies.

Where does the "field beats stock" rule live formally — in the ontology
(as a `preferred_provenance` ordering on Image entities), in the semantic
layer (as a quality threshold), or in the importer (as a routing rule)?

### Q5 — External evidence sources (Drive, Sheet, PlantNet)

**Issue:** 4 (Drive folder); arises again on every Sheet observation, every
PlantNet verification, every WWOOFer audio transcript.

How do we model `evidence_source` for an entity? Concretely:

- The Walnut asset has photo evidence on (a) a farmOS log and (b) Agnes's
  Drive folder. Both should be reachable from the asset.
- Sheet observations are imported then **deleted** from the Sheet
  (`sheet_status=imported_and_cleaned`). The provenance trail is broken.
- PlantNet verifications are recorded in observation notes but the species
  identification doesn't have a typed `verified_by` relationship.

Is this a trust-layer concern (typed provenance edges with confidence scores)?
A semantic-layer concern (metrics that weight source quality)? Both?

---

## 5. What FireflyCorner will do once Foundry locks positions

The five immediate fixes shipped this session are **tactical patches over the
gap**, not the redesign. Once Foundry positions on Q1–Q5 land, the
FireflyCorner redesign work spans:

1. **Layer 1 update** — add process/event entities to `farm_ontology.yaml` per
   Q1, with first-class `related_log`, `evidence_source`, `submission` typed
   relationships per Q3 and Q5.
2. **Layer 2 introduction** — formal state-transition rules (SHACL shapes or
   classifier rules per Q1's resolution) computed by the export pipeline rather
   than hand-curated in JSON.
3. **Importer rewrite** — apply Q2 uniqueness invariant + Q4 photo projection
   inside the import step rather than as one-off scripts.
4. **InteractionStamp migration** — convert text-form stamps on ~5000 existing
   logs to whatever typed-triple form Q3 settles on.

Estimated scope: 2–3 weeks once positions are locked. Half is in the TypeScript
MCP server (importer + classifier), half in the Python pipeline (export +
generate).

---

## 6. Pointers

- **Five immediate-fix changes this session** (separate commit, do not block
  this review):
  - [`scripts/promote_davidson_walnut_photos_2026_05_25.py`](../../scripts/promote_davidson_walnut_photos_2026_05_25.py) — Davidson Plum + Walnut photo promotion (idempotent).
  - [`scripts/generate_site.py`](../../scripts/generate_site.py) — added
    `_render_related_evidence` (issue 3) + extended `render_green_manure_box`
    with activity stream (issue 5). Green-manure `sections.json` data left
    as-is pending Q1 resolution.

- **Local intelligence-layer artefacts referenced:**
  - [`knowledge/farm_ontology.yaml`](../../knowledge/farm_ontology.yaml)
  - [`knowledge/farm_semantics.yaml`](../../knowledge/farm_semantics.yaml)

- **Foundry positions this memo expects to consume when published:**
  - `canon/house-positions/llm-as-noisy-sensor.md` (lands Tue 2026-05-27)
  - `canon/house-positions/semantic-layer-not-thresholds.md` (lands Tue 2026-05-27)
  - `canon/house-positions/optimiser-pattern-hybrid.md` (lands Tue 2026-05-27)
  - Future: shape-contract-projection-vs-upper-ontology

- **Reviewer-of-record memo target:**
  `fa-intelligence-foundry/reviews/firefly-corner/intelligence-layer-state-2026-05-25.md`

---

*Drafted 2026-05-25 in the FireflyCorner morning field-walk session. Hand off
to Foundry by opening a session with this memo path.*
