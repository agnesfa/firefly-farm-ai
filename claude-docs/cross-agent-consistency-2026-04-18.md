# Cross-Agent Consistency — Investigation & Semantic-Layer Gap Analysis

**Date:** 2026-04-18
**Authors:** Agnes (CTO), Claude (Agnes's session)
**Purpose:** Feed the governance + architecture review session with a factual
record of the cross-agent consistency failures uncovered on 2026-04-18, a
map of where the failures sit in the five semantic layers, and a concrete
proposal (FASF) for the shared skill framework that is currently missing.

---

## 1. Investigation trigger

During the 18 April session, Agnes flagged three discrepancies between what
she was seeing via her Claude and what James was reporting via his Claude:

1. **"17 pending logs" gap.** Agnes's Claude surfaced 17 pending farmOS logs.
   James's Claude was telling him there were none.
2. **Missing day-debrief persistence.** James told Agnes he has been doing
   day debriefs with his Claude, which was supposed to record activities in
   farmOS. But his winter green-manure planting (among other items) did not
   appear to be recorded.
3. **Missing knowledge base entry.** James told Agnes he had written a full
   chop-and-drop knowledge entry through his Claude. Agnes's Claude had no
   evidence of it.

The concern was not the specific items — it was the systemic trust erosion:
if two Claudes working the same farm, against the same MCP server, against
the same farmOS, surface fundamentally different realities, the agent layer
is unreliable.

---

## 2. Evidence gathered

### 2.1 The 17 pending logs are real

`query_logs(status="pending")` against the remote farmOS MCP server returns
17 logs split across two categories:

**9 activity logs** — all created by `Claude_user` (Agnes's session),
timestamped 2026-04-04 to 2026-04-05, all with notes beginning
`"JAMES — "`:

- 5 × "Review — P2R5.x" — Maverick transcript follow-ups asking James to
  verify counts
- 1 × "Review — P2R4.6-14" — flags a silent API failure from James's 24 Mar
  session #89 (Lavender + Geranium were never created in farmOS)
- 1 × "Review — P2R5.8-14" — gap section needing a full registration walk
- 1 × "Review — P2R5.22-29" — same, plus Sunflower and red-Okra questions
- 1 × "Observation — P2R5.29-38" — Okra count discrepancy

**8 transplanting logs** — all created 2026-03-17 by the nursery readiness
tracker, all named `"Transplant pending — <species> → <destination>"`:

Lemongrass × 11 → SPIRAL, Chilli (Devil's Brew) × 10 → P2R4, Calendula × 7
→ P2R4, Banagrass × 18 → P2R4, Avocado × 1 → P2R4, Avocado × 3 → P2R4,
Apple × 1 → P2R3, Achiote × 2 → P2R2 + P2R4.

### 2.2 James's session memory is rich — 21 summaries in 30 days

`read_team_activity(user="James", days=30)` returns 21 substantive session
summaries, covering winter prep across P2R5 (Mar 29 – Mar 31, sessions
95–98), full P2R3.50-62 work (Mar 21–22, sessions 82–86), P2R4.6-14
transplanting (Mar 25, session 89), KATO excavator fault (Apr 16, session
118), dam project status (Apr 6, sessions 107–108), mistletoe / willow work
(Mar 27, session 92), seed bank bug reports (Mar 22, session 85), and more.

Several sessions explicitly record farmOS writes via the `farmos_changes`
field (a JSON array). Spot-check of three of those writes:

- **Session 82/84** (Mar 21–22, P2R3.50-62): activity IDs `057a6f34`
  (Seeding winter garden mix), `14424ea1` (Chop-and-drop), `b7d281e6`
  (Mulching), `198198d5` (Transplanting) — **all present in farmOS, status
  `done`**. Confirmed by `query_logs(section_id="P2R3.50-62")`.
- **Session 89** (Mar 24, P2R4.6-14): claimed to have transplanted 5
  Lavender + 2 Geranium. Lavender asset **now exists**
  (`3117e706-7a11-4bc2-966f-947ee308ae8a`, count 5); the asset's notes
  read *"Originally missed from farmOS due to silent API failure detected
  by farm_context data integrity gate."* — so it was missed, then
  recovered by the integrity gate. Geranium: existing Oct 2025 asset had
  `+2 added` rather than a new asset created (same effect, different
  semantics).
- **Session 97/98** (Mar 31, P2R5.0-8 winter prep): described in detail
  but no matching farmOS activities found for *P2R5.0-8 winter prep* on
  Mar 31. Unverified — this is a candidate for a deeper audit.

**Duplicates exist.** Sessions 82 and 84 both recorded the same P2R3.50-62
chop-and-drop + seeding — and the farmOS state shows duplicate activities
(two "Chop and drop", two "Seeding") created one day apart but describing
the same field work. The duplicate was not detected.

### 2.3 James's chop-and-drop knowledge entry is not in the KB

`search_knowledge(query="chop and drop")` returns 27 entries matching, of
which:

- 1 is authored by `Claude (distilled from field practice Mar-Apr 2026)` —
  entry `be6d5ce9`, dated 2026-04-09. This is a Claude synthesis, not
  James's.
- 7 are authored by James himself: Eucalypt Coppicing, Sunn Hemp Seed
  Harvest, Seed Protein Biology, Hipcamp Guest Guide, Lavender Soil
  Preference, Seed Saving (Tomato), Passionfruit Transplanting.
- **None of James's authored entries is about chop-and-drop.**

The Claude-authored `be6d5ce9` entry was created the day Agnes asked
Claude to document chop-and-drop practices — it is not the one James
believed his Claude was writing. That entry does not exist in the KB.

---

## 3. Root-cause analysis

The three discrepancies have distinct but converging causes:

### 3.1 The 17 pending logs are invisible to James because ownership is unstructured

farmOS logs have `status: pending | done`, `type`, `timestamp`, notes, and
references to assets / locations. There is **no assignee field, no owner
field, no "for_user" field.** When Agnes's prior sessions created "JAMES —
review this" tasks, they encoded the assignment in the notes string as a
human-readable prefix. James's Claude has no mechanism to filter on this —
`query_logs` does not scan note text for owner prefixes.

Beyond the ontology gap, there is a **behavioural gap**: James's Claude
operates in *debrief mode* (write-oriented — the human describes what they
did, the Claude persists it). It does not run `query_logs(status="pending")`
at session start. Agnes's Claude operates in *review mode* (read-oriented —
query state, cross-reference, surface anomalies). Two different behavioural
postures, no shared protocol to reconcile them.

### 3.2 James's claimed activities sometimes silently fail

The 24 Mar Lavender + Geranium transplant was a silent API failure. The
session summary recorded the claim; the farmOS write never landed. The
`farm_context` integrity gate caught it, but only because Agnes's Claude
later ran that gate in another session.

There is no **post-write verification** in the write path itself. The
write tool returns success; the next session either catches the gap by
happenstance or misses it entirely.

Also: **duplicate writes are not detected.** Session 82 and 84 each recorded
the same chop-and-drop work, resulting in duplicate activities in farmOS.

### 3.3 James's chop-and-drop knowledge was never persisted as a KB entry

Two possibilities:

1. His Claude **never recognised** the shared knowledge as KB-worthy and
   only wrote a session summary. This is the hypothesis Agnes identified as
   the real gap: *"James assumes his Claude would know to create a KB and
   not just a team memory — that part is assumed as it should be. Any
   valuable knowledge input should persist as a KB or enhance an existing
   one, and write a team memory that explicitly quotes the KB. If not, why
   it did not make it to the KB — potentially highlighting an issue."*

2. His Claude attempted to write the KB entry and the call **silently
   failed** (same pattern as the Lavender/Geranium write).

Either way, the correct agent behaviour is not being enforced anywhere.

---

## 4. Semantic-layer gap map

Applying the five-layer farm_context lens:

### Layer 1 — Ontology (what exists)

**Gaps:**
- No `Task` / `Assignment` / `Request` entity type. Inter-agent tasks are
  encoded as prefix strings in log notes (`"JAMES — …"`), not structured.
- No `owner` / `assignee` field on logs — ownership is unqueryable.
- No explicit relation between a session summary's `farmos_changes` array
  and the actual farmOS logs those changes produced. The array is
  free-text descriptive, not a pointer list.
- No `AgentSkill` entity — no concept of a named, versioned, reusable
  behaviour pattern that every agent should follow.

### Layer 2 — Facts (what's true)

**Gaps:**
- No post-write verification. `create_plant` / `create_observation` /
  `add_knowledge` can silently fail at the HTTP layer and the agent won't
  notice until a later audit.
- No duplicate detection. Same chop-and-drop activity logged twice in two
  sessions produces two identical farmOS records.
- `farmos_changes` in a session summary is a claim, not a verified fact.
  No cross-check exists at write time.

### Layer 3 — Interpretation (what it means)

**Gaps:**
- `"JAMES — "` prefix carries meaning to humans but not to agents.
- "Pending" in farmOS log status conflates multiple meanings: "task
  waiting to be executed", "observation awaiting verification", "review
  task assigned to a human", "nursery signal that is ready but not yet
  consumed". Agents cannot distinguish these without reading each note.
- Session summaries do not link to the KB entries they claim to have
  created, so no way to verify "did this knowledge actually land?".

### Layer 4 — Context (what we did about it + integrity checks)

**Present:**
- `farm_context` does run an integrity gate that cross-references session
  `farmos_changes` against actual farmOS logs (caught the Lavender /
  Geranium failure).

**Gaps:**
- The integrity gate only runs when an agent calls `farm_context` for a
  section. It does not run proactively at session start. Failures
  discovered long after the fact.
- No integrity gate for KB writes (would have caught James's missing
  chop-and-drop entry).
- No integrity gate for duplicate farmOS writes (would have caught the
  duplicate chop-and-drop activities).

### Layer 5 — Gaps (what's missing)

**Gaps about gaps:**
- No gap-surfacing at session start. The "JAMES — review" tasks from 2
  weeks ago sit invisibly in farmOS because nothing pulls them into James's
  Claude's context window.
- No gap-surfacing across stores. Session memory says "created KB entry"
  but KB does not contain one. No automated cross-store reconciliation
  report.

---

## 5. The shared-skill problem

The only layers **currently shared** across Agnes's Claude, James's Claude,
and any future Claude working the farm are:

1. **Team memory** (the Google Sheet of session summaries)
2. **MCP tools** (the `mcp__farmos__fc__*` suite on Railway + STDIO
   fallback)
3. **Knowledge base content** (farm knowledge, not agent behaviour)

There is **no shared layer for how to behave**. Each Claude instance
invents its own session protocol, its own review cadence, its own write
discipline. The discrepancies above are predictable consequences.

This is the layer FASF (Firefly Agent Skill Framework) is proposed to
fill.

---

## 6. FASF — Firefly Agent Skill Framework (proposal)

### 6.1 What is a skill

A **skill** is a named, versioned, declarative pattern of agent behaviour
that any Claude can load and execute consistently. Each skill is a
structured KB entry with:

- **Trigger** — when does this skill apply? (`session_open`,
  `user_shares_knowledge`, `review_requested`, `before_write`, …)
- **Preconditions** — what must be true before the skill runs?
- **Procedure** — ordered, concrete steps. Each step is a tool call or a
  decision rule.
- **Postconditions** — what must be true after the skill runs, asserted
  explicitly.
- **Failure mode** — for every step that can fail, what does the agent
  do? (Default: record the failure in team memory as an explicit flag;
  never silently drop.)
- **Version + author + last_reviewed** — lifecycle metadata.

### 6.2 Where skills live

As KB entries with `category = "agent_skill"`. This uses the infrastructure
that every Claude already has, introduces no new storage, and is
version-controllable via the `update_knowledge` tool.

### 6.3 How skills are loaded

**Phase 1 (pull):** CLAUDE.md mandates that every session begins by
calling `list_knowledge(category="agent_skill")` and selecting skills
whose trigger matches the current situation. No new tooling required.

**Phase 2 (push):** New MCP tool `list_active_skills(context)` that
returns the skills relevant to the current request. Reduces token cost on
every session. Introduced when the pull pattern proves stable.

### 6.4 Day-one skill set

1. **`session_open`** — every session, regardless of user:
   - `list_knowledge(category="agent_skill")` — load active skills
   - `query_logs(status="pending")` — scan notes for `"<USER> —"` prefix
     and surface the user's pending work
   - `read_team_activity(days=7, only_fresh_for=<user>)` — recent team work
   - `farm_context` integrity gate — cross-ref recent `farmos_changes`
     against actual farmOS writes; surface any misses
   - **Postcondition:** the agent has a summary of pending, recent, and
     known-divergent state before the user's first request is processed.

2. **`ingest_knowledge`** — trigger: user shares durable knowledge:
   - Detect knowledge value (heuristic: is this a durable technique,
     principle, or observation that another human / agent should find
     later?)
   - Search KB for existing entry on the topic
   - If exists → enhance via `update_knowledge`. Record the entry_id and
     the diff.
   - If not → create via `add_knowledge`. Record the returned entry_id.
   - Write team memory that **explicitly cites the KB entry_id and title**.
   - **Failure mode:** if the KB write fails at any step, the session
     summary must contain an explicit `KB_WRITE_FAILED` flag with the
     error. Never silently.

3. **`review_assignment`** — trigger: session_open, detect current user's
   assigned work:
   - Scan pending log notes for `"<USER> —"` prefix
   - Scan team memory questions field for unresolved `"<USER> — "` items
   - Surface both as the user's queue, grouped by age
   - **Postcondition:** the user sees every assigned item or an explicit
     "nothing assigned to you" statement.

4. **`record_fieldwork`** — trigger: user describes completed field work:
   - Create the farmOS activity / log / plant asset
   - **Post-write verify:** immediately re-read the created entity via
     `query_logs` or `query_plants` and confirm it exists with the
     expected fields. Do not rely on the write tool's "success" return
     alone.
   - If verify fails, retry once, then flag explicitly in session memory.
   - Write session summary with the verified IDs.

5. **`per_row_review`** — trigger: user requests disciplined row review:
   - For each section in the row:
     - List active plants (species, count, last observation date)
     - List pending logs attached to the section
     - List integrity flags from the audit KB entries
     - Present agent's best judgement per asset: "keep as-is" / "update
       count" / "archive as ghost" / "field-verify"
   - Execute user decisions as a batch.

### 6.5 Enforcement

CLAUDE.md is the binding contract. Two tiers:

- **Repo CLAUDE.md** (Agnes on Claude Code): already exists. Add a
  section that mandates session_open + ingest_knowledge + record_fieldwork
  skills be applied.
- **Claude Desktop users** (James, Claire): no repo, no CLAUDE.md.
  Instead: a short, pinned "session protocol" instruction in their Claude
  config that tells their Claude to call `list_knowledge(category="agent_skill",
  topics="session_protocol")` at the start of every session and follow the
  result. The actual protocol lives in the KB, so it's updateable centrally
  without touching each user's config.

### 6.6 Lifecycle

Skills are governed by the same ADR process as other architectural decisions
for substantive changes. Minor updates land via `update_knowledge` inline.
Every skill carries a `last_reviewed` date and surfaces in a "skills needing
refresh" query after 90 days of staleness.

---

## 7. Immediate mitigations (pre-governance)

These can be applied now, before the governance session formally ratifies
FASF, to reduce bleed:

1. **James's Claude protocol** — `claude-docs/james-claude-session-protocol.md`
   drafted alongside this analysis. A short instruction James can paste into
   his Claude Desktop config to enforce session_open + ingest_knowledge
   manually until FASF is live.

2. **Close the 17 pending logs** — the 9 Review logs are stale task notes;
   most are addressable with batch mark-done + resolution summary. The 8
   Transplant pendings need triage against current nursery state (some have
   been executed in the field since March).

3. **Re-run farm_context integrity gate across all recent sessions** — catch
   silent-failure residue before the next WWOOFer cohort starts.

4. **Seed the agent_skill category in the KB** — draft entries for
   `session_open` and `ingest_knowledge` as KB entries now, so they are
   discoverable to any Claude that runs `list_knowledge(category="agent_skill")`,
   even before FASF is formally ratified.

---

## 8. For the governance session

**Decisions needed:**
- Ratify FASF as the shared-skill layer (or alternative).
- Approve the day-one skill set (5 skills above) or revise.
- Approve the enforcement model (CLAUDE.md + pinned Claude Desktop
  instruction + KB-as-source-of-truth).
- Decide whether to add a `Task` entity to the ontology, or keep assignment
  in note prefixes (with `review_assignment` skill to make it queryable).
- Decide whether `farm_context` integrity gate should run at session_open
  automatically or on demand.
- Set cadence for skill review (proposed: 90 days).

**Architectural reviews to trigger:**
- Ontology review: `knowledge/farm_ontology.yaml` — does it need a Task /
  Assignment / AgentSkill entity?
- Write-path review: post-write verification pattern across all write
  tools (`create_plant`, `create_observation`, `add_knowledge`, etc.).
- Duplicate-detection review: where in the write path do we check for
  "this exact activity already logged today"?

---

*Companion documents:*
- `claude-docs/adr/0006-agent-skill-framework.md` — ADR draft for ratification
- `claude-docs/james-claude-session-protocol.md` — short-term protocol for
  James's Claude Desktop pending FASF rollout
