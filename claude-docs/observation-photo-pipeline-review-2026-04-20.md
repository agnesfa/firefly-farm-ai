# Observation & Photo Pipeline — End-to-End Review (v2, corrected)

- **Date:** 2026-04-20
- **Authors:** Agnes (review lead), Claude (investigator)
- **Status:** draft v2, pre-governance pre-reading
- **Purpose:** before writing more code, establish an accurate picture of
  how a WWOOFer observation flows from phone to QR page, what each ADR
  actually covers, and where the remaining gaps are.
- **Supersedes:** v1 of this doc (had an incorrect claim about
  multi-species new_plant submissions — corrected here).

This document feeds the governance session. It is not itself an ADR; it
is the input to a targeted ADR update: ADR 0008 amendment (new
invariants I8/I9/I10/I11/I12) and a short ADR 0005 clarification.

**2026-04-21 update:** I12 added after the P2R4.52-62/.62-72/.72-77
empty-page bug traced to 24 future-dated inventory logs silently ignored
by farmOS's `asset.inventory` recompute. See §6b I12.

---

## 1. The actual end-to-end flow (verified)

The observe page has exactly **two UI modes** and three submission paths:

| UI mode | User action | `observations[]` sent | `mode` field | Photos sent |
|---|---|---|---|---|
| **Single Plant — existing** | Tap plant in picker → optional photos → count/notes | 1 entry | `quick` | hero photo (optional) + any "Add more photos" (`target=plant`) |
| **Single Plant — new plant** | Tap hero camera → PlantNet ID → confirm species → count/notes | 1 entry | `new_plant` | **hero photo only** (PlantNet extra angles are NOT saved) |
| **Full Section** | Section notes + per-plant count/notes updates + section photos | N entries (one per updated plant) | `inventory` (or `comment`) | section photos only (`target=section`) — **no per-plant photo input** |

### Verified via Sheet data

Every `mode=new_plant` row in the submission Sheet has a **unique
`submission_id`** and `count=1`. Agnes's intuition was correct:
the UI correctly enforces one plant per new-plant submission. Maverick's
11 new-plant rows on 2026-04-03 are 11 separate submissions (all
rapid-fire in the same minute), not one batch.

### Filename convention (post-ADR-0005, shipped 2026-04-15)

`observe.js:935-955` prefixes every photo filename:

```
{sub_id_first_8}_{section_id}_{target}_{NNN}.jpg
```

- `target` ∈ {`plant`, `section`} — from `data-target` on the input.
- Hero photo (Single-Plant): `{prefix}_{section}_plant_001.jpg`.
- Extra angles (PlantNet path): NOT included in submission — only hero.
- "Add more photos" in Single-Plant: `{prefix}_{section}_plant_NNN.jpg`.
- "Add section photos" in Full-Section: `{prefix}_{section}_section_NNN.jpg`.

Apps Script `handleGetMedia` filters files by `{sub_id_first_8}_`
prefix, so cross-submission contamination in the Drive folder is
closed. ✅

---

## 2. What is NOT broken in the live pipeline

- ✅ **Single-Plant submissions (both `quick` and `new_plant`):**
  exactly one observation, one plant log, and only that submission's
  photos attached to that one log. Zero ambiguity. This is what Agnes
  wants: a clean, attributable new-plant record.
- ✅ **Submission isolation:** every submission's files have a unique
  UUID prefix; `handleGetMedia` filters on it; the Drive folder can
  hold many submissions without contamination.
- ✅ **Hero photo lifecycle:** `resetForm` (line 1067) clears
  `heroPreview.dataset.base64` between submissions — the leak that
  motivated ADR 0005 is closed.
- ✅ **PlantNet photos vs log photos:** extra PlantNet-ID angles are
  kept in a separate array (`plantnetPhotos`) and NOT submitted to
  farmOS. Only the hero photo becomes a file entity attached to the
  log. Clean separation.

---

## 3. What IS broken — three live defects + one UX clarity gap

### Defect A — Full-Section inventory: photos fan out across all plant logs

- **Scenario.** A WWOOFer uses Full-Section mode: updates counts on 7
  plants and uploads 3 section photos. Submission hits the importer.
- **What happens.** `import_observations` iterates the 7 observations
  (server.py:2069). For each, it calls `_attach_and_maybe_promote`
  which uploads **all 3 section photos** to that plant's observation
  log. Result: 3 photos × 7 logs = 21 file entities, photos showing on
  every plant card on the QR page.
- **What should happen.** Section photos belong on a section-level
  observation log (`asset_ids=[]`, `location_ids=[section_uuid]`).
  Per-plant logs get zero photos (they're pure count/condition updates).
- **Fix location:** `_attach_and_maybe_promote` routing logic +
  creating the section log (Phase 3c work in ADR 0008 addendum).

### Defect B — `create_plant` dumps full submission body to `asset.notes`

- **Scenario.** A WWOOFer submits a new plant (Single-Plant → new_plant
  mode). Importer calls `create_plant(... notes=_build_import_notes(obs, ...))`
  (server.py:1304). That function writes the full payload
  (`Reporter: X\nSubmitted: ...\nMode: new_plant\nPlant notes: ...\n
  Count: 0 → N\n[ontology:InteractionStamp] ...\n submission=<uuid>`)
  to the plant **asset's** `notes` field.
- **Why this is wrong.** The asset is a long-lived handle for the
  physical plant. Its notes should contain stable planting context
  (source, consortium role, special handling). The InteractionStamp
  + submission_id + field-note narrative belong on the observation log
  that accompanies the plant creation — which the same import already
  creates.
- **Fix location:** `create_plant` + TS mirror, plus backfill script
  to clean existing plant assets.

### Defect C — Generator renders `asset.notes` verbatim on section cards

- **Scenario.** User opens a QR section page. Every plant card shows
  the 400-char submission dump from Defect B as "notes."
- **Cause.** `export_farmos.py:721-729` reads `asset.notes` directly;
  `generate_site.py:514` renders it unescaped.
- **Fix location:** generator strips `[ontology:InteractionStamp]` +
  `submission=` lines; truncates to 120 chars; omits the block if the
  remainder is meaningless. Independent of Defects A/B; ships first.

### Defect D — "I observed / I did / Action needed" radios are dead UI

- **Scenario.** In Single-Plant mode, the form has three radio buttons
  at [generate_site.py:1131-1144](scripts/generate_site.py:1131):
  "👁 I observed" (default), "🔧 I did", "📌 Action needed". The
  selected value ships in the payload as `obs_type`.
- **What actually happens.** Verified: **no Python or TypeScript code
  reads `obs_type`.** The importer branches only on `mode`
  (quick / new_plant / inventory / comment). The radio's value is
  ignored. The only UI surface that shows it back to the user is the
  recent-submissions panel icon (observe.js:1263), which re-reads the
  submitted payload — a UI echo, not a data consequence.
- **Worse:** Full-Section (inventory) mode has NO such radios at all.
  So even if `obs_type` were honored, the signal is only present in
  half the submissions.
- **Consequence.** Log type (`observation` vs `activity` vs
  `transplanting` vs `seeding` vs `harvest`) is not actually governed
  by user intent today. Everything winds up as `log/observation`,
  regardless of what the text says. This violates ADR 0008 invariant
  I1 (log type correctness) at scale — the audit previously identified
  28 mis-classified logs (e.g., "chopped and dropped" logged as
  observation instead of activity).
- **Fix direction (Agnes's call):** drop the radios; derive log type
  and status from **notes text + ontology** at import time, as an
  enforceable invariant (see I11 below). UI simplification + semantic
  correctness in one change.

### UX-clarity gap — Add-new-plant: which photo is saved?

- **Scenario.** A WWOOFer taps the hero camera, takes a photo, PlantNet
  identifies the species. They're unsure so they tap "Add another
  angle (1/5)" and take a bark photo, a leaf photo, a flower photo.
  PlantNet now has 4 angles to identify from. They submit.
- **What gets saved to farmOS:** only the FIRST photo (hero). The
  other 3 angles were kept in JS-only `plantnetPhotos` array, used for
  PlantNet API, then discarded on submit.
- **What the user probably thinks:** "all 4 photos are evidence of
  this new plant."
- **Not a data defect** — attribution of the saved photo is correct.
  But there's user trust and evidence-completeness at stake.
- **Options:**
  - **U1.** Clearly badge the hero "will be saved" vs others "for
    identification only." Minimum change, maximum clarity.
  - **U2.** Save all 1–5 PlantNet angles as file entities on the log.
    Each gets its own numbered filename. Log shows all angles as
    evidence. More complete record but more storage.
  - **U3.** Let the user pick which angles to keep before submission
    (checkboxes). Most flexible, most UI complexity.
- **Recommendation.** U2 — save all angles. Reference photo
  promotion still picks one (I5 tier rules), but having all angles on
  the log makes later field re-ID trivial. Minimal code change: pass
  `plantnetPhotos` array into `collectMediaData`.

---

## 4. Verified legacy damage (separate from live pipeline)

Leah's 2026-04-14 submissions went through **pre-ADR-0005** observe.js,
so their files in Drive have filenames like `P2R5.29-38_plant_001_4.jpg`
with **no submission prefix**. When the April-19 re-attach script
walked Drive to recover the photos onto farmOS logs, it matched by
`(date, section)` heuristic, which attached multiple plants' photos
onto each plant log. That is how the Coriander log (`fc5f01ed`) ended
up with 6 photos from 5 different species.

- **Scope of legacy damage:** every Leah log from 2026-04-14 in P2R5.
  Need an audit tally.
- **Fix approach:** detach-and-delete (ADR 0005 Option B pattern).
  Since the original files still live in Drive, the photos aren't lost
  — they can be re-routed to a section log per submission or
  discarded if no safe routing is possible.

This is cleanup, not a live-pipeline bug.

---

## 5. What each ADR covers today

| ADR | Subject | Covers | Gap |
|---|---|---|---|
| **0001** | Photo pipeline attach-then-verify | Every photo uploaded unconditionally; PlantNet only gates species-reference promotion. | Doesn't specify per-log routing. |
| **0004** | Batch observation tools | Python/TS parity; batch = sequential loop. | Photo routing. |
| **0005** | Submission-scoped media | Filenames prefixed with `{sub_id_first_8}_`; `handleGetMedia` filters by prefix. Closes CROSS-submission contamination. | Doesn't specify what happens to photos from a multi-observation submission (Defect A). Says per-plant photo UI is "deferred" — we can now retire this as "out of scope by design" since the UX doesn't need it. |
| **0006** | FASF skills | `record_fieldwork` skill enforces I6 attribution at the agent layer. | Photo routing; asset notes. |
| **0007** | Import reliability | 6-fix stack (Fix 2 shipped). | Fix 4 (post-write verify) is supposed to catch all invariant breaks but wasn't scoped for asset notes or photo routing. |
| **0008** | Observation record invariant (I1–I7) | Seven invariants on log notes, photos, status, attribution, propagation. | Invariants govern LOG records, not asset records (Defect B). I4 is per-log, not about cross-log routing within a submission (Defect A). No QR render spec (Defect C). |
| **0008 addendum** | Phase 3 write-time enforcement | Phase 3a (I4 dedup), 3b (tier-aware I5) shipped. Phase 3c (section vs plant log split) specced, not shipped — this IS Defect A's fix. | — |

---

## 6. Proposed ADR updates

### 6a. ADR 0005 — inline addendum

Replace the "Open questions → per-plant photo capture UI" note with:

> **Closed: UX does not require per-plant photo capture in multi-
> observation submissions.** Full-Section inventory mode has no
> per-plant photo input by design — photos in that mode are section-
> level and attach to a section-level log (see ADR 0008 invariant I9).
> Single-Plant modes (quick and new_plant) have exactly one
> observation and one plant log, so all submission photos attach to
> that one log unambiguously.

### 6b. ADR 0008 — new invariants I8, I9, I10, I11, I12

Appended to "The Seven Invariants" section; renumbered to Twelve.

#### I8 — Asset notes hygiene

A plant asset's `notes` field must contain stable planting-context
text — INCLUDING the submitter's one-liner narrative — and NOT
the full submission metadata envelope:

- **Allowed:**
  - Planting date, seed/cutting source, consortium role, permanent
    notes ("grafted April 2026", "rootstock: Anna").
  - Submitter's narrative (text AFTER `Plant notes:` in the
    import payload, e.g. "Leah transcript 14 Apr 2026. two flowers
    observed"). Useful context on the QR card.
- **Forbidden:**
  - `[ontology:InteractionStamp]` lines — belong on the log.
  - `submission=<uuid>` fragments — same.
  - Metadata headers (`Reporter:/Submitted:/Mode:/Count:`) — no
    narrative, already captured on the log.
  - Boilerplate ("New plant added via field observation").
- **Rationale:** asset and log aren't duplicates. Metadata lives on
  the log. The narrative is cheap to keep on the asset and makes
  the QR card render useful context instead of empty.
- **Enforcement at write time:** `create_plant` sanitises via
  `sanitise_asset_notes`: drops stamp + submission + metadata-header
  lines; strips `Plant notes:` as a PREFIX, keeps the narrative.
- **Enforcement at audit time:** validator greps asset.notes for
  disallowed markers; backfill applies the same sanitiser.

#### I9 — Photo routing within a submission

Every photo file attached to a log must match the log's scope. Given
the current UX:

- **Single-observation submission** (`mode ∈ {quick, new_plant}`,
  `observations.length = 1`): all submission photos attach to the
  single observation log for that plant. Straightforward.
- **Multi-observation submission** (`mode = inventory`,
  `observations.length > 1`): all submission photos attach to ONE
  section-level observation log (`asset_ids=[]`,
  `location_ids=[section_uuid]`). Per-plant logs get zero photos —
  they are count/condition-only updates.
- **Never:** the same photo file attached to more than one log.
- **Rationale:** the UX does not capture per-plant→photo binding in
  inventory mode; photos are section-scoped by form construction.
  The importer must respect that.
- **Enforcement at write time:** `import_observations` decides log
  routing per submission, not per observation; creates the section
  log lazily; attaches each file exactly once.
- **Enforcement at audit time:** validator counts files shared
  across multiple logs within one submission and flags each as I9
  violation.

#### I11 — Log type & status derived from notes content, not UI

`type` (observation / activity / transplanting / seeding / harvest)
and `status` (pending / done) of an imported log must be derived
from the **semantic content of the notes text**, cross-referenced
with `knowledge/farm_ontology.yaml` verb/action mappings. They must
NOT be derived from a UI form radio button.

- **Rationale.** UI radios in Single-Plant mode are not honored by
  the importer today (Defect D), and have no counterpart in Full-
  Section mode. Even if we fixed the plumbing, relying on a
  submitter to self-classify every entry is fragile: volunteers
  won't read the taxonomy carefully. The text they write is the
  ground truth; the classifier reads it.
- **Classification rules** (initial, deterministic):
  - `seeded`, `sowed`, `seed`, `germinated` → `type=seeding`.
  - `planted`, `planting`, `plant` (as verb), `transplanted`,
    `transplant`, `moved`, `relocated`, `replanted` → `type=transplanting`.
  - `chop`, `chopped`, `dropped`, `pruned`, `prune`, `cut back`,
    `mulched`, `mulch`, `weeded`, `weed`, `watered`, `watering`,
    `sprayed`, `applied`, `inoculated`, `fertilised`, `composted`,
    `dug`, `tilled` → `type=activity`.
  - `harvested`, `harvest`, `picked`, `collected`, `yielded`,
    `gathered` → `type=harvest`.
  - `needs`, `should`, `to do`, `todo`, `urgent`, `action required`,
    `action needed`, `please`, `must`, `tbd`, imperative verb
    leading a sentence → `status=pending` (task/TODO).
  - Past-tense narrative of observed state without action verb →
    `type=observation`, `status=done`.
- **Ambiguity handling (Q5 policy).** If classifier confidence is
  below threshold:
  1. Log IS created (write succeeds — no submission lost).
  2. Default classification: `type=observation`, `status=pending`.
  3. `[FLAG classifier-ambiguous: <reason>]` marker prepended to
     the notes value (visible on the QR log-detail page and in
     farmOS UI).
  4. The log MUST surface to human review via ALL of:
     - `query_logs(status="pending")` — session-open protocol.
     - `validate_observations.py` as an I11 violation until
       reclassified.
     - A dedicated MCP tool `list_classifier_ambiguous(scope=...)`
       that returns the review queue with classifier reasoning.
     - The `farm_context` integrity gate flags the backlog size.
  5. Human reviewer reclassifies via `update_observation_status`
     (or a new `reclassify_log` tool). Correction is recorded.
- **Continuous learning (Q5b).** Every human correction is logged
  to a persistent `classifier_corrections.jsonl` (or team-memory
  entry) recording:
  `{log_id, original_notes, classifier_output, human_correction,
  reviewer, timestamp, reason_if_given}`. This record feeds:
  - **Rule tuning** for the deterministic classifier: new verbs or
    patterns Agnes/Claire add to the verb list when a class of
    error shows up repeatedly.
  - **Few-shot examples** for the skill upgrade (Step 9): the
    corrections become training data the agent references at
    classification time.
  - **Accuracy metric** surfaced via `system_health()`: classifier
    first-attempt success rate. Degradation triggers a review.
- **Enforcement at write time:** every log-creating path in the
  importer runs the classifier and sets type/status accordingly.
- **UI consequence:** remove the `obs-type` radio group from the
  Single-Plant form. The UI becomes: optional photo + count +
  condition + free-text notes. That's what the submitter can
  actually judge; semantic labeling is not their job.
- **Future upgrade path (post-ratification of FASF, ADR 0006):**
  swap the deterministic classifier for an agent-skill
  `classify_observation(notes) → {type, status, confidence,
  reasoning}`. Low-confidence cases queue for human review; the
  skill learns from reviewer corrections over time (skill
  invariant inheritance).
- **Enforcement at audit time:** validator I11 check flags any log
  whose type/status disagrees with what the classifier would have
  assigned from its notes — signals either a classifier bug
  (tune the rules) or a legacy mis-classified log (cleanup
  backlog).

#### I12 — Inventory log timestamps must not be in the future

Any log carrying a quantity with non-empty `inventory_adjustment`
(`reset` / `increment` / `decrement`) must have `timestamp ≤ now`.

- **Rationale.** farmOS's computed `asset.inventory` field is
  derived from `reset` adjustments on logs with `timestamp ≤ now`.
  Future-dated resets are silently dropped from the recompute —
  the log and qty exist, relationships are intact, but
  `asset.inventory` stays stale. The QR page renders "0 plants"
  while farmOS holds a positive count. Silent-data-loss class:
  no write error, no validation failure, surfaces only when a
  human notices a missing section. Root-cause trace: the 24
  mis-dated `2026-12-18` logs (year typo for `2025-12-18`, batch
  import 7 March 2026) produced the empty P2R4.52-62 / .62-72 /
  .72-77 pages reconciled 2026-04-21.
- **Enforcement at write time:** `parse_date` (Python) and
  `parseDate` (TS) raise a validation error if resolved timestamp
  exceeds `now + 24h`. 24h grace for AEST↔UTC edge cases; tight
  enough to block year-typo dates. `update_inventory` always uses
  today, unaffected. `create_observation` / `create_plant` /
  `import_observations` / `create_seed` fail fast on caller-
  supplied future dates.
- **Enforcement at audit time:** validator I12 check greps every
  log with `quantity--standard` relationship whose
  `inventory_adjustment` is non-empty and flags any with
  `timestamp > now + 86400`. Report `{log_id, asset_ref,
  timestamp, delta_days}`.
- **Legacy cleanup:** backfill script re-dates existing future-
  dated inventory logs (year-typo heuristic: subtract 1 year if
  resulting date resolves to the past; else flag for human
  review).
- **Out-of-scope:** direct JSON:API writes bypass MCP; operators
  of those paths are also responsible for the
  `inventory_asset`/`units` quirk documented in
  `reference_farmos_inventory_quirks.md`. Validator I12 check
  catches violations from any source.

#### I10 — QR render hygiene

The site generator must render invariant-respecting output:

- **Plant card (section view):** `plant.notes` is rendered only
  after stripping `[ontology:InteractionStamp]` and `submission=`
  lines. Remaining content is truncated to 120 characters. If the
  stripped content is empty or trivial, the notes block is omitted.
- **Log-detail page:** full `notes.value` is rendered with the
  InteractionStamp moved to a "Provenance" block. This is the
  current behaviour of `render_log_detail_page` — codify as I10.
- **Section page:** section-level logs (`asset_ids=[]`) render in a
  dedicated "Field observations" block above the plant inventory.
  Phase 3c spec.

---

## 7. Proposed implementation order

Once ADR 0008 amendment is ratified:

1. **Generator strip + truncate** ([generate_site.py:514](scripts/generate_site.py:514))
   — independent, same-day, no farmOS write. I10 partial.
2. **`create_plant` notes split** — stop writing submission body to
   asset.notes; keep only on the accompanying observation log. Python
   + TS. I8 write-time enforcement.
3. **Add-new-plant UX: save all PlantNet angles** — pass
   `plantnetPhotos` into `collectMediaData` so every angle is uploaded
   as a file entity on the new plant log. Visible badges already
   identify them.
4. **Importer photo routing (Phase 3c)** — build
   `route_media_to_logs` helper in Python + TS; multi-observation
   submissions create a section log and attach all photos there;
   per-plant logs get none. I9 write-time enforcement.
5. **Deterministic log-type classifier + remove UI radios** — new
   `classify_observation(notes)` function in both servers using
   ontology verb mappings; used by importer to set `type` + `status`
   on every created log. Remove `obs-type` radio group from observe
   form. I11 write-time enforcement. (Step-order note: ship the
   classifier BEFORE removing the UI so we have a fallback if the
   classifier misbehaves; UI removal is a trivial follow-up.)
6. **Validator I8 + I9 + I10 + I11 + I12 checks** — add to
   `scripts/validate_observations.py`. Run P2 audit to quantify
   backlog.
7. **Backfill script** — detach I8-violating content from asset notes
   (keep narrative, drop stamp + submission lines), detach I9-
   violating cross-log photos (create section log per affected
   submission, move photos there, delete file entities that can't be
   safely routed per ADR 0005 Option B), re-type I11-violating logs
   via classifier, re-date I12-violating future-dated inventory logs
   (year-typo heuristic, human review for ambiguous cases).
8. **Phase 3c render** — section-level log block on the section QR
   page. I10 completion.
9. **I12 write-time guard** — `parse_date` / `parseDate` reject
   `ts > now + 24h`. Ships same commit as validator I12. Tests
   cover: year-typo rejected, today accepted, today + 12h accepted
   (AEST edge), today + 2d rejected.

Steps 1 and 6 can ship same-day without disruption. Steps 2–5 are the
pipeline fix. Step 7 is legacy cleanup. Step 8 is render.

Post-ratification of FASF (ADR 0006, deferred per Agnes's Q3):
**Step 9 — skill upgrade.** Swap the deterministic classifier in Step
5 for an agent-skill `classify_observation` with confidence scoring +
human-in-loop for low-confidence cases. Skill learns from reviewer
corrections. No invariant change — I11 remains the contract.

---

## 8. Open questions for governance

- **Q1 — Add-new-plant PlantNet angles (§3 UX gap):** save all 1–5
  angles on the log (U2) vs badge-only clarity (U1)? **Agnes
  answered: save all (U2) in Q1.**
- **Q2 — Legacy orphan cleanup:** detach + delete per ADR 0005 Option
  B? **Agnes answered: yes (detach + delete).**
- **Q3 — Ratification order:** ADR 0008 amendment first. **Agnes
  answered: amendment first; skills after everything works.**
- **Q4 — obs-type radios (Defect D / I11):** drop from UI, derive log
  type + status from notes content via classifier. **Agnes answered
  (this turn): classifier-driven, deterministic first then skill
  upgrade; radios either dropped or repeated on all forms (leaning
  drop).** Assumption locked unless governance objects.
- **Q5 — Classifier failure-mode policy:** when classifier confidence
  is low, default to `observation` + `pending` with a `[FLAG
  classifier-ambiguous]` marker. **Agnes answered (this turn):
  succeed-with-flag, conditional on the flag systematically
  surfacing for human review.** Surfacing requirements now part of
  I11 (see §6b): pending-logs listing, validator violation, dedicated
  MCP review queue, farm_context backlog visibility.
- **Q5b — Continuous learning:** every human reclassification is
  captured as a persistent correction record, feeds rule-tuning now
  and skill few-shot examples later. **Agnes requested.**

---

## 9. Not in scope

- No UX redesign beyond the add-new-plant angles saving change.
- No Observations.gs changes beyond current ADR 0005 shipment.
- No KB / seed bank / harvest pipeline changes.
- No scope change to the seven existing invariants — I8/I9/I10/I11/I12 extend.

---

*End of review v2. Next action: ratify → implement steps 1–7 in order.*
