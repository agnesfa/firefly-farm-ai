# UX Review — Deferred Items (Post-v4 Migration Backlog)

**Author:** Agnes + Claude, 2026-04-23
**Context:** Captured during the Apr 23 verification walk. Surfaced while testing the observation pipeline end-to-end on field + nursery QR pages.

**Guiding principle** — memory `feedback_ux_must_be_bulletproof.md`: Firefly Corner runs on continuous WWOOFer turnover (~every 2 weeks) plus rotating Hipcamp / Landcare visitors. Every interface is effectively **first-time use, every time**. UX hardening is not "polish" — it is core infrastructure.

**Shipping today (2026-04-23), NOT in this doc:**
- **Fix A** — Floating toast for submit confirmation (fixed-position banner + 8s timeout on inventory/comment)
- **Fix B** — Nursery inline form canonical payload shape (`observations[]` + `submission_id` + `section_notes`)
- **Fix D** — Server-side shape validation in `Observations.gs` (reject payloads that are neither `observations[]`-bearing nor `section_notes`-bearing)

Everything below is deferred to post-v4 migration (2026-04-27+) and should be re-prioritised during the first UX-focused session after cutover.

---

## 1. Nursery "Add plant" flow — full design pass

**Problem:** Empty nursery zones (e.g. `NURS.STWB`) can't have plants added. The inline per-plant form only edits existing inventory. No field equivalent of the `new_plant` mode exists for nursery.

**Why deferred:** Nursery data model is materially different from field. A proper design needs to capture:
- **Container type:** pot size (e.g. 0.5L / 1L / 2L tubestock), tray, ground bed, cutting jar, seedling raft
- **Container count:** how many pots / trays / etc.
- **Propagation method:** seed (new_count = seeds sown), cutting (new_count = cuttings taken, parent plant reference), division, air-layer, transplant-in
- **Source:** seed_bank (which lot), nursery (parent plant id), purchased (supplier), gift (from whom)
- **Stage:** germinating, seedling, juvenile, ready-to-transplant
- **Expected transplant-out window:** weeks-from-now or target date
- **Parent plant reference:** for cuttings/divisions — auditable propagation chain

None of these fields exist in the current flat `observations[]` schema. Adding them ad-hoc would be a significant data model debt.

**Recommended scope for design session:**
- Agnes + Claire walk through actual nursery use cases (seed sowing, cutting-take, pot-up, transplant-ready flag)
- Decide whether nursery observations become a distinct `mode: nursery_add` with structured fields, OR stay in `new_plant` with a nursery-specific notes schema
- Decide whether `plant_type` alone is enough or if we need a `propagation_event` first-class entity in farmOS
- Decide UX: inline on view page (quick) vs dedicated nursery observe page with full fields (thorough)

**Interim (post-v4, pre-full-design):** Simplest unblocker is a "+ Add plant" inline form on the nursery view page that only captures species + count + notes (notes holds the propagation details as free text for now). That gets us out of the "NURS.STWB is permanently empty" trap without committing to a data model.

---

## 2. Full nursery observe page (parity with field)

**Problem:** `NURS.*-observe.html` pages exist on disk but are (a) unreachable from view pages (no FAB), (b) broken — `plants: []` hardcoded in the generator, (c) only offer `quick` + `comment` modes. Field sections have all four (`quick`, `new_plant`, `inventory`, `comment`) plus photo capture + PlantNet + section-notes.

**Why deferred:** Depends on #1 above (data model). Once the nursery add-plant flow is defined, regenerate the nursery observe page using the same template as field + nursery-specific overrides for add-plant fields.

**Acceptance:**
- FAB "📋 Record Observation" + "🔍 Identify" visible on every nursery view page
- Observe page offers 4 modes: quick, new_plant (nursery-specific fields per #1), inventory, comment
- Section-level notes supported
- Photo capture + PlantNet integration
- Feeds the same Apps Script endpoint with canonical payload shape

---

## 3. Nursery inline form — photo capture

**Problem:** The inline per-plant mini-form on nursery view pages has no file input. Every nursery observation today is photo-less. Quality photos of nursery plants are critical for Claire's tier-2+ species reference photo promotion (I5 tier classifier).

**Why deferred:** Inline form is tight vertically. Adding a proper camera affordance needs design (icon button? expandable panel?) that matches the field observe page's camera hero without breaking the inline form's compactness.

**Acceptance:**
- A camera / file-upload button on each inline form
- Captured photos attach to the submission, routed to the right log by the importer
- Same tier classifier applies (tier-3 eligible, promotable to species reference)

---

## 4. Section-log block — cap to 2-3 + separate listing page

**Source:** Yesterday's note in `claude-docs/pending-decisions-2026-04-22.md` §"QR page enhancement backlog".

**Problem:** Section view pages show up to 5 recent section logs with full text + up to 6 thumbnails each ([generate_site.py:700](scripts/generate_site.py:700)). Busy sections push plant content below the fold. Mobile-first pages need plants as primary signal.

**Short-term proposal:**
- Cap visible section logs to 2-3 most recent
- Add "+ N more activities" link → expands inline or opens dialog

**Long-term proposal:**
- Dedicated `{section_id}-observations.html` listing page with pagination + filter by observer / mode / date
- Mirrors the log-detail page pattern (one-click from section view → full context on dedicated page)
- Visitor-vs-farmhand duality: visitors stay on the slim view page, farmhands one-click deeper

**Scope:** Moderate — template changes in `generate_site.py` + new page generator function. Probably 1-2 hours.

---

## 5. Identity confirmation prompt

**Problem:** Today (2026-04-23), the test submission for NURS.SH1-4 came in under "Claire" because Agnes forgot to change the name field. The field defaults to the last-saved name from `localStorage.getItem("firefly_observer_name")`. No confirmation prompt before submit.

**Why serious:** Identity attribution on observations matters — it determines who gets "fresh" in `read_team_activity`, who owns cleanup tasks, and whether InteractionStamps reflect the real actor. "Wrong name stuck from yesterday's session" is a recurring failure mode for a volunteer-churn team.

**Proposal options (pick one or combine):**
- **Option X:** Before submit, show a confirm dialog: "Submitting as **Claire** — correct? [Yes, submit] [Change name]". Adds a click but prevents attribution errors.
- **Option Y:** Make name field visually prominent on every page load (e.g. persistent pill at top of observe page: "Observing as Claire — [change]"). Less intrusive but less forcing.
- **Option Z:** Timebox the saved name — expire localStorage identity after N hours of inactivity, force re-entry on next session. Combines with X or Y.

**Recommendation:** Y + Z together — prominent display + 12h expiry. Non-intrusive for rapid-fire submissions within a session, but forces fresh attribution when a new person picks up the tablet the next morning.

---

## 6. Recent-submissions panel visibility

**Problem:** The "Recently submitted" panel rendered by `renderRecentSubmissions()` in [observe.js:1236](site/public/observe.js:1236) has the same scroll issue as the `obs-status` div (today's Fix A) — it's at a fixed position in the DOM, not fixed in the viewport. After an inventory submit, it may be below the viewport.

**Why it matters:** This panel says "These observations have been saved. Agnes or Claire will review them..." — it's the primary reassurance that the work landed. If it's off-screen, the user has no confirmation at all.

**Proposal:** Auto-scroll the recent-submissions panel into view on first render after submit, OR anchor the panel to a fixed sidebar / footer on mobile. Also add a subtle "👁 View your recent submissions" link at the top of the form so it's accessible without scrolling.

---

## 7. Server-side hard-fail shape gate (Fix D — shipped today but expand post-v4)

**Shipping today:** Reject payloads that have neither `observations[]` nor `section_notes`.

**Post-v4 expansion:** Add telemetry — log malformed submissions (with redacted payload) so we can detect when a new UI surface drifts off the contract. Classic silent-drift prevention. Tie into ADR 0007 Fix 7 (observability for stale approvals) — both are "submissions that should have happened but didn't".

**Also:** Formalise the payload shape as a JSON Schema in the repo (`site/src/observation-payload.schema.json`), validated by both server-side Apps Script and a client-side pre-flight check in observe.js / inline form JS. Kills the class of drift where a new form emitter doesn't match the contract.

---

## 8. "Comment-only" submission mode on nursery view page

**Problem:** Nursery view page has no way to log a section-level comment (e.g. "Snails eating Jojoba leaves, need to check tomorrow"). Nursery observe page *does* offer a comment mode but it's unreachable (per #2).

**Interim:** Once #2 lands with a reachable nursery observe page, comment mode is free.

**Interim-interim:** Could add a compact "Add zone note" textarea + submit on the nursery view page, same shape as field section_notes. ~20 lines in `generate_nursery_pages.py`.

---

## 9. Audit — other forms on the site for the same payload-shape drift

**Problem:** Today we caught the nursery inline form drifting off the canonical payload shape. That was a silent-failure bug that lived for weeks. **Other forms on the site likely drift too.**

**Forms to audit:**
- `seedbank.js` — seed bank submissions
- `harvest.js` — harvest submissions
- Any form on `amenities.html` / `index.html` / any custom page
- Any Apps Script doPost that isn't Observations.gs

**Audit criteria for each:**
- Payload shape matches contract?
- submission_id generated?
- Success feedback visible after submit?
- Error feedback visible if network/server fails?
- Duplicate-submit protection (disable button / idempotency)?
- Confirmation that data landed in the sheet (not skeleton row)?

**Scope:** 2-3 hour review pass, probably discovers 2-4 more silent-failure paths. Single session after v4 cutover. Use `scripts/validate_observations.py` as the pattern — mechanical defect detection for forms.

---

## 10. Client-side contract pre-flight

**Proposal:** Before `fetch(OBSERVE_ENDPOINT, ...)`, validate the payload shape against a shared schema. Catches drift in dev before it ships. Shows user a loud error if the form is internally broken instead of silently-successful. Ties to #7 (shared JSON Schema).

---

## Prioritisation for first post-v4 UX session

| # | Item | Priority | Effort |
|---|------|----------|--------|
| 1 | Nursery "Add plant" design + interim stub | **P0** — blocks new nursery plantings | Design: 1 session. Interim stub: 1 hour. |
| 2 | Full nursery observe page parity | P1 — depends on #1 | 2-3 hours after #1 design |
| 3 | Nursery inline photo capture | P1 | 1 hour |
| 4 | Section-log cap + listing page | P1 | 1-2 hours |
| 5 | Identity confirmation | **P0** — attribution errors ongoing | 30 min (Y + Z) |
| 6 | Recent-submissions visibility | P2 | 30 min |
| 7 | Shape gate expansion + schema | P2 | 2 hours |
| 8 | Nursery comment mode | P2 — blocked by #2 or standalone | 30 min standalone |
| 9 | Other-forms audit | **P0** — unknown silent failures | 2-3 hours |
| 10 | Client-side pre-flight | P2 | 1 hour |

**First post-v4 UX session order:** #9 (audit — find what's broken before investing in features) → #1 + #5 (P0 fixes) → remainder.
