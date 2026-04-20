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
