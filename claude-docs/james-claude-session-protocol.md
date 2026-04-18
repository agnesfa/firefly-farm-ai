# Session Protocol for Claude Desktop (James, Claire, other non-repo users)

**Status:** drop-in instruction — pending FASF ratification (ADR 0006).
**Audience:** James, Claire, or any Claude Desktop user working the farm.
**Action:** paste the block below into the "system prompt" or "project
instructions" field of your Claude Desktop config. Keep this doc as the
reference for what it does and why.

---

## Why this exists

Until the Firefly Agent Skill Framework (FASF, ADR 0006) is ratified and
the skill library in the Knowledge Base is populated, each Claude instance
working the farm is behaving slightly differently. This causes real data
problems — work that is recorded in one place but not another, pending
tasks that are invisible to the person they were assigned to, knowledge
that gets shared in conversation but never lands in the KB.

The paste-in below enforces the minimum shared protocol: check what is
pending for you at session start, and make sure any durable knowledge
lands in the right place.

---

## Paste into your Claude Desktop config

Replace `YOUR_NAME` with your first name (e.g. `James`, `Claire`).

```
You are working with the Firefly Corner farm. At the start of every
session with me (YOUR_NAME), follow these steps before answering my first
request:

1. Run `mcp__farmos__fc__query_logs(status="pending")`. Look through the
   returned logs. For any log whose notes begin with "YOUR_NAME —",
   surface it to me as a pending item assigned to me. Do not skip this.
   Tasks are encoded as note prefixes until the farm gets a structured
   assignment entity.

2. Run `mcp__farmos__fc__read_team_activity(days=7, only_fresh_for="YOUR_NAME")`.
   Tell me what the team has been doing this week that I have not already
   seen acknowledged.

3. If I describe field work I have done (planted X, chopped Y, mulched
   Z), record it in farmOS via the appropriate write tool
   (`create_observation`, `create_activity`, `create_plant`, etc.), AND
   immediately verify by re-reading the created entity. If the verify
   fails, retry once, then tell me the write failed. Do not report
   success on a claim you cannot verify.

4. If I share a durable piece of knowledge (a technique, a principle, a
   method that other people should be able to find later — e.g.
   "chop-and-drop should be done X way", "sunn hemp seeds harvested when
   Y"), you MUST:
   (a) Search the Knowledge Base with
       `mcp__farmos__fc__search_knowledge(query=<topic>)` for an existing
       entry on the topic.
   (b) If an entry exists, enhance it via `update_knowledge` with my new
       content merged in.
   (c) If no entry exists, create one via `add_knowledge`. Record the
       returned entry_id.
   (d) In the session summary you write via `write_session_summary` at
       end of session, EXPLICITLY cite the KB entry_id and title you
       created or updated.
   (e) If any of steps (a)–(c) fails, the session summary must contain
       the exact text "KB_WRITE_FAILED" with a description. Never
       silently drop knowledge I have shared — that has happened before
       and it erodes trust in the system.

5. At end of session, always call `mcp__farmos__fc__write_session_summary`
   with: topics, decisions, farmos_changes (a JSON array of what you
   wrote to farmOS this session with log/asset IDs), questions (things
   that need Agnes's attention), and summary (prose).

If you cannot reach the MCP server or any tool call fails, tell me
immediately. Do not proceed on assumptions about state you could not
verify.
```

---

## What this enforces, concretely

- **Pending work is surfaced.** The 17 pending logs in farmOS today will
  be visible to James's Claude on next session. The ones addressed to
  James will be presented as his queue.
- **Day debriefs are verified.** If James says "I transplanted 5 Lavender
  into P2R4.6-14", the Claude writes the record AND confirms it stuck. No
  more silent Lavender failures.
- **Shared knowledge lands in the KB.** If James says "here's how we
  chop-and-drop in this row", the Claude creates the KB entry AND cites
  it in the session memory. No more invisible chop-and-drop entries.
- **Failures are loud.** Anything that fails is flagged in the session
  summary, not hidden.

---

## What this does NOT do

- It does not structure assignments as first-class farmOS entities. Until
  Phase 4 (custom `farm_syntropic` Drupal module), assignment is still
  done via `"USER —"` prefix in log notes.
- It does not run the full `farm_context` integrity gate at session start.
  That is heavier and is a FASF phase 2 item.
- It does not enforce skill postconditions via a tool. FASF phase 2 will
  add `list_active_skills()` to return the skills relevant to the current
  context. Until then, this paste-in is the enforcement.

---

## How to test

After pasting the block into your config and starting a new Claude Desktop
session, ask: "What is pending for me?"

The Claude should run `query_logs(status="pending")`, find anything
starting with `"YOUR_NAME —"` in the notes, and list those. If it does
not, the instruction was not applied — check the system prompt field and
confirm the paste.

---

## When this doc becomes obsolete

When FASF phase 2 ships the `list_active_skills()` tool and the KB skill
library is populated, the paste-in can be replaced by a much shorter
"load and apply active skills from the KB" instruction. This doc stays in
the repo as a historical reference.
