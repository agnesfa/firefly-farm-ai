# Farm Intelligence Layer — Design in Five Layers

> **A Cooperative Intelligence Architecture for Firefly Corner Farm**
>
> Based on the Valliance AI "Five Layers of Enterprise Intelligence" framework.
> Designed as a portable pattern for any domain where entities have lifecycles
> and humans + AI cooperate to observe, decide, and act.
>
> Created: April 4, 2026
> Authors: Agnes + Claude Code (from Claude mobile session analysis + Claude Code enhancement)
> Status: Design complete — implementation in progress

---

## 1. The Core Pattern

Entities have lifecycles. Humans and AI observe, decide, and act on those entities. Intelligence emerges when the system tracks not just **what happened**, but **what it means** and **why decisions were made**. Intelligence **compounds** when those traces feed back into better future observations, decisions, and actions.

This pattern applies to:
- **Firefly Corner Farm** — plants moving through syntropic lifecycle stages, humans (Claire, WWOOFers, Agnes) and AI cooperating to track and nurture them
- **COIP Platform** — orders moving through fulfillment lifecycle, customers + agents + staff cooperating
- **Any Firefly Agents application** — entities, lifecycles, human-AI cooperation

### The Five Questions

| Layer | Question | What It Provides |
|-------|----------|-----------------|
| 1. Ontology | What exists? | The empty blueprint. Entity types, relationships, constraints. Contains NO data. |
| 2. Knowledge Graph | What is true? | Facts populating the ontology. Real entities, real relationships, real measurements. |
| 3. Semantic Layer | What does that mean to us? | Translation from facts to meaning. Governed metrics, canonical definitions. |
| 4. Context Graph | What did we do about it? | Decision traces. Not just WHAT happened, but WHY. Institutional memory. |
| 5. Trust Layer | Should we have? | Provenance, access control, confidence. The system evaluating its own reliability. |

### Why Order Matters

The Valliance article's central argument: these layers are **sequential and load-bearing**. Skip a layer and the architecture fails structurally, not gracefully.

- Build a knowledge graph without an ontology → every system invents its own definitions, "Pigeon Pea" means something different in each silo
- Apply a semantic layer without a knowledge graph → metrics calculated on incomplete or inconsistent facts
- Build a context graph without a semantic layer → decision traces reference undefined terms, past decisions can't be compared

### The Compounding Intelligence Test

Ask "How is the farm doing?" in session 1 and again in session 50.

- **If intelligence compounds:** Session 50 is faster, more precise, uses established definitions, references past decisions, identifies patterns session 1 couldn't see.
- **If not compounding:** Each session reads CLAUDE.md, queries 5 systems, improvises definitions, produces a unique-to-this-session response. Data accumulates but intelligence doesn't compound because there's no semantic layer to lock in meaning and no context graph to lock in decisions.

**Today the farm is in the second state.** This design fixes that.

---

## 2. Layer 1 — The Farm Ontology: What Exists

### Current State: IMPLICIT

The farm has an ontology — it's scattered across CLAUDE.md (prose), plant_types.csv (column structure), farmOS schema (JSON:API types), and Agnes's head. Entity types like Plant, Section, Species exist in code but are not formally specified anywhere a human can review or a machine can validate against.

### The Ontology as Explicit Artifact

**File: `knowledge/farm_ontology.yaml`**

This is the farm's schema of reality. It must be:
- **Human-reviewable** — Claire or a future farm manager can read it and say "yes, this is how our farm works" or "no, we've added something new"
- **Maintainable** — version-controlled in git, changes are explicit commits with rationale
- **Portable** — not tied to farmOS. If the farm moves to a different platform, the ontology travels
- **Evolutionary** — grows as new concepts emerge from field reality

### Entity Types

#### farmOS-Backed Entities

| Entity | farmOS Type | Canonical ID | Description |
|--------|------------|-------------|-------------|
| **Plant** | `asset/plant` | asset name | A specific planting instance: species + section + date + status |
| **Species** | `taxonomy_term/plant_type` | farmos_name | The type of plant, with strata/succession/functions. Enriched by plant_types.csv until Phase 4 farm_syntropic module adds these as native fields |
| **Section** | `asset/land` | section ID (P2R3.15-21) | A physical portion of a row, with QR code pole |
| **Row** | `asset/land` | row prefix (P2R3) | A cultivated row containing sections |
| **Paddock** | `asset/land` | paddock prefix (P2) | A cultivated area containing rows |
| **WaterAsset** | `asset/water` | asset name | Dams, trenches, keyline water infrastructure |
| **Structure** | `asset/structure` | asset name | Buildings: nursery, camp, amenities block |
| **Equipment** | `asset/equipment` | asset name | Tools, machinery |
| **CompostBay** | `asset/compost` | asset name | Active compost production bays |
| **Seed** | `asset/seed` | asset name | Seed inventory (263 records in CSV, to be created in farmOS) |
| **Material** | `asset/material` | asset name | Mulch, soil amendments, supplies |

#### Non-farmOS Entities

| Entity | Canonical Source | ID Format | Description |
|--------|-----------------|-----------|-------------|
| **Actor** | Implicit (to be formalized) | name | A person who observes, decides, or acts. Has role: manager, farmhand, visitor |
| **Task** | farmOS `log/activity` (status=pending) | log name | A planned action in the decision pipeline: pending → in_progress → done |
| **Observation** | farmOS `log/observation` + QR Sheet | log name / submission_id | A field report: inventory count, condition, photo |
| **KnowledgeEntry** | Knowledge Base (Apps Script) | entry_id (UUID) | Codified learning: tutorials, SOPs, references, source materials |
| **Supplier** | seed_bank.csv | supplier name | Seed and plant sources (18 known) |
| **Harvest** | Harvest Sheet (Apps Script) | submission_id | A recorded harvest: species, weight, location, date |
| **Session** | Team Memory (Apps Script) | summary_id | A decision trace: topics, decisions made, questions raised, farmOS changes |

### Relationships

```
Plant  ──GROWS_IN──▶  Section
Plant  ──IS_SPECIES──▶  Species
Species  ──HAS_STRATA──▶  {emergent, high, medium, low}
Species  ──HAS_SUCCESSION──▶  {pioneer, secondary, climax}
Species  ──HAS_FUNCTIONS──▶  [nitrogen_fixer, edible_fruit, ...]
Section  ──BELONGS_TO──▶  Row  ──BELONGS_TO──▶  Paddock
Seed  ──IS_SPECIES──▶  Species
Seed  ──FROM_SUPPLIER──▶  Supplier
Task  ──TARGETS──▶  Section | Plant | Species
Task  ──CREATED_BY──▶  Actor | Session
Task  ──COMPLETED_BY──▶  Actor
Observation  ──REFERENCES──▶  Plant | Section
Observation  ──REPORTED_BY──▶  Actor
KnowledgeEntry  ──COVERS_SPECIES──▶  [Species...]  (via related_plants)
KnowledgeEntry  ──COVERS_SECTION──▶  [Section...]  (via related_sections)
KnowledgeEntry  ──COVERS_DOMAIN──▶  [Topic...]  (via topics field)
Harvest  ──OF_SPECIES──▶  Species
Harvest  ──FROM_SECTION──▶  Section
Harvest  ──RECORDED_BY──▶  Actor
Session  ──BY_ACTOR──▶  Actor
Session  ──REFERENCES_CHANGES──▶  [farmOS entity UUIDs]
```

### Constraints

```
# Syntropic rules
A tree Section SHOULD have all 4 strata represented (emergent, high, medium, low)
An open Section SHOULD have at least 2 strata (medium, low)
Pioneer species ARE EXPECTED to die — low survival is design intent, not failure
Every active Section SHOULD have an observation within 30 days

# Naming conventions
Plant asset name = "{date_label} - {farmos_name} - {section_id}"
Section ID format = P{n}R{n}.{start}-{end} | NURS.{zone} | COMP.{bay}
Species canonical name = farmos_name from plant_type taxonomy

# Lifecycle rules
Seed → (Seeding Log) → Plant (in nursery) → (Transplanting Log) → Plant (in field)
Task: pending → in_progress → done (with rationale at each transition)
Every Plant MUST have a Species relationship
Every Section MUST belong to a Row
```

### The Join Keys

| Key | Connects | Example |
|-----|----------|---------|
| `farmos_name` | Plant ↔ Species ↔ KnowledgeEntry (related_plants) ↔ Seed | "Pigeon Pea" |
| Section ID | Section ↔ Plant (location) ↔ KnowledgeEntry (related_sections) ↔ Observation | "P2R3.15-21" |
| Topic | Farm domain ↔ KnowledgeEntry (topics) ↔ farmOS section prefixes | "nursery" → NURS.* |
| Actor name | Session ↔ Observation ↔ Task | "Claire", "Maverick" |

---

## 3. Layer 2 — The Farm Knowledge Graph: What Is True

### Current State: WORKING BUT FRAGMENTED

farmOS **is** the knowledge graph. 700+ plant assets, 1260+ logs, 272 plant types, 93+ land assets. It contains typed entities and typed relationships that conform to a schema.

But the knowledge graph is fragmented across **7 separate data stores**:

| Store | What It Holds | API |
|-------|--------------|-----|
| farmOS (margregen.farmos.net) | Plants, land, logs, inventory, taxonomy | JSON:API |
| plant_types.csv | Enriched species metadata (strata, functions, botanical names) | File read |
| Knowledge Base (Google Sheet) | Tutorials, SOPs, guides, references | Apps Script |
| Field Observations (Google Sheet) | QR-submitted field reports | Apps Script |
| Team Memory (Google Sheet) | Session summaries, decisions | Apps Script |
| Seed Bank (Google Sheet) | Seed inventory, suppliers | Apps Script |
| Harvest Log (Google Sheet) | Harvest records | Apps Script |

### Entity Resolution

The hardest Layer 2 problem is alive at the farm:

- "Cherry Guava" vs "Guava (Strawberry)" vs "Psidium cattleianum" → same Species
- "pigeon pea" in Claire's spreadsheet vs "Pigeon Pea" in farmOS → same Species
- The v6→v7 plant types migration (March 2026) was entity resolution at scale: 16 renames, 15 archives, 157 creates

The `farmos_name` join key and species name normalization are entity resolution mechanisms. The `farm_context` tool must use these same join keys to traverse across stores.

### Known Fragility

- farmOS pagination caps at ~250 results with `links.next` — must use offset-based pagination
- Archived records consume pagination slots even with `status=active` filter
- Write tools must use `fetchByName` (direct query) for existence checks, not CONTAINS result sets
- No real-time sync between stores — pages regenerated manually, KB entries added manually

---

## 4. Layer 3 — The Farm Semantic Layer: What It Means

### Current State: ABSENT — THE CRITICAL GAP

Every Claude session invents its own definitions. "Healthy section" means something different depending on the question, the session, and which Claude is answering.

### The Semantic Layer as Curated Definitions + Computable Code

**File: `knowledge/farm_semantics.yaml`** — human-readable, reviewable definitions
**File: `mcp-server/semantics.py`** — code that reads YAML and computes metrics

The YAML is what Agnes and Claire review. The code reads the YAML and computes. When field reality contradicts a definition, Agnes updates the YAML.

### Semantic Definitions

#### Section Health

| Metric | Definition | Thresholds |
|--------|-----------|------------|
| **Strata Coverage** | Fraction of expected strata with living plants. Expected: 4 for tree sections, 2 for open. | good ≥ 0.75, fair ≥ 0.50, poor < 0.50 |
| **Survival Rate** | Living / total ever planted. Note: low pioneer survival is EXPECTED by design. | healthy ≥ 0.70, concerning ≥ 0.50, at_risk < 0.50 |
| **Activity Recency** | Days since last observation or activity log. | active ≤ 14, needs_attention ≤ 30, neglected > 60 |
| **Succession Balance** | Pioneer:secondary:climax ratio. Varies by section age. | Young: pioneer-heavy. Maturing: transitioning. Established: climax dominant. |

#### Plant-Level

| Metric | Definition |
|--------|-----------|
| **Transplant Readiness** | Nursery plant age exceeds species.transplant_days |
| **Species Distribution** | Count of sections where species has living plants |

#### Knowledge

| Metric | Definition |
|--------|-----------|
| **KB Coverage** | Whether KB entries exist for each species in the field and each active farm domain |
| **Workflow Reproducibility** | Whether SOPs exist for common field tasks |

#### Decision Pipeline (Layer 4 Integration)

| Metric | Definition | Thresholds |
|--------|-----------|------------|
| **Task Completion Rate** | Completed / created tasks per period | healthy ≥ 0.80, concerning ≥ 0.60 |
| **Observation-to-Action Ratio** | Observations that led to follow-up tasks | High = responsive. Low = observations filed but not acted on. |
| **Decision Trace Completeness** | Tasks with rationale recorded | Tracks whether the "why" is being captured |

### Feedback Loops

| Signal | Action |
|--------|--------|
| Survival rate consistently violates threshold for pioneers | Review ontology: is strata/succession classification correct? |
| Transplant readiness predictions fail | Review semantic definition: is transplant_days accurate for this climate? |
| Tasks go unactioned despite observations | Review decision pipeline: is the task workflow working? |
| Different sessions give different health assessments | Review semantic definitions: are thresholds clear enough? |

---

## 5. Layer 4 — The Farm Context Graph: What We Did About It

### Current State: EMBRYONIC

Team Memory captures WHAT was discussed, not WHY. farmOS logs record WHAT was done, not the reasoning. When Claire left, her decision rationale left with her.

### The Decision Lifecycle

```
OBSERVE → DECIDE → PLAN → ASSIGN → EXECUTE → REPORT → LEARN
   │         │        │       │         │         │        │
   │         │        │       │         │         │        └─▶ KnowledgeEntry
   │         │        │       │         │         └─▶ Observation log
   │         │        │       │         └─▶ Activity log (done)
   │         │        │       └─▶ Actor picks up task
   │         │        └─▶ Task (pending, with rationale)
   │         └─▶ Session decision trace
   └─▶ Observation (field walk, QR report, transcript)
```

**Example chain:**
1. OBSERVE: Claire notices pigeon pea die-off in P2R3.15-21
2. DECIDE: "Replant with hardened nursery stock — frost was the cause"
3. PLAN: `create_activity(section="P2R3.15-21", notes="Replant 3 pigeon pea — frost-hardened stock from NURS.SH2-1", status="pending")`
4. ASSIGN: WWOOFer Maverick takes on the task
5. EXECUTE: Maverick transplants
6. REPORT: QR observation with count update
7. LEARN: Frost-hardened stock survives → add to KB as frost management technique

### What's Missing Today

- Linking tasks to triggering observations (the "because" link)
- Linking task completion to outcome observations (the "did it work?" link)
- Structured rationale on tasks (not just "water nursery" but "water nursery because shelf 2 seedlings wilting, no watering in 5 days")

The `farm_context` tool assembles this chain from existing data. Over time, the chain becomes more explicitly tracked.

---

## 6. Layer 5 — The Trust Layer: Should We Have?

### Lightweight Trust for Prototype

| Concern | Implementation |
|---------|---------------|
| Ontology governance | Only Agnes modifies `farm_ontology.yaml` — git commits with rationale |
| Semantic governance | `farm_semantics.yaml` versioned in git. Breaking changes require review |
| Provenance | farmOS logs track who/when. Add source attribution (AI vs human) |
| Confidence flags | `farm_context` includes confidence: HIGH (complete data) vs LOW (missing attributes) |

---

## 7. The `farm_context` Tool

### Signature

```python
farm_context(
    subject: str = None,   # Species (e.g., "Pigeon Pea")
    section: str = None,   # Section ID (e.g., "P2R3.15-21")
    topic: str = None      # Farm domain (e.g., "nursery")
)
```

### Response — All Five Layers

```json
{
  "query": {"type": "section", "id": "P2R3.15-21"},
  "ontology": {
    "entity_type": "Section",
    "constraints": ["tree section — expects 4 strata"],
    "relationships": ["belongs_to: P2R3, Paddock 2"]
  },
  "facts": {
    "plants": [...],
    "kb_entries": [...],
    "plant_type_metadata": {...}
  },
  "interpretation": {
    "strata_coverage": {"score": 1.0, "status": "good"},
    "survival_rate": {"score": 0.83, "status": "healthy"},
    "activity_recency": {"days": 12, "status": "active"},
    "succession_balance": {"pioneer": 40, "secondary": 35, "climax": 25}
  },
  "context": {
    "pending_tasks": [...],
    "recent_observations": [...],
    "decision_chain": [...],
    "actors_involved": [...]
  },
  "gaps": [
    "No frost protection SOP in Knowledge Base",
    "Pending task has no actor assigned"
  ]
}
```

---

## 8. The Ontology Evolution Protocol

When encountering a new concept in a transcript, CSV, observation, or any data:

```
1. CLASSIFY: Is this an instance of an existing entity type?
   YES → Map to existing type (entity resolution). Done.
   NO → Continue.

2. ASSESS: Does this concept have:
   a) Its own lifecycle? (created → active → archived)
   b) Relationships to 2+ other entities?
   c) Attributes that matter for decisions?
   YES to any → candidate for new entity type.
   NO to all → attribute of an existing entity.

3. FORMALIZE: Add to farm_ontology.yaml with:
   - Entity type + canonical source system
   - Relationships to existing entities
   - Constraints
   - Git commit with WHY

4. PROPAGATE: Check downstream:
   - Does farm_semantics.yaml need new metrics?
   - Does farm_context need a new query path?

5. VALIDATE: Human review → commit
```

---

## 9. Portability to COIP and Beyond

| Farm Pattern | COIP Equivalent |
|-------------|----------------|
| Species (plant_type taxonomy) | Product (catalog) |
| Plant (asset in section) | Order (in fulfillment pipeline) |
| Section (location) | Warehouse/Store (fulfillment location) |
| Task (pending activity) | Action Required (order intervention) |
| Observation (field report) | Interaction Record (customer conversation) |
| KnowledgeEntry (tutorial/SOP) | Resolution Playbook |
| Actor (Claire, Maverick) | Agent + User (CSR, customer) |
| Session (team memory) | Thread (Mastra conversation) |

### The Portable Abstract

```yaml
ontology:
  entities: [Subject, Instance, Location, Task, Observation, Knowledge, Actor, Session]
  relationships: [INSTANCE_OF, LOCATED_AT, TARGETS, OBSERVED_BY, COVERS, DECIDED_BY]

semantic_layer:
  metrics: [health_score, coverage_score, recency_score, pipeline_score]
  feedback_loops: [threshold_violations → ontology_review]

context_graph:
  lifecycle: [observe → decide → plan → assign → execute → report → learn]
  traces: [who, what, why, when, outcome]
```

---

## 10. Interaction Intelligence — Learning from Human-AI Conversations

### The Principle

Every human-AI conversation is a signal. What questions people ask, what data they pull, whether the answer satisfied them — these are rich indicators of what the system gets right and where it fails. The COIP platform captures this explicitly with **sentiment scores** on every interaction. The farm should do the same.

### Signals from Conversations

| Signal | What It Reveals | How to Detect |
|--------|----------------|---------------|
| **Repeated questions** | The answer wasn't satisfying or wasn't persisted | Same query pattern across multiple sessions |
| **Question type by role** | What each person needs that the system doesn't surface proactively | James asks about marketing/story → system should surface harvest yields automatically. Claire asks about plant health → system should push strata reports. |
| **Data pull frequency** | What entities/sections/species get the most attention | Rank MCP tool calls by entity — high-frequency = high-priority for proactive monitoring |
| **Follow-up depth** | Whether initial answers are sufficient | Single-turn resolution = good. Multi-turn clarification = definition gap or data gap |
| **Correction rate** | How often the human corrects the AI's interpretation | "No, that's not what healthy means" = semantic layer gap |
| **Tool call patterns** | Whether the AI queries the right systems in the right order | If Claude always queries farmOS then KB then plant_types → that's the natural join order for farm_context |
| **Unanswered questions** | What the system can't answer at all | "Why did Claire plant tagasaste here?" → context graph gap |
| **Satisfaction signal** | Whether the human acted on the answer | Task created after query = answer was useful. No action = answer was noise. |

### Per-Role Intelligence

| Actor | Typical Questions | What They Need Proactively |
|-------|------------------|---------------------------|
| **Agnes** (CTO) | System health, architecture, cross-farm patterns | Weekly digest: data quality, tool reliability, team activity |
| **James** (Marketing) | Harvest stories, section stories, visitor content | Section highlights: "P2R3 has full strata for the first time" |
| **Claire** (Agronomist) | Plant health, planting plans, nursery readiness | Transplant alerts, strata gaps, renovation candidates |
| **WWOOFers** | "What do I do in this section?", task lists | Pre-computed daily task lists based on pending activities |

### Implementation: Session Metadata

Team Memory already captures session summaries. Enhance with:

```yaml
session_metadata:
  actor: "James"
  role: "manager"
  duration_turns: 8        # conversation length
  tools_called:            # which MCP tools were used
    - query_plants: 2
    - search_knowledge: 3
    - get_inventory: 1
  entities_referenced:      # what was discussed
    species: ["Pigeon Pea", "Macadamia"]
    sections: ["P2R3.15-21"]
    topics: ["harvest", "paddock"]
  satisfaction_signal: "task_created"  # or "no_action", "correction", "follow_up"
  corrections: 0            # times the human corrected the AI's interpretation
  unanswered: []            # questions the system couldn't answer
```

This metadata accumulates into a **usage intelligence layer** that reveals:
- Which semantic definitions are working (low correction rate)
- Which are drifting (high correction, repeated questions)
- What proactive intelligence each role needs (frequent pull patterns → push instead)
- Where the ontology has gaps (unanswered questions about entities that don't exist)

### The Feedback Loop to Upper Layers

```
Interaction signals → Detect pattern → Feed back to:
  - Ontology: new entity type needed (unanswered questions about undefined concepts)
  - Semantic Layer: threshold wrong (corrections), definition unclear (repeated questions)
  - Context Graph: decision trace missing (why-questions with no answer)
  - Knowledge Base: coverage gap (frequent queries about topics with no KB entries)
```

This is the **learning layer** the Valliance article identifies as missing from the five layers: "mechanisms by which the system evolves." The interaction signals ARE the learning mechanism.

---

## 11. Scale Triggers

| Layer | Trigger | Status |
|-------|---------|--------|
| L2 → Production | Query returns > 250 results | Already past — pagination fix needed |
| L3 → Governed | Different sessions give different assessments | Happening now — **build immediately** |
| L4 → Traceable | "Why did we do X?" has no answer | Beginning — Claire left, decisions lost |
| L5 → Governed Evolution | Unauthorized change cascades into bad data | Not yet critical |

---

## 12. Source Documents

| Document | Location |
|----------|----------|
| Five Layers of Enterprise Intelligence | `claude-docs/five-layers-enterprise-intelligence.md` |
| Phase KB: Knowledge Cross-Referencing | `claude-docs/phase-kb-knowledge-crossref.md` |
| Claude Mobile Session Transcript | `claude-docs/session-pull-next-planned-build-2026-04-04.md` |
| Shared Farm Intelligence Options | `claude-docs/shared-intelligence.md` |
| COIP Target Architecture | `~/Repos/fireflyagents/fa-coi-platform/claude-docs/coip-target-architecture-202603/` |
| Pagination Fix Plan | `claude-docs/pagination-fix-plan.md` |

---

*This document is the reference architecture for the Farm Intelligence Layer. It evolves as the farm evolves. Changes should be committed with rationale.*
