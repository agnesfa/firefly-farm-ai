---
name: skill_name_here
version: 0.1.0
status: draft                      # draft | active | superseded
system: B                          # A (client-side tactical) | B (shared behavioural / FASF)
trigger: trigger_identifier        # e.g. session_open, user_describes_fieldwork
last_reviewed: YYYY-MM-DD
author: Agnes, Claude
supersedes: none
related_adr: 0006                  # comma-separated ADR numbers this skill implements / depends on
related_ontology_verbs: []         # verbs from knowledge/farm_ontology.yaml this skill handles
---

# Skill: {skill_name_here}

## Purpose

One paragraph. What does this skill give the system that it doesn't have without it? Who benefits? Reference the real incident / pattern that motivated the skill — the pre-ratification conversation context is the best source.

## Trigger

When does this skill run? Be specific. Some skills run every session; some run only on explicit user intent; some run on specific tool outputs.

- Exact conditions (one per line):
  - Condition A
  - Condition B

## Preconditions

What must be true before the skill executes? If a precondition fails, the skill does not run — it reports the missing precondition and defers.

- Precondition 1
- Precondition 2

## Procedure

Ordered, concrete steps. Each step is a tool call or a decision rule. No prose.

### Step 1 — Step name

- Tool: `tool_name(args)`
- Decision: if X then Y else Z

### Step 2 — Step name

...

## Postconditions

After the skill completes, what must be true? These are asserted explicitly — the agent states them in the session summary so a reviewer can verify.

- Postcondition 1 (observable how)
- Postcondition 2 (observable how)

## Failure mode

For every step that can fail, what does the agent do? Default: record the failure explicitly in the session summary — **never silently drop**.

- Step N fails → {action: retry once | abort | defer | flag}
- Tool unavailable → {action}
- Data missing → {action}

## Dependencies

- MCP tools: `tool_a`, `tool_b`
- Knowledge files: `knowledge/plant_types.csv`, `knowledge/farm_ontology.yaml`
- Other skills this one invokes: `record_fieldwork`, `ingest_knowledge`
- External services: PlantNet, GitHub Pages

## Example

A concrete end-to-end example of the skill running. Real data, real outputs.

## Known gaps

Open issues / TODO items before the skill is fully production-ready. Each should eventually become either a task or a reason to supersede this skill.

- Gap 1
- Gap 2

## Lineage

- Origin: what prompted the skill
- Related ADRs: which ADRs reference or depend on this skill
- Related feedback / memory entries: any user-memory files that back this behaviour
