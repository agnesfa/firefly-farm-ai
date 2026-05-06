# Seed Bank end-to-end process review — pending

**Status:** Parked 2026-05-04 by Agnes pending holistic review.
**Don't run `sync_seed_transactions` and don't correct the sheet baseline until this review is complete.**

## What the 2026-05-04 session discovered

### Sheet ↔ farmOS drift (90 days, 10 transactions)

The `sync_seed_transactions` MCP tool exists and is functional + idempotent, but **has never been run**. Ten transactions submitted via the seed bank QR form between 2026-03-21 and 2026-05-04 (1,700g of Winter Market Garden Mix + 200g Bunnya Pine + 100g Tomato add) landed in the sheet's Transactions tab but never reached farmOS.

farmOS state at 2026-05-04: Winter Market Garden Mix 19,300g, Bunnya Pine 500g, Tomato 0.5g — i.e. unchanged since whoever first entered them.

### Sheet's `quantity_grams` baseline broken for Winter Market Garden Mix

`SeedBank.gs:301`:
```js
newGrams = Math.max(0, currentGrams - Math.abs(grams));
```
combined with `currentGrams = parseFloat(row[INV.QTY_GRAMS]) || 0` (line 296). When the inventory column is empty for a seed, every take silently caps at zero. The form has shown observers `previous_value: "0g"` for Winter Market Garden Mix for 90+ days while they were taking real bulk seed.

Bunnya Pine (initialised 500g) and Tomato (initialised 0g, only had +100 add) chained correctly. The bug only bites uninitialised cells.

Cause confirmed by Agnes: "very likely James or Claire did the first entry directly with his Claude instead of using the Seed bank QR page." The sheet baseline was never seeded.

### End-to-end correlation, 90-day window

(See `scripts/_seedbank_e2e_correlation.py` — uncommitted throwaway diagnostic.)

| Direction 1 — txn → matching seeding log within ±3d | Count |
|---|---|
| Clean (proper farmOS `Seeding —` log matches txn) | 3 |
| Hard leak (no farmOS evidence at all) | 2 — leah Apr 10, Apr 12 (400g WMG total) |
| Partial gap (section activity exists but no formal seeding log) | 3 — Bunnya Pine Mar 22, James Apr 20 P1R5, James Apr 30 P1R3 |
| N/A (incoming stock, not a sowing) | 1 — Tomato Mar 21 |
| Pending — late record by Agnes | 1 — May 4 18:44 (for Sat May 2 P1R5.0-10) |

| Direction 2 — seeding-like farmOS logs WITHOUT a matching txn | Count |
|---|---|
| Confirmed sowing events with no seed bank entry | ~5 (see below) |
| Maverick transcript inventory observations of self-seeded plants (noise) | many |
| Kacper inventory section comments mentioning "mulching" (noise) | many |

Confirmed sowings without seed bank txns:
- 2026-03-18 Claire seeded White Borage at P2R3.15-21 (sachet quantity, Greenpatch)
- 2026-03-21 P2R3.50-62 "Scattered 200g winter garden mix" + "Sowed winter garden mix across the 10m section" — *two* seeding logs that day; James's same-day txn was 150g for "10m stretch" of P2R3 (numbers don't match, possibly two distinct events)
- 2026-03-24 NURS.FRDG `Seed withdrawal` log: "150g winter garden mix withdrawn from fridge by James. **James logged this via iPhone**" — direct API workaround, never landed in sheet
- 2026-03-25 P1R1 "WWOOFers Sarah and Kacper completed chop and drop, sowed winter garden mix, and mulched the last 30m of P1R1" — real sowing, no txn
- 2026-05-01 Agnes P1R5.0-10 "150g Winter mix seeded plus mulched" (pending observation `5d29309b`) — Saturday seed bank attempt failed silently, only the section comment landed

### Form failure mode (one-off, not reproducible)

Agnes reported on 2026-05-04 that her seed bank submit on Saturday 2026-05-02 "did nothing." Same-session 2026-05-04 18:44 retry landed cleanly. Possible causes (not narrowed): network blip, stale browser tab, missing required field, transient Apps Script error. **Form is reliable when it works**, but no observability — when it fails, neither the user nor the sheet records the attempt.

## Why the holistic review is the right next step

Three patterns reinforce each other:

1. **The form captures less than half the actual seeding activity.** 5 confirmed sowings have no txn; only 3 of 9 (now 10) txns have proper end-to-end matches.
2. **People work around the form because it's broken.** James's iPhone-logged direct activity log on 2026-03-24 is symptomatic — the workaround creates more workarounds.
3. **Sheet-side baseline silently drifts to zero.** The form actively misleads observers (previous_value: "0g" while they take real seed).

Patching any one of these in isolation just shifts the problem. The seed bank only makes sense in relation to nursery propagation, direct paddock sowing, transplanting, and harvest→seed-save — and those processes themselves have data-model gaps (no plant asset for Winter Mix, no individually tracked green manure, etc.).

## Review scope

1. **Scenario inventory** — enumerate every legitimate use of the seed bank end-to-end. Provisional list (Agnes/James/Claire to validate + extend):
   - Bulk withdraw → direct paddock sowing
   - Bulk withdraw → nursery seed-starting
   - Sachet withdraw → nursery seed-starting (small variety packs)
   - Bulk add from on-farm harvest (sun hemp, pigeon pea, cowpea returned to fridge)
   - Bulk add from purchase (Greenpatch / Daleys / Eden Seeds delivery)
   - Sachet add from purchase
   - Status change (sachet full / half / empty)
   - Replenishment flag (no inventory change, just "needs reorder")
   - Loss / spoilage write-off (Claire's mouldy maize)
   - ?? more

2. **Per scenario** — capture: trigger event, actor(s), what should land where (sheet, farmOS, both, neither), tools today, where the chain breaks.

3. **Adjacent process coherence** —
   - Nursery propagation: seed → seedling → plant asset → transplant. Today: ad-hoc, partly via QR observe pages, partly via direct Claude logs.
   - Direct paddock sowing: seed → seeded section. Today: no plant asset representation. Same data-model gap as `project_invasive_species_handling` and `project_green_manure_categorisation` (pending).
   - Harvest → seed-save cycle: links to I13 work in MEMORY.md (cowpea harvest workflow).

4. **Conceptual gaps** —
   - Withdrawal vs sowing event are independent records. Should withdrawal carry `target_section`? Should sowing back-reference the withdrawal log?
   - Where does "seeded section" live in the data model when there's no individually tracked plant asset (e.g. winter mix sown as a polyculture)?
   - How does sachet/bulk distinction affect the form's interactions and the audit trail?

5. **Phased fix plan** — out of scope until 1–4 are settled.

## Action items in the meantime

- **Don't run sync or fix the sheet baseline.**
- Throwaway diagnostic `scripts/_seedbank_e2e_correlation.py` stays uncommitted on disk; useful when the review picks up.
- Memory pointer: `project_seedbank_holistic_review_needed.md` (indexed in `MEMORY.md`).
- Operational follow-up (separate from the review):
  - Verify with leah what happened to her Apr 10 + Apr 12 takes (400g WMG; no farmOS evidence)
  - Verify with James whether his Apr 20 P1R5 + Apr 30 P1R3 takes were sown as recorded
  - Ask James whether the Mar 22 Bunnya Pine 200g take was actually sown, and where (no farmOS Bunnya Pine seeding log exists)

## Connection to the broader pipeline-reliability theme

This is the same silent-failure family as the section-observe form bug fixed earlier today (commits `63a16da`, `f712f92`, `0f49f26` — held, not pushed). Forms succeed visually, data lands in unexpected places. Adds to the post-v4 architecture revision pile alongside `claude-docs/observation-pipeline-issues-2026-04-29.md`.
