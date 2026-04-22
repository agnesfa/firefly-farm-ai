# Pending decisions — 2026-04-22 autonomous import session

**Context:** Agnes stepped out ~10:00 AEST. Claude processing the remaining 49-submission backlog under auto-handled rules agreed beforehand; flagging anything that needs her call.

**When you're back:** scan this doc, tell Claude "approve #N" / "reject #N" / "defer #N", and Claude will execute.

---

## Flags (append-only, most recent at bottom)

### F1 — NURS.GR junk row with empty submission_id
- Row: James, 2026-03-22, NURS.GR, empty submission, no plants, no notes
- Issue: `update_observation_status` requires a submission_id; empty string doesn't match any row. No MCP tool exposes row_id updates.
- **Decision needed:** either fix the row manually in the sheet (flip Status to "rejected" directly), or leave as permanent pending noise, or extend the MCP tool to accept row_id as an alternative.
- Impact: none on imports, just visible as 1 pending row in every queue query. Defer.

### F2 — P2R5.8-14 Coriander species-identification question
- Submission 8e3c3d0c imported (Kacper's 2→0 "No coriander observed" observation) with note preserved.
- Kacper's field note also said: *"Species picture looks the same as jacaranda — possibly incorrect."*
- The existing P2R5.8-14 Coriander plant_type may be misidentified — could actually be Jacaranda.
- **Decision needed:** same pattern as Sweet Potato → Potato reclassification. If confirmed misidentified, archive the Coriander plant asset in P2R5.8-14 + optionally create Jacaranda asset. Per feedback_check_adrs_before_fixing + species-reclassification rule, I didn't act without your call.
- Imported data: Kacper's 2→0 "no coriander observed" log + photo (if any). Safe to leave as-is until you decide.

### F3 — Cuban Jute unknown-species note (P2R5.22-29)
- Kacper's inventory 23603752 included section_note *"Unknown species found in the section - automatic recognition points at Cuban Jute."*
- Section log imported with the note (single copy — section_notes dedup fix working).
- **Decision needed:** create Cuban Jute plant_type in taxonomy? Requires agronomy review (is it Cuban Jute or something else? strata + succession?). Defer until next field walk or direct confirmation.

### F4 — 35 stale pre-tonight approved-but-not-imported submissions
After tonight's clear, the `approved` queue still holds 35 submissions from earlier passes that were approved but never imported. Breakdown:
- **10 Maverick (2026-04-03)** on P2R5.8-14 (10), P2R5.22-29 (4), P2R5.29-38 (3). All `new_plant` mode registering counts that are now already reflected in existing farmOS plant assets — re-importing would likely create duplicate plant assets. Risk: high.
- **3 Kerstin (2026-04-03)** on P2R5.38-44 — Okra, Pumpkin, Cowpea `new_plant`. Existing plant assets from earlier walks cover these.
- **9 Daniel (2026-03-17–18)** on P1R3 sections — all `comment` mode activity reports (chop-and-drop, weeding, green manure). Low risk to import as activity logs; could be useful operational history.
- **1 Olivier (2026-03-17)** on P2R1.16-25 — water-leak comment. Low risk activity log.
- **3 Hadrien (2026-03-11)** on P2R2.16-23/.23-26 — includes **an Achiote reclassification** ("The passion fruit was in fact an Achiotte") = species reclassification, flagged.
- **1 Agnes (2026-03-09)** on P2R1.0-3 — Mint "Found it!"

**Decision needed:** for each batch, approve-import / reject / defer. I didn't auto-process these per the "don't risk duplicates" rule for stale approvals. Daniel's activity-log comments are the safest batch to import if you want to fill in the historical record.

### F5 — Pipeline observations captured tonight (no decision needed, just FYI)
Captured in logs / memory so you can pick up the thread:
- Client timeouts on inventory-mode submissions remain routine (server completes, client disconnects ~45s). ADR 0007 Fix 3 async queue is the real fix. Until then, chunks of 2 per batch + verify-after-timeout is the workable pattern.
- PlantNet warning "configured but never called" appears on multi-species section-log imports — expected (no single species to verify against for section-log photos). Not a bug, just noise in the report.
- The `same_name_prior_log` marker (ADR 0007 Fix 5 minimal) is now emitted on action results when a same-day same-species log from a different submission is detected. If you ever see this in an import result, it's the forward-compat surface for full Fix 5 operator-confirm flow.

---

## Auto-handled rules for this session
- Duplicates within same minute → reject one (prefer the one with notes)
- Self-corrections ("discard previous") → reject older, keep newer
- Superseded counts within same hour same observer → reject older
- Dead / missing observations → import as-is
- Condition notes (yellow, eaten, brown, etc.) → import as-is
- Cowpea harvest section_notes → import as activity log per A2 (I13 deferred)
- James's NURS.GR empty junk → reject

## What will NOT be auto-handled (flagged instead)
- New plant_type creation (e.g. Cuban Jute)
- Species reclassification ("not X, it's Y")
- Ambiguous PlantNet overrides
- New bug class discovery → halt + save state
