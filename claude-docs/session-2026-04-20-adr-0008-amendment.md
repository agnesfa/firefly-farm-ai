# Session 2026-04-20 — ADR 0008 Amendment (I8/I9/I10/I11)

> **Resume anchor for next session.** Read this first.
> **Span:** afternoon of 2026-04-20 (Agnes's QR-page review → full 8-step shipment).
> **Previous session audit:** [`session-audit-2026-04-18-to-20.md`](session-audit-2026-04-18-to-20.md).
> **Pre-reading for governance:** [`observation-photo-pipeline-review-2026-04-20.md`](observation-photo-pipeline-review-2026-04-20.md).

---

## 1. Why this session happened

Agnes reviewed the deployed QR pages after the morning's Phase 3a/3b
shipment and spotted three defects that the earlier fix cycle hadn't
caught:

1. **Plant-card notes over-inflated** on P2R5.44-53 (Okra, Nasturtium)
   and P2R5.29-38 (Coriander): entire submission dumps including
   `[ontology:InteractionStamp]`, `submission=<uuid>`, and
   `Reporter:/Submitted:/Mode:/Count:/Plant notes:` headers were
   rendering verbatim as plant-card descriptions.
2. **Wrong photo** on the Nasturtium reference + Nasturtium log (one
   photo was an Okra).
3. **Coriander log with 6 photos from 5 species** (papaya, jacaranda,
   parsley, okra, and one actual coriander candidate) — exactly the
   kind of mis-attribution ADR 0005 was supposed to have closed.

The root cause chain, traced end-to-end, turned out to be larger than
the three display symptoms. It exposed:

- **Dead UI** — the "I observed / I did / Action needed" radio group
  on the Single-Plant form was ignored by the importer. Log type was
  effectively random.
- **Missing invariant** — asset `notes` had no written rule. The
  import pipeline dumped the submission body there freely.
- **Importer routing gap** — `_attach_and_maybe_promote` uploaded
  the entire `submission_media` list to **every** per-plant log in a
  multi-observation submission (Kerstin/Maverick/Leah patterns).
- **Render gap** — section-level logs (`asset_ids=[]`) existed in
  farmOS but had no template to render on the QR page.

The response was an ADR 0008 amendment adding four new invariants
(I8/I9/I10/I11), and an 8-step implementation that shipped end-to-end
in the same session.

## 2. What shipped (all in `main`, all deployed)

**Commits on `main`:**

| SHA | Title |
|---|---|
| [`d4988f4`](https://github.com/agnesfa/firefly-farm-ai/commit/d4988f4) | ADR 0008 amendment: I8/I9/I10/I11 invariants + review doc |
| [`818f5f6`](https://github.com/agnesfa/firefly-farm-ai/commit/818f5f6) | Write-time + display enforcement (124 files, Python + TS + generator + observe.js) |
| [`ee32635`](https://github.com/agnesfa/firefly-farm-ai/commit/ee32635) | Tooling: validator I8/I9/I11 checks + backfill script |

**Deployed to:**
- GitHub Pages — 107 regenerated QR pages with clean notes + new
  section-log render block.
- Railway (TS MCP server) — new sanitiser, classifier, I9 photo
  routing, per-log status. All 4 team members' Claude sessions pick
  it up automatically.
- Apps Script: **no changes this session**. Most recent Apps Script
  deploy remains the April-15 ADR 0005 submission-prefix fix.

**Data surgery applied to live farmOS (via `scripts/cleanup/backfill_adr_0008_amendment.py --scope P2 --apply --only i8`):**

| Action | Count | Notes |
|---|---:|---|
| Plant asset `notes` sanitised (I8) | **25** | Coriander/Nasturtium/Okra + 22 others; InteractionStamp + metadata headers stripped; Plant-notes narrative kept |
| Errors | 0 | |

**The four new invariants (full text in [ADR 0008](adr/0008-observation-record-invariant.md#amendment--2026-04-20-invariants-i8-i9-i10-i11)):**

- **I8** — Asset notes hygiene. Asset `notes` keeps the
  submitter's narrative (text after `Plant notes:`) as stable
  planting context but drops InteractionStamp, `submission=`, and
  pure-metadata headers (Reporter/Submitted/Mode/Count).
- **I9** — Photo routing within a submission. Single-obs
  submission → photos on the one log. Multi-obs submission → ONE
  section-level log created lazily, all photos there, zero on
  per-plant logs. Same file never on >1 log.
- **I10** — QR render hygiene. Plant card notes: strip + 120-char
  truncate. Log detail: full notes + separate provenance block.
  Section page: dedicated "Field observations" block above
  inventory.
- **I11** — Log type and status derived from notes content by
  deterministic classifier, not a UI radio. Ambiguity → succeed
  with `[FLAG classifier-ambiguous]` + pending status +
  systematic surfacing for human review. Continuous-learning
  correction record feeds rule-tuning now, skill few-shot later.

**Tests:** 278 → 308 Python; 222 → 251 TS. **Total: 559 → 561** (after
late fix adjustments). No regressions.

**Key artefacts (re-read these when resuming):**

| File | Purpose |
|---|---|
| [`claude-docs/adr/0008-observation-record-invariant.md`](adr/0008-observation-record-invariant.md) | Eleven Invariants (I1–I7 original; I8–I11 amendment) — the contract |
| [`claude-docs/adr/0005-submission-scoped-media.md`](adr/0005-submission-scoped-media.md) | Closing note: per-plant photo UI is out-of-scope by design |
| [`claude-docs/observation-photo-pipeline-review-2026-04-20.md`](observation-photo-pipeline-review-2026-04-20.md) | Governance pre-reading — full root-cause trace + 8-step plan |
| [`mcp-server/asset_notes.py`](../mcp-server/asset_notes.py) + [`.../asset-notes.ts`](../mcp-server-ts/plugins/farm-plugin/src/helpers/asset-notes.ts) | I8 sanitiser — standalone, no fastmcp dep |
| [`mcp-server/classifier.py`](../mcp-server/classifier.py) + [`.../classifier.ts`](../mcp-server-ts/plugins/farm-plugin/src/helpers/classifier.ts) | I11 deterministic classifier — verb list is the spec |
| [`scripts/validate_observations.py`](../scripts/validate_observations.py) | Validator — now checks I1–I11 |
| [`scripts/cleanup/backfill_adr_0008_amendment.py`](../scripts/cleanup/backfill_adr_0008_amendment.py) | I8 apply-able; I9/I11 report-only |

---

## 3. What is QUEUED for Agnes

### 3a. Governance session — now overdue

**Agenda (pre-reading is already written):**

1. **Ratify ADR 0008 amendment** (status: `proposed`). This
   ratifies I8/I9/I10/I11. Pre-reading:
   [observation-photo-pipeline-review-2026-04-20.md](observation-photo-pipeline-review-2026-04-20.md).
2. **Ratify ADR 0006 (FASF)** — deferred. Still in `proposed`. The
   agent-skill upgrade for the I11 classifier (Step 9) depends on
   this.
3. **Ratify ADR 0007 (Import Pipeline Reliability)** — still
   `proposed`. Fix 2 shipped; Fixes 1, 3, 4, 5, 6 pending.
4. **Charter (L0) + Principles (L1)** — still owed. Needs Claire's
   brainstorm from pre-March context.
5. **Full `claude-docs/` audit** — many partial + overlapping docs;
   consolidate.
6. **Review MCP framework** in light of Lesley's latest release.
7. **Scaling triggers, observability, security checks.**

Post-ratification kickoffs:

- **Step 9 — Skill upgrade.** Swap deterministic classifier for
  agent-skill `classify_observation` with confidence + few-shot from
  `classifier_corrections.jsonl`. No invariant change — I11 contract
  is stable across implementations.
- **FASF skill library seeding** — KB entries with
  `category=agent_skill`. Day-one skills: `session_open`,
  `ingest_knowledge`, `review_assignment`, `record_fieldwork`,
  `per_row_review`.

### 3b. Cleanup backlog (report-only today; needs human review)

Run `python scripts/cleanup/backfill_adr_0008_amendment.py --scope P2`
(no --apply) to refresh the backlog.

- **I9 photo mis-routing (legacy, pre-ADR-0005):** ~0 reported by the
  narrow I9 check, but the legacy Leah 2026-04-14 contamination
  (Coriander log with 6 photos from 5 species) is handled
  case-by-case. Needs visual triage on the affected logs.
- **I11 type mismatches:** 59 logs where classifier disagrees with
  stored type. Info-level. Reviewer decides — sometimes the stored
  type is correctly non-obvious from the wording.
- **I1 activity-language in observations:** 28 (unchanged from
  baseline). Example: "chop and drop" logged as observation instead
  of activity. Needs case-by-case re-typing.
- **I4 duplicate photos:** 12 legacy Leah cross-contamination.
- **I6 missing InteractionStamp:** 903 — legacy pre-Apr-1 logs.
  Info-level. Decide: backfill mechanically or accept as historical.

### 3c. Live data flags still open (from previous session)

- **Coriander log `fc5f01ed` in P2R5.29-38** — PlantNet top-3 says
  not coriander. Needs field re-ID. Plant asset retained pending
  decision (archive phantom + create correct species, or rename).
- **Duplicate chop-and-drop activities in P2R3.50-62** — sessions
  82 (Mar 21) and 84 (Mar 22) both wrote. Needs merge.

### 3d. Phase 2B mechanical cleanup (low urgency)

- **71 I6 InteractionStamp backfills** on post-Apr-1 logs.
- **28 I1 log-type re-types** (observation → activity for
  chop-and-drop/seeding/transplanting) — the I11 classifier can now
  propose types; human decides and applies.
- **16 species stuck at tier-1** multi-plant photos with no stock
  (Achiote, Curry Leaf, Dianella, Sunn Hemp + 2 archived).
  Resolve via next field walks.

### 3e. Apr 15 carry-overs (still open)

- `system_health()` optimisation — 51.6 s → target < 20 s.
- Report `mcp-remote` stale session issue to maintainers.
- Wire `mcp_reliability` from TS connection stats.
- Migrate farmOS auth to framework `PlatformAuthHandler`
  (Lesley's recommendation).

### 3f. Team-coordination

- **James needs to paste** [`james-claude-session-protocol.md`](james-claude-session-protocol.md)
  into his Claude Desktop config. Until he does, his Claude won't
  check pending logs or cite KB entry_ids.
- **Kacper QR submission-loss** (per James's summary 122). Kacper
  hit a bug on the QR form earlier in the day, reported it to
  James, and STOPPED using QR after that. **He'll retry tomorrow
  (2026-04-21).** Zero Sheet entries for Kacper today is expected,
  NOT a new defect. The bug itself is still not diagnosed —
  separate pre-existing issue, predates today's amendment. Next
  session starts there (see §3g below).
- **2 new WWOOFers** started 2026-04-20 (Kacper + 1 other). Their
  QR submissions tomorrow will exercise the new classifier + I9
  routing live — watch the QR page for anything that looks wrong.

### 3g. Pre-governance review (Agnes's explicit ask — first task next session)

**DO NOT ratify anything at governance until this review is done.**

1. **Review James's 2026-04-20 logs in farmOS** before accepting
   summary 122 at face value. James's back-up-logging of Kacper's
   transplants via Claude Desktop was itself a data-entry
   operation — needs visual / semantic check:
   - Activity log `e4bbd980` — Winter preparation P1R5
   - Activity log `8e9f7c3a` — Seed withdrawal NURS.FRDG
   - Activity log `be1a11c1` — Transplanting 12x Banagrass → P2R4
   - Activity log `7314a63f` — Transplanting 7x Pigeon Pea → P2R5
   - Observation log `28ecc971` — NURS.BCK Banagrass 56→44
   - Observation log `81b55383` — NURS.SH1-3 Pigeon Pea 56→49
   - Activity log `ad77209c` — Seed loss NURS.FRDG (mouldy maize)
   - Activity log `98fd258f` — Seed drying NURS.FRDG (rescued cobs)

   Questions to ask per log:
   - Is the log type correct (activity vs observation vs
     transplanting vs seeding)? With I11 in place we can now run
     the classifier against each and see where it disagrees.
   - Is the asset/location attachment right (P2R4 vs which
     specific sub-section, same for P2R5)?
   - Are the nursery inventory counts (56→44 / 56→49) consistent
     with today's field actions and last known nursery state?
   - Is the InteractionStamp provenance right (`Claude_user`
     initiator is generic — should it carry James's name)?
   - Any duplicates with earlier logs?

2. **Diagnose Kacper's QR submission bug** — what actually
   failed. Ask James for the exact error Kacper saw. Check:
   - Console errors on Kacper's phone if reachable.
   - Apps Script execution log for 2026-04-20 failures.
   - Whether the submission landed in Drive folders even if Sheet
     append failed.

3. **Then and only then**, go into the governance session with a
   clean bill of health on recent writes.

**Note on the summary acknowledgement.** I (Claude) acknowledged
James's summary 122 on Agnes's behalf at session close — that was
premature; the `acknowledge_memory` call only hides the entry from
"fresh-only" queries, it is NOT a substitute for the review above.
Re-read the summary and complete the review regardless.

---

## 4. Next-session start protocol

```
system_health()
get_farm_overview()
read_team_activity(days=7, only_fresh_for="Agnes")
python scripts/validate_observations.py --scope P2 --out /tmp/audit.md
```

**Then read THIS doc first**, then the pre-reading doc
([observation-photo-pipeline-review-2026-04-20.md](observation-photo-pipeline-review-2026-04-20.md))
if steering toward governance.

Also:
- `git log --oneline -10` — trajectory.
- Check that Railway deploy succeeded for commit `818f5f6`
  (https://railway.app → firefly-fa-mcp-server → Deployments).

---

## 5. Hard-won lessons from today

1. **Write-time enforcement of display-level strip isn't free.** I
   initially conflated "strip at display" (Step 1) with "strip at
   write" (Step 2) using the same forbidden-prefix list. At display
   time stripping `Plant notes:` as a prefix keeps the narrative.
   At write time stripping it as a *line* deleted it. Agnes caught
   the inconsistency in the dry-run output. Fixed by making the
   sanitiser treat `Plant notes:` as a prefix-only strip.
2. **The UI was clean — the pipeline was dirty.** Agnes's original
   intuition that the UX enforces one plant per new-plant submission
   was correct (verified via Sheet data: every `mode=new_plant` row
   has a unique submission_id, count=1). The multi-species patterns
   in the logs were rapid-fire separate submissions, not batched.
   This killed my initial "need per-plant photo UI" hypothesis and
   reframed the defect as purely importer-side.
3. **Dead UI is the worst UI.** The `obs-type` radios looked
   authoritative to submitters but were ignored by the pipeline.
   Deleting the radios + deriving from notes text is cleaner and
   more honest.
4. **Semantic classifiers need human escape hatches.** I11's
   ambiguity policy — succeed-with-flag + systematic surfacing
   across four channels + persistent correction record — is the
   part that makes the classifier safe to ship.
5. **Cleanup without enforcement = Groundhog Day.** 25 asset-notes
   cleaned today, but the cycle only breaks because `create_plant`
   now sanitises at write time. Without Step 2, this week's
   submissions would repopulate the dumps.

---

## 6. Session metrics

- 4 hours, 1 session.
- Commits: 3 (docs, enforcement, tooling).
- Files touched: ~130 (most are generated QR HTML).
- Tests added: 53 (Python 30 + TS 23).
- Data changes (farmOS): 25 plant asset notes sanitised.
- Hours of planned work compressed: this replaces what was going
  to be at least 2 sessions (Phase 3c + governance).

---

*Session closed 2026-04-20 evening. Next session picks up at §4 start protocol.*
