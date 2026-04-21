---
title: Firefly Corner — Skill Library
description: Index and governance doc for all agent skills in the Firefly Corner system.
last_reviewed: 2026-04-21
---

# Skill Library

All skills used by Claude agents at Firefly Corner live here. This folder is the **source of truth** — deployment targets (Claude Code `.claude/skills/`, Claude Desktop account uploads, farmOS KB entries with `category=agent_skill`) are synchronised from these files. Edit here, commit, then sync.

See [ADR 0006](../adr/0006-agent-skill-framework.md) for governance and rationale.

## Two systems, one source

| System | Where installed | Who reads | Storage shape |
|---|---|---|---|
| **A — Client-side tactical** | `.claude/skills/NAME/SKILL.md` (CC) OR account attachment (Desktop) | Only the client that has it installed | Per-user install, may bundle scripts + templates |
| **B — Shared behavioural (FASF)** | KB entry with `category=agent_skill` | Every Claude with MCP access (CC + Desktop + future clients) | Single entry per skill, cross-client |

Both systems have their source `.md` file here. Deployment adapters push to the right target.

**When to use which:**
- **System B** for *protocols the agent always follows* — write-path postconditions, session open/close discipline, KB ingestion rules, classification logic. These are contracts.
- **System A** for *workflows the user triggers* — process a transcript, generate a row inventory, bulk-import photos. These are tools that can bundle scripts the MCP layer can't run.
- A System A skill that creates farmOS records invokes a System B contract. They compose.

## Naming convention

- **System B (shared behavioural):** verb-first snake_case. `open_session`, `record_fieldwork`, `ingest_knowledge`, `classify_observation`, `archive_ghost_plant`, `review_observations`. Verbs align with [knowledge/farm_ontology.yaml](../../knowledge/farm_ontology.yaml) verb mappings.
- **System A (tactical):** kebab-case. `process-transcript`, `row-inventory`, `seed-bank-withdrawal`.
- The style split is a visual cue for which system the skill belongs to — you can tell at a glance.

## Folder layout

```
claude-docs/skills/
├── README.md                      ← this file
├── _template.md                   ← spec template for new skills
├── shared_behavioural/            ← System B — FASF, seeded to KB
├── shared_tactical/               ← System A — sources for skills installed on multiple clients
└── _agnes_only/                   ← CC-only, Agnes's workflow, not shared
```

## Current catalogue

### `shared_behavioural/` — System B (FASF)

| Skill | Status | Notes |
|---|---|---|
| [open_session](shared_behavioural/open_session.md) | drafted | Every session, regardless of user — load skills, scan pending work, integrity gate |
| [record_fieldwork](shared_behavioural/record_fieldwork.md) | drafted | Post-write verify contract — catches silent write failures (ADR 0007 Fix 4) |
| [close_session](shared_behavioural/close_session.md) | drafted | Session summary discipline — cite KB entry_ids, flag failures explicitly |
| [review_observations](shared_behavioural/review_observations.md) | drafted | Consolidated from earlier 0.1-draft (formerly `review_observations.md` in this folder) |
| `ingest_knowledge` | stub | User shares durable knowledge → KB search → enhance or create → record entry_id in session memory |
| `review_assignment` | stub | Detect assigned work for current user (pending logs + team memory questions) |
| `per_row_review` | stub | Walk row section-by-section with strata + pending + integrity presented per section |
| `classify_observation` | stub | I11 classifier (deterministic today; skill upgrade post-ratification — ADR 0008 amendment Step 9) |

### `shared_tactical/` — System A

| Skill | Status | Install targets |
|---|---|---|
| `process-transcript` | stub — live in `.claude/skills/process-transcript/SKILL.md` | Agnes CC (installed). To migrate for Claire: promote executable parts to MCP tools. |
| `review-observations` | stub — live in `.claude/skills/review-observations/SKILL.md` | Agnes CC (installed). Behavioural counterpart is `shared_behavioural/review_observations.md`. |
| `row-inventory` | stub — originally installed on Claire's CC (Mar 15, pre-departure) | Claire frozen at pre-Mar-22 version. Candidate for System B migration + MCP tool for xlsx generation. |
| `plant-taxonomy-manager` | stub — originally installed on Claire's CC (Mar 17, pre-departure) | Same situation as row-inventory. |

### `_agnes_only/` — not shared

| Skill | Status | Notes |
|---|---|---|
| `governance_session` | stub | Walkthrough → review → edit ADRs → flip status. Ritual used for ADR 0006/0007/0008 ratification. |
| `pre_governance_review` | stub | Review live data for real issues before ratifying rules — flush out gaps the ADR misses. |
| `deploy_coordination` | stub | Hold push on CI/CD changes — matches [feedback_deploy_coordination](../../~/.claude/projects/-Users-agnes-Repos-FireflyCorner/memory/feedback_deploy_coordination.md). |

## Contribution and lifecycle

**The repo is source of truth, but the repo is not the contribution interface.** Nobody using the farm system except Agnes understands SDLC, commits, or PRs — and they shouldn't need to. Contribution happens through the same path users already use for everything else: talk to your Claude, Claude writes it to team memory, Agnes promotes to source.

### How users contribute (no git knowledge required)

```
User (any)                      Their Claude                     Agnes's Claude              Source
───────────                     ─────────────                    ───────────────             ──────
"the review skill                → records in team memory        → open_session surfaces     → Agnes edits
 missed X — should                 with topics including           the skill_feedback          .md, commits,
 also check Y"                     skill_feedback:review_          signal next session         runs sync
                                   observations                  → Agnes discusses with
                                                                   her Claude, decides
                                                                   to edit or decline
                                                                 → commits change
                                                                 → runs sync_agent_skills
                                                                                           → KB + clients
                                                                                             pick up the
                                                                                             new version
                                                                                             on next session
```

**What the user sees:** the system gets smarter over time; their Claude picks up new protocol on each session; feedback they gave at breakfast is reflected by dinner. No repository, no commit, no PR, no `.md` file.

**What Agnes sees:** a queue of skill-improvement signals surfaced at session open. Fast edit loop — open the `.md`, edit, commit, sync in one session. The commit discipline stays with her; the feedback flow stays open to everyone.

### Lifecycle

- **Edits** land as git commits on the source `.md` file — Agnes only. Never edit the KB entry directly via `update_knowledge`; the reconcile tool will flag it and force a decision.
- **Sync** via `scripts/sync_agent_skills.py` (to be built) — reads `shared_behavioural/*.md`, writes KB entries with `category=agent_skill`. Must be lightweight: runnable in-session by Claude, single command, no pipeline. Three keystrokes total.
- **Reconcile** detects drift between repo and KB. Drift means someone edited KB directly — Agnes decides to push (overwrite with repo) or pull (backport to repo).
- **Review cadence** is 30 days. `open_session` surfaces skills with `last_reviewed` older than 30 days from today.
- **Versioning** via semver in frontmatter + git history. Bump `version:` on behaviour change; update `last_reviewed:` on review pass (even with no edit).

### What Agnes must commit to

For this contribution model to feel participative rather than gatekept, Agnes's promotion loop has to be *fast* — skill-feedback signals that sit in the backlog for weeks erode trust that feedback gets heard. Target: any non-trivial skill-feedback signal is either acted on or responded to within one session cycle. If Agnes is the bottleneck, the sync tool + in-session edit flow has to be cheap enough that this isn't painful.

## Open work

- [ ] Build `scripts/sync_agent_skills.py` + TS mirror
- [ ] Build reconcile tool + wire into `system_health()`
- [ ] Promote any tactical skill with remote users (today: Claire's `row-inventory`, `plant-taxonomy-manager`) — executable parts → MCP tools, behavioural wrappers → System B specs
- [ ] Resolve the `review_observations` / `review-observations` naming collision (one file per system, both reference each other)
- [ ] Flesh out stubs into full specs
