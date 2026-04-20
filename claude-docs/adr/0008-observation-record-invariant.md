# 0008 — Observation Record Invariant + Validator

- **Status:** proposed
- **Date:** 2026-04-20
- **Authors:** Agnes, Claude
- **Supersedes:** —
- **Related:** 0001 (photo pipeline), 0004 (batch observation tools),
  0005 (submission-scoped media), 0006 (agent skill framework), 0007
  (import pipeline reliability)

## Context

Over the past four sessions (2026-04-14 through 2026-04-20) we have
shipped six ADRs that each tackle one failure mode of the observation
import pipeline: photo pipeline semantics (0001), batch tools (0004),
submission-scoped media (0005), agent skill framework (0006), and
import pipeline reliability (0007).

Despite this, every QR-page review session surfaces new defects:
- 2026-04-14 — Leah's photos cross-attached to 15 unrelated logs (→ 0005)
- 2026-04-18 — Papaya reference photo overwritten by lower-quality one
- 2026-04-18 — "James — review" tasks invisible to James's Claude (→ 0006)
- 2026-04-18 — Observations.gs inconsistent list responses (→ 0007)
- 2026-04-20 — 18 species with field photos attached to logs but the
  plant_type reference still showing stock (Issue 1 this session)
- 2026-04-20 — photos double-attached to logs (Issue 2 this session)
- 2026-04-20 — section_notes text fanned out onto every plant-log in
  the section (Issue 3 this session)

These are not the same defect. Each surfaces a different rule that the
system should have been enforcing but never was. Agnes's exact question:
*"How can we break that cycle?"*

**The root cause is that we have never written down what a correctly
imported observation must satisfy.** Every ADR so far addresses a
specific failure mode. None of them specify the full contract. So the
system has no way to audit itself — every defect has to be discovered
by a human looking at the QR page.

## Decision

Introduce **The Observation Record Invariant** as the formal contract
every observation record (across all log types: observation, activity,
transplanting, seeding, harvest) must satisfy. Ship a **validator**
that checks any record against the invariant, and an **audit tool**
that runs the validator across a scope (section, date range, all). The
validator becomes the enforcement point at write time (ADR 0007 Fix 4)
and the discovery point at audit time.

Specifically:

1. **Specification** — the seven invariants below are the contract.
   Every log-creating code path must produce records that satisfy all
   seven. Every audit must check all seven.

2. **Validator** — a pure function
   `validate_observation_record(log, context) → list[Violation]`.
   Returns structured violations with invariant ID, severity, and
   remediation hint. Zero side effects. Fully unit-testable.

3. **Audit tool** — a surface over the validator that runs it across a
   scope and produces a report. Exposed as MCP tool
   `audit_observation_records(section_prefix=..., date_from=..., date_to=...)`.

4. **Enforcement at write time** — the import pipeline calls the
   validator as the last step before returning success (subsumes ADR
   0007 Fix 4). A violating record either (a) is corrected in-place
   before commit, or (b) fails the write with a specific violation
   message. Never silently creates a defective record.

5. **Enforcement at audit time** — the audit tool is run after any
   session that writes logs (part of ADR 0006 `session_open` skill's
   postcondition check). Violation backlog is surfaced to the operator.

## The Seven Invariants

### I1 — Log type correctness

A log's `type` field must match the semantic nature of the event:

- **observation** — a count, condition, or presence check of one or
  more specific plants, or a note about a section's state
- **activity** — a farming action taken (chop-and-drop, mulching,
  seeding, weeding, pest treatment, transplant staging, etc.)
- **transplanting** — a plant or batch of plants moved between locations
- **seeding** — a seed asset consumed to create a plant asset
- **harvest** — produce removed from a plant asset

Wrong type strips the semantic meaning. Agents cannot answer "what
activities did we do in P2R5 this month" if chop-and-drop activities
are logged as observations.

### I2 — Asset attachment matches scope

If the record is **plant-specific** (describes one or more named plants):
- `asset_ids = [plant_uuid, …]` — one or more plant assets
- `location_ids = [section_uuid]` — the section the plants live in
  (for spatial indexing)
- Notes reference only those plants

If the record is **section-level** (describes the section as a whole):
- `asset_ids = []` — empty
- `location_ids = [section_uuid]` — the section asset
- Notes reference the section, not any specific plant

Mixed records (plant-specific + section-level content) are **forbidden**.
Split into two separate logs at write time.

### I3 — Notes hygiene

The `notes.value` text of a log must contain only content relevant to
the attached entity. Specifically:

- Plant-log notes must not contain "Section notes:" text or similar
  section-level commentary.
- Section-log notes must not contain per-plant commentary ("5 eaten",
  "looking sick", etc.).
- An `InteractionStamp` trailer is always present (ADR 0006
  `record_fieldwork` skill postcondition).

Violations of I3 are typically produced by inventory-mode submissions
that carry a `section_notes` field but the importer fans that field
out to every per-plant log it creates.

### I4 — Photo uniqueness

The `image` relationship on a log is a **set**, not a bag: every
file reference must be unique by (filename OR filesize-and-content-hash).
Duplicate attachments — two references to files with identical
content — are a violation.

The typical cause is an import that is retried after the backend
silently completed the first attempt. Post-write verification (write-
time enforcement of I4) would catch this: if the log already has the
photo, skip re-attach.

### I5 — Reference-photo promotion

The `image` relationship on a `taxonomy_term/plant_type` is
**single-valued** by policy. Its one member is the canonical reference
photo for the species. Ranking rules, in order:

1. **Field photo beats stock photo.** A stock photo is any file whose
   filename matches a stock-photo pattern (URL-encoded scientific name,
   Wikipedia dump, Köhler illustration, etc.) or was uploaded before
   the farm had field photographs. A field photo has a submission_id
   prefix, section-ID prefix, or was uploaded by the import pipeline.
2. **Higher PlantNet score beats lower** (at same source class —
   field-vs-field or stock-vs-stock).
3. **Newer beats older** on ties.
4. **Multi-plant frames, "unknown" tags, and flagged mis-IDs never
   promote** regardless of other rules.

Multi-valued `image` fields are a violation: resolve to the single best
per ranking rules and patch the relationship to contain only that file.

### I6 — Status + attribution

- `status` ∈ {`pending`, `done`}. Never null.
- Notes contain an `[ontology:InteractionStamp]` line with at minimum:
  `initiator=<user>`, `role=<role>`, `channel=<channel>`,
  `action=<action>`, `target=<target>`, `ts=<iso8601>`.
- For QR-submitted logs, the `submission=<uuid>` field is present in
  the InteractionStamp.
- The `Reporter:` line in notes names the field submitter.

A log with null status or missing attribution has broken audit trail
and cannot be reconciled with team memory's `farmos_changes` claims.

### I7 — Semantic propagation

After a log is written, downstream derived state is updated:

- Section health score recomputed (`farm_semantics.yaml`)
- Strata coverage recomputed (if last-of-species changes)
- Diversity index recomputed (if species presence changes)
- Plant_type reference photo re-evaluated (I5 may trigger)
- Site regen queued (or triggered directly if operator session)
- Team memory `farmos_changes` field cites the log ID by UUID

I7 is the hardest to verify retrospectively; the practical check is
that the integrity gate in `farm_context` shows no drift between
team memory claims and actual farmOS state. For legacy logs, I7 is
advisory; for new writes it is enforced at write time.

## Rationale

### Why the invariant approach

- **Closed set.** The seven invariants are exhaustive — every failure
  mode we have seen maps to one of them. We don't keep discovering new
  classes of bug; we discover new instances of known classes.
- **Testable.** Each invariant is a pure predicate: log + context →
  bool + violation detail. Unit-testable. No mocks beyond a log
  fixture.
- **Composable with existing ADRs.** Every prior ADR addresses
  specific invariants. 0001 is I4+I5. 0005 is I4. 0007 Fix 4 is
  write-time enforcement of all seven. 0006 `record_fieldwork` skill
  implements I7's "integrity gate."
- **Breaks the discovery cycle.** Currently each defect is discovered
  by a human. With the validator, defects are surfaced by the tool.
  The operator's job is to read a report and decide, not to hunt.

### Alternatives considered

- **Fix each issue as it appears, ADR-by-ADR.** This is what we have
  been doing. Result: four sessions, six ADRs, still finding new
  defects. Rejected because it cannot converge — the cycle is real.
- **Build a general "data integrity" framework with arbitrary
  assertions.** Rejected as over-engineered. The seven invariants
  cover every observed failure class; an extensible framework can be
  added later if the set grows.
- **Rely on more unit tests of the import code.** Rejected because
  unit tests verify code paths, not invariants on live data. The
  defects we have seen are emergent from interactions between
  Observations.gs, farmOS, the photo pipeline, the import tool, and
  the site generator — a test-per-code-path approach misses them.

## Consequences

### Positive

- Single authoritative spec. ADRs 0001/0004/0005/0006/0007 reference
  I1–I7 instead of re-specifying their corners.
- Discovery of existing defects is mechanical. Run the audit; the
  backlog is the output.
- Regression prevention is mechanical. Add a new test case = a new
  invariant unit test.
- The validator is the enforcement point the field-beats-stock rule
  (memory `feedback_reference_photo_highest_quality.md`) needed.
- Cycle-breaker: we stop discovering new defect classes by QR-page
  inspection.

### Negative

- Legacy log backlog may be large. The first audit will surface
  hundreds of violations of varying severity. Triage takes real time.
- Some invariants (I7 propagation) are hard to verify retrospectively
  and may need to be marked "advisory" for pre-invariant logs.
- Write-time enforcement (ADR 0007 Fix 4) requires plumbing into every
  log-creating code path: Observations.gs import tool (both language
  servers), direct MCP tools (create_plant, create_observation,
  create_activity, etc.), backfill scripts, the photo pipeline. That is
  substantial work.

### Neutral

- The invariants may evolve. Start with seven; add I8 or split I3 if a
  new class of defect emerges that does not fit the existing set. The
  ADR is amendable.

## Implementation plan

**Phase 0 (this session) — spec**
- This ADR, ratified.
- Cross-reference the seven invariants into ADR 0001/0004/0005/0006/0007.

**Phase 1 (this session or next) — validator + audit**
- `scripts/validate_observations.py` — Python implementation of all
  seven invariant checks (I7 best-effort).
- Audit run across P2R1–P2R5 sections + all plant_type references with
  active plants.
- Output: structured violation backlog (JSON + human-readable
  markdown).

**Phase 2 — backlog cleanup**
- Work through violations by severity. Each fix removes a class of
  violation, not a one-off. Re-run audit after each fix class.

**Phase 3 — write-time enforcement**
- Integrate validator into import-observations.ts and
  mcp-server/server.py. Post-write verify uses it (ADR 0007 Fix 4).
- Create-plant / create-observation / create-activity / create-log
  direct tools also run the validator.

**Phase 4 — MCP surface**
- `audit_observation_records(scope) → report` MCP tool.
- `validate_observation_record(log_id) → violations` MCP tool.
- Session-open skill (ADR 0006) runs a quick audit on recent writes.

## Links

- Companion: `claude-docs/cross-agent-consistency-2026-04-18.md`
- ADR 0001: photo pipeline — owns I4 + I5
- ADR 0004: batch observation tools — owns I6 attribution for batch writes
- ADR 0005: submission-scoped media — owns I4 file-level uniqueness
- ADR 0006: agent skill framework — `record_fieldwork` skill implements I7
- ADR 0007: import pipeline reliability — Fix 4 implements write-time enforcement of all invariants

---

## Amendment — 2026-04-20: Invariants I8, I9, I10, I11

- **Status:** proposed (same governance ratification as base ADR)
- **Authors:** Agnes, Claude
- **Pre-reading:** `claude-docs/observation-photo-pipeline-review-2026-04-20.md`
- **Context:** the 2026-04-20 QR-page review (Coriander, Nasturtium,
  Okra) surfaced three new defect classes not covered by I1–I7:
  (a) plant asset `notes` field polluted by full submission-body
  dumps (InteractionStamp + submission_id + Reporter/Mode/Count
  blocks); (b) photos fanned out across all per-plant logs in a
  multi-observation submission because the importer had no
  within-submission routing rule; (c) dead UI radios for
  `obs_type` (I observed / I did / Action needed) that the
  importer ignored, leaving log type effectively random. The
  seven-invariant set is extended to eleven so the contract covers
  the full observation record — asset, log, photos, and semantic
  type/status — without gaps. Base invariants I1–I7 are
  unchanged. Renumbering: the ADR becomes "The Eleven Invariants"
  once ratified.

### I8 — Asset notes hygiene

A plant asset's `notes` field must contain only stable,
planting-context text — including the **one-liner narrative** the
submitter wrote about this plant — and NOT the full submission
metadata envelope.

- **Allowed:**
  - Planting date, seed/cutting source, consortium role, permanent
    notes ("grafted April 2026", "rootstock: Anna", "companion of
    Pigeon Pea 5m west").
  - The submitter's **narrative** from the creation submission —
    i.e. the text AFTER `Plant notes:` in the original import
    payload ("Leah transcript 14 Apr 2026. two flowers observed",
    "cilantro ~5cm, early growth, stable"). This text is useful
    context for anyone reading the QR page and survives as a
    short-form record of the plant's origin.
- **Forbidden:**
  - `[ontology:InteractionStamp]` lines — belong on the log, not
    the asset.
  - `submission=<uuid>` fragments — same rationale.
  - Pure-metadata headers: `Reporter:`, `Submitted:`, `Mode:`,
    `Count:` lines. These are timestamps / mode / counts with no
    narrative content; they're already captured on the observation
    log.
  - Boilerplate phrases ("New plant added via field observation").
- **Rationale:** asset and log are not duplicates. Metadata (who,
  when, how, count-delta, stamp) lives on the log where it belongs.
  But the human narrative ("two flowers observed") is more useful
  as stable asset context than as a one-shot log note — it lets the
  QR card render `"Leah transcript 14 Apr 2026. two flowers
  observed"` instead of an empty card. This strikes the balance
  between clean asset records and useful public-facing context.
- **Enforcement at write time.** `create_plant` sanitises notes
  via `sanitise_asset_notes` / `sanitiseAssetNotes`: strips
  InteractionStamp + submission= + metadata-header lines; strips
  the literal `Plant notes:` PREFIX from any line but keeps the
  narrative that follows. The full stamped / metadata-carrying
  notes are written to the companion observation log only.
- **Enforcement at audit time.** Validator I8 check greps
  `asset.notes` for `[ontology:InteractionStamp]`, `submission=`,
  or any of the metadata prefixes and flags any match. Backfill
  script applies the same sanitiser to legacy assets.

### I9 — Photo routing within a submission

Every photo file attached to a log must match the log's scope.
Given the current observe-form UX, this reduces to two cases:

- **Single-observation submission** (`mode ∈ {quick, new_plant}`,
  `observations.length = 1`): all submission photos attach to the
  one observation log for that plant. Straightforward — there is
  only one log to attach to.
- **Multi-observation submission** (`mode = inventory`,
  `observations.length > 1`): all submission photos attach to ONE
  section-level observation log (`asset_ids=[]`,
  `location_ids=[section_uuid]`). Per-plant observation logs get
  zero photos — those logs are count/condition-only updates.
- **Never:** the same photo file attached to more than one log
  within a submission.
- **Rationale:** the UX does not capture per-plant→photo binding
  in inventory mode (no per-plant photo input — photos there are
  section-scoped by form construction). The importer must respect
  that scoping. Fanning photos onto every plant log pollutes every
  plant card on the QR page and creates cross-plant mis-attribution
  that takes manual review to untangle.
- **Enforcement at write time.** `import_observations` decides log
  routing per submission, not per observation. It creates the
  section log lazily (only if photos or section_notes exist) and
  attaches each media file to exactly one log. This subsumes the
  Phase 3c addendum's section-log split.
- **Enforcement at audit time.** Validator I9 check counts files
  shared across multiple logs in the same submission and flags any
  such file as a violation.

### I10 — QR render hygiene

The site generator must produce invariant-respecting output.

- **Plant card (section view):** `plant.notes` is rendered only
  after stripping `[ontology:InteractionStamp]` and `submission=`
  lines. Remaining content is truncated to 120 characters; if the
  stripped content is empty or trivial, the notes block is omitted
  entirely from the card.
- **Log-detail page:** full `notes.value` is rendered with the
  InteractionStamp moved to a "Provenance" block (current
  behaviour of `render_log_detail_page` — codified).
- **Section page:** section-level observation logs (`asset_ids=[]`,
  `location_ids=[section_uuid]`) render in a dedicated "Field
  observations" block above the plant inventory. Today these logs
  exist in farmOS (7 created during Phase 2A cleanup) but are
  invisible on the QR page; I10 closes that render gap.
- **Rationale:** the QR page is the primary read surface for
  non-technical team members and visitors. If asset notes are
  dumped raw or section-level logs don't render, what the reader
  sees does not reflect the actual state of the record. I10 makes
  rendering a first-class invariant.

### I11 — Log type & status from notes content, not UI radios

The `type` (observation / activity / transplanting / seeding /
harvest) and `status` (pending / done) of every imported log must
be derived from the semantic content of its notes text,
cross-referenced with `knowledge/farm_ontology.yaml` verb/action
mappings. They must NOT be derived from a UI form radio button.

- **Rationale.** UI radios in Single-Plant mode (`obs_type`:
  "I observed" / "I did" / "Action needed") are shipped in the
  submission payload but are not read by any importer code — the
  value is dead. Full-Section mode has no such radios at all, so
  even if the plumbing were fixed, the signal is only present on
  half the submissions. Relying on a volunteer to self-classify
  every entry is also fragile: workers won't internalise the
  farmOS log-type taxonomy. The text they write is ground truth;
  the classifier reads it. This brings I1 (log-type correctness)
  from audit-time discovery to write-time enforcement.

#### I11 — Classification rules (initial, deterministic)

Applied to the lowercased notes text; matches are whole-word
unless noted. First matching rule wins in the following precedence
order:

1. `seeded`, `sowed`, `seed` (as verb), `germinated` → `type=seeding`.
2. `transplanted`, `transplant`, `planted`, `planting`, `plant`
   (as verb), `moved`, `relocated`, `replanted` → `type=transplanting`.
3. `harvested`, `harvest`, `picked`, `collected`, `yielded`,
   `gathered` → `type=harvest`.
4. `chop`, `chopped`, `dropped`, `pruned`, `prune`, `cut back`,
   `mulched`, `mulch`, `weeded`, `weed`, `watered`, `watering`,
   `sprayed`, `applied`, `inoculated`, `fertilised`, `composted`,
   `dug`, `tilled` → `type=activity`.
5. `needs`, `should`, `to do`, `todo`, `urgent`, `action required`,
   `action needed`, `please`, `must`, `tbd`, or any leading-
   imperative verb → `status=pending` (tells the log it's a TODO
   task regardless of type).
6. Otherwise — past-tense narrative of observed state without an
   action verb → `type=observation`, `status=done`.

Rules 5 and 6 compose with rules 1–4: an activity can be `pending`
("needs watering"), a transplanting can be `pending`
("transplant tomorrow"), etc.

#### I11 — Ambiguity handling (Q5 policy)

If classifier confidence falls below threshold (e.g., competing
verb matches without context, or a text that matches no rule):

1. **The log IS created** — submissions are never lost.
2. Default classification: `type=observation`, `status=pending`.
3. A marker is prepended to the notes value:
   `[FLAG classifier-ambiguous: <reason>]`. Visible on the QR
   log-detail page and in farmOS UI.
4. The log MUST surface to human review via all of:
   - `query_logs(status="pending")` — session-open protocol.
   - `validate_observations.py` as an I11 violation until
     reclassified.
   - A dedicated MCP tool
     `list_classifier_ambiguous(scope=...)` returning the review
     queue with classifier reasoning.
   - The `farm_context` integrity gate flags the backlog size.
5. A human reviewer reclassifies via
   `update_observation_status` (or a new `reclassify_log` tool).
   The correction is recorded per §I11 continuous learning below.

#### I11 — Continuous learning

Every human reclassification writes a persistent correction record
to `classifier_corrections.jsonl` (or a team-memory entry with
`category=classifier_correction`):

```json
{
  "log_id": "<uuid>",
  "original_notes": "<text>",
  "classifier_output": {"type": "observation", "status": "pending", "confidence": 0.31, "reason": "..."},
  "human_correction": {"type": "activity", "status": "done"},
  "reviewer": "<name>",
  "timestamp": "<iso8601>",
  "notes": "<reviewer's explanation of the correction>"
}
```

These records feed three loops:

- **Rule tuning (now, deterministic).** When a class of
  mis-classification recurs, Agnes/Claire add the missed verb or
  pattern to the verb list above. The ADR is amended.
- **Few-shot examples (post-FASF, Step 9).** When the classifier
  is upgraded from deterministic to agent-skill
  (`classify_observation` per ADR 0006), the corrections become
  training data the skill references at classification time.
- **Accuracy metric (ongoing).** `system_health()` surfaces
  classifier first-attempt success rate across a rolling window.
  Degradation beyond a threshold triggers a review.

#### I11 — UI consequence

The `obs-type` radio group at
`generate_site.py:1131-1144` is removed. The Single-Plant form
becomes: optional photo(s) + count + condition + free-text notes.
That's what the submitter can judge. Semantic labeling is not
their job.

### Amendment — Implementation plan (extends base Phase 1–4)

The base ADR's Phase 1 (validator) and Phase 3 (write-time
enforcement) extend to cover I8–I11. Ordered steps (see pre-reading
for full detail):

1. **Generator strip + truncate** — I10 partial; independent.
2. **`create_plant` notes split** — I8 write-time.
3. **Add-new-plant: save all PlantNet angles** — UX clarity; log
   gains complete field evidence.
4. **Importer photo routing (Phase 3c)** — I9 write-time.
5. **Deterministic log-type classifier + remove UI radios** —
   I11 write-time. Classifier ships before UI change so any
   regression has a rollback path.
6. **Validator I8 + I9 + I10 + I11 checks** — audit-time.
7. **Backfill script** — detach I8 content from asset notes,
   re-route I9 cross-log photos per ADR 0005 Option B, re-type
   I11-violating legacy logs via classifier.
8. **Phase 3c render** — section-level log block on QR section
   page. I10 completion.
9. **(Post-ADR 0006 ratification)** Skill upgrade: swap
   deterministic classifier for agent-skill with corrections as
   few-shot examples. No invariant change — I11 contract is
   stable across implementations.

### Amendment — Open-questions status

All open questions raised during the 2026-04-20 review have been
resolved before drafting this amendment:

- **Q1** (save all PlantNet angles) — yes.
- **Q2** (legacy orphan cleanup) — detach and delete (ADR 0005
  Option B).
- **Q3** (ratification order) — this amendment first; skill
  upgrade deferred until pipeline is stable.
- **Q4** (drop UI radios) — yes, classifier-driven.
- **Q5** (ambiguity failure-mode) — succeed-with-flag, conditional
  on systematic surfacing to human review queue (specified in I11
  above).
- **Q5b** (continuous learning) — correction records persistent;
  feed rule tuning, skill few-shot, accuracy metric.

### Amendment — Links

- `claude-docs/observation-photo-pipeline-review-2026-04-20.md` — full pre-reading with defect traces
- ADR 0005 — closing note on per-plant UI scope (same date amendment)
- ADR 0006 — FASF; receives I11 classifier as a skill post-ratification
- `knowledge/farm_ontology.yaml` — verb mappings consumed by I11 classifier
