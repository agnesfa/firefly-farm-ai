# 0011 — Read-side tool surface must cover the full data model, not a stylised subset

- **Status:** accepted — 2026-05-24
- **Date:** 2026-05-24
- **Authors:** Agnes, Claude
- **Related:** ADR 0009 (farmOS v4 cutover), `feedback_read_side_tool_surface_gap` memory note

## Context

A 2026-05-24 diagnostic session surfaced that three of the MCP read
tools cannot enumerate row-level or paddock-level land assets:

- `query_sections` filters via the regex `^P\dR\d\.\d+-\d+$` —
  matches only section-shaped names like `P1R2.0-14`. Row-level
  (`P1R2`) and paddock-level (`P1`) assets are silently excluded.
- `get_farm_overview` derives "rows" by splitting section names on
  `.`, so any row that has no sections is invisible.
- `query_logs(section_id="P1R2")` returned 0 logs even though P1R2 has
  logs in farmOS, because the filter matched on the log NAME substring
  rather than the log's `location` relationship.

I concluded P1R2 and P1R4 "didn't exist" and nearly created duplicate
row assets. The data was there; the tool surface didn't enumerate it.

The `getAllLocations` helper already fetches every land + structure
asset, but it buckets everything not matching the section/nursery/compost
regex into a `grouped.other` bucket that no MCP tool surfaces. So the
gap was tool-surface, not data-access.

## Decision

Three changes, both servers (TypeScript + Python):

1. **New tool `query_locations`** that enumerates ALL land + structure
   assets and classifies each by `level` (`paddock` | `row` | `section`
   | `nursery` | `compost` | `structure` | `other`). Filters: `name`
   (exact), `name_prefix`, `level`, `include_archived`. Returns a list
   of locations plus per-level counts.

2. **`query_logs` now uses `filter[location.id]=<UUID>`** when the
   `section_id` input resolves to a known land/structure asset — this
   is the structurally correct way to find "every log attached to
   P1R2", matching the farmOS data model (logs reference location
   assets via the `location` relationship). When the name doesn't
   resolve, falls back to the old name-substring behaviour for back-
   compat and surfaces `filter_method` on the response so the caller
   knows which path was taken.

3. **Memory note** (`feedback_read_side_tool_surface_gap.md`) +
   index entry in `MEMORY.md` recording the rule: never conclude an
   asset/log doesn't exist from a single MCP read tool returning zero.

`get_farm_overview` is left as-is for now — the section-derived row
view is documented behaviour, and the new `query_locations` tool
provides the truth-source for "which rows exist."

## Rationale

The bug class isn't about a missing feature — it's about a tool
surface that *looks complete* but enumerates a stylised subset of the
data model. When an LLM (me) reads `query_sections` and sees a clean
section list, it has no signal that row-level and paddock-level land
assets exist beyond the regex. Worse, when `query_logs` returns 0 for
a real asset, there's no signal that the filter was substring matching
on names rather than the structural attachment relationship — the
result looks authoritative.

The fix is two-pronged: a new tool that exposes the complete surface
(`query_locations`), and a correctness fix to the existing tool's
filter semantics (`query_logs` → location-id), with explicit
`filter_method` on the response so future "0 results" findings carry
their own context.

### Alternatives considered

- **Just add the level classifier to `query_sections`.** Rejected:
  the tool's name is "sections" and its semantics are documented
  (sections only). Adding rows/paddocks would surprise existing
  callers (the QR site generator, etc.) and conflate two different
  questions.
- **Just fix `query_logs` and live with the section-surface gap.**
  Rejected: half the bug. The diagnostic incident would have still
  happened — I'd have queried logs successfully but concluded the
  parent asset didn't exist based on `query_sections`.
- **Auto-create row assets when `create_plant` references a missing
  one.** Rejected: write-tool auto-creation hides the data-model gap
  and creates lower-quality assets (no parent relationships, no
  land_type, etc.). The right fix is to make the read surface
  trustworthy and rely on humans/Claude to do the creation explicitly.
- **Drop the name-substring fallback in `query_logs` entirely.**
  Rejected: there are real cases where the section_id input is mis-
  spelled or pre-cleanup (e.g. an old log mentions `P2R3.15-21` in its
  name even though the location was reorganised) — silent zero
  results would be worse UX than a fallback with a surfaced flag.

## Consequences

### Positive

- Row-level and paddock-level assets are now discoverable through the
  MCP surface. Future "does P1R2 exist?" questions have a clean
  answer in one tool call.
- `query_logs` now matches the farmOS data model — logs attached to a
  location are findable regardless of what the log was named.
- The `filter_method` field on `query_logs` responses turns silent
  fallbacks into observable ones.
- Sets precedent for the post-v4 read-side audit (open backlog item).
  Every read tool should have its filter semantics scrutinised the
  same way.

### Negative

- One more tool name to remember (`query_locations` vs
  `query_sections`). Mitigated by clear tool descriptions that point
  to the new tool when the old one returns nothing surprising.
- The `query_logs` semantic change is technically a contract change:
  previously a section_id that didn't resolve still produced
  name-substring results without flagging that the input was unknown.
  Mitigated by keeping the fallback path and surfacing the method
  on the response — callers that ignored the unrecognised section
  before still get the same result.

### Neutral

- Test count: TS 320 → 340 (+20), Python +20 expected once Agnes
  runs the suite locally.
- No farmOS API or schema change. v3 and v4 both expose
  `filter[location.id]` on log endpoints — verified via the existing
  `api-version.ts` helpers; no new conditional logic needed.

## Implementation

Files changed:

- **TS server:**
  - `mcp-server-ts/plugins/farm-plugin/src/clients/farmos-client.ts`
    — new `getLocations()` + `fetchLogsByLocationId()`, refactored
    `getLogs()` to use attachment filter when resolvable.
  - `mcp-server-ts/plugins/farm-plugin/src/tools/query-locations.ts`
    — new tool.
  - `mcp-server-ts/plugins/farm-plugin/src/tools/query-logs.ts` —
    description + response shape update (adds `filter_method`).
  - `mcp-server-ts/plugins/farm-plugin/src/tools/index.ts` —
    register `queryLocationsTool`.
  - `mcp-server-ts/plugins/farm-plugin/src/__tests__/query-locations.test.ts` (new, 12 tests)
  - `mcp-server-ts/plugins/farm-plugin/src/__tests__/query-logs-attachment.test.ts` (new, 8 tests)
- **Python server:**
  - `mcp-server/farmos_client.py` — new `get_locations()` +
    `fetch_logs_by_location_id()`; `get_logs()` split into
    `get_logs()` (back-compat list return) + `get_logs_with_method()`
    (returns `(logs, filter_method)`).
  - `mcp-server/server.py` — `query_locations` tool added,
    `query_logs` updated to use `get_logs_with_method` and surface
    `filter_method`.
  - `mcp-server/tests/test_query_locations.py` (new)
  - `mcp-server/tests/test_query_logs_attachment.py` (new)
- **Docs:**
  - This ADR.
  - `/Users/agnes/.claude/projects/-Users-agnes-Repos-FireflyCorner/memory/feedback_read_side_tool_surface_gap.md`
  - Index entry in `MEMORY.md` Pinned references.

**Deployment:** TS server needs a Railway redeploy. Python server is
local-only and picks up changes on next session start.

## Open questions

- **Should the QR site generator move off `query_sections` /
  `get_farm_overview` and onto `query_locations`?** — Agnes, when the
  generator is next touched. Today's site templates only need
  sections, so no urgency.
- **Should `get_farm_overview` itself enumerate rows via
  `query_locations` rather than deriving from sections?** — Agnes.
  Useful for "are there rows with no sections?" insight but changes
  the overview shape; defer until there's a concrete need.
- **Read-side audit of every tool's filter semantics** — open backlog
  item from this incident. `query_plants(section_id=...)` uses CONTAINS
  on plant NAME, which has the same structural mismatch as the old
  `query_logs`. Worth fixing, but a separate PR — plants are named
  with the section ID embedded by convention so the bug is latent, not
  active.
