# Architecture Decision Records — Firefly Corner Farm AI

This folder captures the decisions that shape the farm AI system:
what we changed, why we changed it, what it replaced, and what we'd
need to reconsider to change it again. Each ADR is a short, immutable
story of a single decision. Superseding an old ADR creates a new one
rather than editing the original.

## Why we keep ADRs here

The farm AI system has now accumulated enough moving parts
(farmOS + Apps Script + Python + TypeScript + GitHub Pages + PlantNet +
Claude UIs per role) that decisions made in one session are invisible
to the next session unless we write them down. The April 14 Leah photo
pipeline regression is the canonical example: the "always discard
rejected photos" coupling was introduced in a hardening session but
the trade-off was never recorded, so when it broke silently nobody
knew what the original intent was.

ADRs exist so future-us (and Claude-as-future-us) can answer three
questions cheaply:

1. **Why is it like this?** — not "what does the code do", but "why
   was this approach chosen over the alternatives we considered".
2. **What would we need to change to revisit it?** — what invariants,
   what dependencies, what risks.
3. **What did we learn the hard way?** — regressions and incidents
   that caused the decision should be linked from the ADR so the
   context survives.

## How to write one

Copy `TEMPLATE.md` to `NNNN-short-slug.md` where NNNN is a four-digit
zero-padded sequence number. ADRs are never deleted or rewritten —
if a later decision supersedes an earlier one, mark the old ADR as
`Status: superseded by ADR NNNN` and keep its body intact.

Keep ADRs short. One decision, one ADR. One page is usually enough;
more than three pages usually means two decisions.

Link from ADRs to:

- the code that implements them (path + commit SHA at time of
  writing if the file is likely to move)
- the team memory entry or session summary that records the
  implementation work
- any Drive documents, issues, or external references
- related ADRs (supersedes, superseded by, depends on, relates to)

## Numbering

ADRs are numbered in the order they're written, not by importance.
The number is a stable identifier — even if you later decide an ADR
is obsolete, its number stays in the folder.

## Index

| # | Title | Status |
|---|---|---|
| 0001 | Photo pipeline: always attach, verify to promote | accepted — 2026-04-15 |
| 0002 | Knowledge Base file upload via KnowledgeBase.gs | accepted — 2026-04-15 |
| 0003 | Field-sheet reconciliation audit tool and storage | accepted — 2026-04-15 |
| 0004 | Batch observation tools + Python-server photo pipeline parity | accepted — 2026-04-15 |

New entries go at the bottom of the table. Supersedings keep the old
row but mark it `superseded by ADR NNNN`.
