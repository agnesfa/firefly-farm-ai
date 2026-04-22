# SDLC with AI — design thinking seed

**Date:** 2026-04-22 (surfaced mid-session by Agnes after the 4th bug-class escape in one evening)
**Author:** Agnes (observation), Claude (transcription)
**Status:** Design-thinking seed, not a proposal. Needs a proper pass post-v4.

## The observation

We have a decent test suite — **319 Python + 268 TS = 587 tests, all green, across three test layers** (pure helpers, HTTP-mocked clients, tool-orchestration). Yet in a single evening on 2026-04-21/22 we bumped into **four distinct bug classes** that reached live data before being caught, each of which silently corrupted or dropped WWOOFer field observations:

1. **Gate-on-flag** — import silently gated photo fetch on the sheet `media_files` column being populated, dropping ~13 photo attachments when the column regressed.
2. **Contract drift** — farmOS file upload returns `{data: [{...}]}` on some paths and `{data: {...}}` on others; the TS client only handled the dict form and returned `null` for every list-form response, producing zero photo uploads.
3. **Name-collision silent drop** — `logExists(name)` dedup short-circuited when a log with the same name already existed, even when the existing log was a different submission; `2334a179` Okra 13→15 was silently dropped because `23603752` inventory already had a log with the same name at count 13.
4. **Duplicate concatenation** — inventory-mode expansion writes the same `section_notes` on every species row; the importer concatenated all rows without dedup, producing 4× duplicate Cuban Jute text on a 4-species section log.

None of these were caught by the existing tests. All reached live data. Agnes had to spot them in production.

## What the current tests actually measure

Audit of the 587 passing tests against the four bug classes above:

| Bug class | Would existing tests have caught it? | Why not |
|---|---|---|
| Gate-on-flag | ❌ | Happy-path mocks always populate `media_files` ≥1 char. No test with empty column + Drive files present. |
| Contract drift | ❌ | All upload mocks return dict form. No test fuzzes the response shape or mirrors real farmOS behaviour. |
| Name-collision silent drop | ❌ | `logExists` always mocked to `null` (no collision) or handled per-test explicitly. No test simulates two distinct submissions for the same plant on the same day. |
| Duplicate concatenation | ❌ | No test exercises inventory mode with non-empty `section_notes`. Single-species tests don't expose the expansion-induced duplication. |

**The pattern:** our tests verify that the code we wrote does the thing we wrote it to do (tautology). They do not verify that the code handles the states the real world will produce, nor that downstream invariants hold after multi-step sequences.

## Classes of tests we're under-indexed on

1. **Contract tests against real response shapes.** farmOS returns what it returns; our mocks shouldn't be narrower than the API. Suggestion: capture real responses (dry-run against staging or anonymised samples) and drive mocks from recorded fixtures. Test both `{data: {}}` and `{data: []}` forms explicitly on every write path.

2. **Temporal / collision / multi-submission scenarios.** Real workflows produce sequences: morning inventory → afternoon recount; observer A → observer B on the same plant same day; retry after partial failure. Our tests run one submission at a time with clean state. Suggestion: a scenario layer that threads N submissions through the full pipeline and asserts the *final* farmOS state, not the individual return values.

3. **Adversarial / negative-space tests.** "What if the upstream system regresses?" is the bug class we keep hitting. Suggestion: for every upstream dependency (sheet column, Drive folder, Apps Script endpoint, farmOS response shape), write a test that assumes the dependency has silently broken and asserts either a loud failure or a graceful degradation with operator-visible warning — never silent data loss.

4. **Post-condition verification.** A test that asserts `total_actions: 1` is a tautology — it asserts the code returns what the code computed. The useful assertion is: after the tool call, the farmOS log exists with the expected count AND carries the expected `submission=<id>` marker AND has the expected media attached. Suggestion: extend the tool mocks to maintain a small in-memory farmOS state, so tests can assert on the state the tool left behind, not just the return value.

5. **Invariant tests.** ADR 0008 defines I1–I12. Each invariant should have a set of tests that assert "running the pipeline end-to-end never produces data that violates invariant X". These are scenario tests from (2) with invariant assertions layered on top.

## On tests that just mirror implementation

A recurring failure mode in AI-assisted code generation: the assistant writes the implementation, then writes tests by inverting the implementation. The tests are green because they encode the same assumptions as the implementation. They protect against refactoring regressions but not against the assumptions being wrong in the first place.

The cure isn't more tests; it's **tests written against the contract/invariant, not the implementation**. If the contract says "photos attach when they exist in Drive", the test should assert that property for *every path that might encounter photos*, including the ones we didn't think about. A fuzz-or-scenario generator over possible upstream states is strictly better than hand-authored happy-path fixtures per path.

## Proposed SDLC lifecycle (seed — needs refinement)

Today's cycle:
```
Design (ADR) → Build (AI code + happy-path tests) → Deploy → Feedback (Agnes spots bug in prod) → Correct → evolve back to Design
```

The weak link is: Feedback happens **in production, on Agnes's time**. Tokens/time are expensive. Each escape costs a session-debug cycle plus loss of trust.

Target cycle:
```
Design (ADR + invariants) →
  Build (AI code + invariant-driven tests + scenario tests + post-condition assertions) →
    Local Verify (full scenario suite, not just unit-green) →
      Deploy (with telemetry on the *behaviours* that could regress) →
        Feedback (automated regression + invariant scans + operator escalations only for novel classes) →
          Correct (update ADR + tests + code atomically; new bug class always produces a scenario test) →
            Evolve (ADR amendment)
```

Key shifts:
- **Invariants before implementation.** Each ADR produces a testable invariant set. Tests are written against invariants first, then implementation.
- **Scenario suites, not just unit suites.** A scenario is a sequence: `submission_A → submission_B → retry A`. The scenario asserts on the *final* state against invariants. Unit tests remain for specific helpers.
- **Post-incident contract.** Every bug found in prod MUST produce a scenario test that reproduces it; the bug isn't fixed until the test exists and fails against the old code. (Tonight's 4 bugs should have produced 4 scenario tests; we shipped 3.)
- **Test usefulness metric.** Not "coverage %" but "bug classes caught in test / bug classes found in prod". If the ratio is < 1, tests are ornamental.
- **AI-aware**: the AI assistant should be aware of this lifecycle. Memory now has `feedback_check_adrs_before_fixing.md` — this document should have a companion memory that applies the same rule to test writing: "before writing any test, check ADR for the invariant it's meant to enforce; if no ADR invariant, write the invariant first."

## Practical next step (post-v4)

- One working session to draft the **invariant-scenario test framework** on top of the existing 3-layer harness. Start with ADR 0008 invariants I1–I12, one scenario per invariant.
- Retrofit: run the scenario suite against tonight's 4 bug classes. Confirm all 4 would have been caught.
- Write a one-pager on what a "useful test" looks like in this codebase, bind it to the skill library so every agent-produced test meets the bar.
- Revisit the deploy feedback loop: Railway auto-deploy + Apps Script redeploy + test-in-prod is fragile. Staging envs aren't cheap but if we reach 50+ WWOOFer observations/week they will pay for themselves.

## Meta-observation

The repeated pattern tonight — photo pipeline fixes, name-collision fix, even the initial status+review triage — I was proposing fixes **before checking prior ADR/session context**. That's a failure mode orthogonal to the test coverage issue: *context discovery before design*. See also `feedback_check_adrs_before_fixing.md` in memory, saved this same session after Agnes's second correction.

The combined failure mode: AI + shallow tests + incomplete context discovery = fragility compounds with every fix. Each "fix" risks a new bug class because the landscape being fixed wasn't fully mapped.

The remedy, ultimately, is cultural-within-the-AI — a discipline of "check invariants before code, scenarios before units, prior art before proposals". That discipline needs to be durable; memory entries are a first-order tool but the framework (scenario tests + ADR-driven design + memory-anchored context) is what actually makes it stick.
