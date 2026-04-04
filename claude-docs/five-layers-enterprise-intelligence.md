# Five Layers of Enterprise Intelligence
### And Why the Order Matters

> *Source: [Valliance AI](https://valliance.ai/what-we-think/content/five-layers-of-enterprise-intelligence-(and-why-the-order-matters)/valliance-content)*

---

## Overview

Five terms. Overlapping definitions. Different jobs. One operating system.

The concepts of **ontology**, **knowledge graph**, **semantic layer**, **context graph**, and **trust layer** have been well-defined in academic and semantic web literature for decades. The current AI hype cycle has collapsed them into interchangeable marketing language — and the confusion is costly.

Enterprises are building knowledge graphs without ontologies — the equivalent of populating a database without defining a schema. These five layers are not interchangeable. They are **sequential**. Each one answers a question the previous layer cannot, and each depends on the answers already provided beneath it. Skip a layer, and the architecture doesn't degrade gracefully — it fails structurally.

---

## The Five Questions

| Layer | Question Answered |
|---|---|
| Ontology | What does the world look like? |
| Knowledge Graph | What is true? |
| Semantic Layer | What does that mean to us? |
| Context Graph | What did we do about it? |
| Trust Layer | Should we have? |

---

## Layer 1: The Ontology — What the World Looks Like

**Core question: What exists?**

An ontology defines the **nouns and verbs** of your business:

- **Nouns** (entity types): Customer, Account, Product, Contract, Obligation
- **Verbs** (relationships): a Customer *holds* an Account; an Account *contains* Positions
- **Constraints**: a retail Customer cannot hold an institutional Product

### What it is NOT

- Not a taxonomy (which only classifies things into hierarchies)
- Not a database — it contains **no data**. It is the empty blueprint; the schema of the world model.

### Why it comes first

Without an ontology, every downstream system invents its own definitions. "Customer" means something different in CRM, Finance, and Compliance. These are three different concepts sharing one word — and until the ontology forces a canonical definition, every system is silently disagreeing with every other.

### Pragmatic note

"Ontology first" is not the only viable sequence. A practical alternative is to start with existing data, craft the ontology over it as an interpretive layer, and let the knowledge graph emerge from the combination. The ontology still gets built — inductively from observed data patterns rather than deductively from first principles. **The important thing is that it gets built at all.**

---

## Layer 2: The Knowledge Graph — Populating the World with Facts

**Core question: What is true?**

The knowledge graph populates **itself** using the ontology as its schema. Where the ontology says "a Customer holds an Account," the knowledge graph says "Acme Corp holds Account 4471-B, opened 14 March 2019, managed by Sarah McAccountmanager."

### Common misconceptions

- A **graph database** (Neo4j, Amazon Neptune) is a *storage engine*. A **knowledge graph** is a *semantic construct* — data that conforms to an ontology, with typed entities and relationships that carry meaning. You can build a knowledge graph on top of a relational database.

### The hard problems

**Entity resolution**: When the CRM stores "John Smith," the ERP stores "J. Smith," and the HRIS stores "John D. Smith" — the knowledge graph resolves them into a single canonical entity. Without class definitions from the ontology, there's no principled basis for deciding whether two records refer to the same thing.

**Semantic reconciliation**: Source systems don't merely store data in different formats — they encode different assumptions about the domain.

> "Revenue" in sales includes pipeline. In finance, it means recognised revenue. In operations, it means billable hours delivered. Same word. Three different numbers. Three different truths.

Mapping these into the knowledge graph is a **business decision**, not a technical one. The plumbing of moving data between systems is a solved problem. **Agreeing on what the data means is not.**

### Real-world examples

- **Google's Knowledge Graph**: powers search enrichment across billions of queries — went through years of iterative ontology refinement
- **LinkedIn's Economic Graph**: models people, companies, skills, and jobs — continuously evolving its ontology as new patterns emerged

---

## Layer 3: The Semantic Layer — Making Facts Speak Business

**Core question: What does that mean to us?**

The semantic layer is a **translation interface** — it maps formal knowledge graph structures into business language: metrics, definitions, and governed calculations that the organisation agrees on.

Where the knowledge graph knows Acme Corp has three accounts totalling £4.2m in contract value, the semantic layer knows this makes Acme Corp an **"Enterprise" customer** (defined as any customer with total contract value exceeding £3m).

### What it is NOT

- Not a dashboard
- Not a reporting tool

It is the **abstraction layer** that dashboards and reporting tools query against. (Tools like dbt's metrics layer and Looker's LookML popularised this concept in analytics.)

### Why it matters for agentic AI

Without a semantic layer, every AI agent that queries organisational data must interpret the knowledge graph on its own terms — deciding what "revenue" means, how to aggregate it, which accounts to include. The result: **different agents produce different answers to the same question**.

A well-constructed semantic layer gives an LLM:
- The canonical meaning of every business term
- The sanctioned calculation behind every metric
- Constraints on how data should be aggregated

> Without it, the agent hallucinates definitions. With it, the agent reasons from governed truth.

**In an agentic enterprise, the semantic layer is the guardrail that prevents autonomous systems from confidently producing different answers to the same question.**

---

## Layer 4: The Context Graph — How Decisions Get Made

**Core question: What did we do about it?**

The context graph is a **decision-trace layer** — a living record of how decisions were made against organisational facts: what data was consulted, what rules applied, what precedents existed, who approved, and what the outcome was.

### Two framings in the market

1. **Decision trace layer** (Foundation Capital framing): a record of *why* decisions were made — not just that they were made
2. **AI-optimised subgraph** (technical literature): a contextual window into the knowledge graph, scoped for a specific task or query

### Why it matters

Most organisations have no structured record of how decisions were made. The reasoning lives in email threads, Slack messages, and people's heads. **When those people leave, the reasoning leaves with them.**

The context graph captures institutional memory as a traversable, queryable structure — turning a reactive agent into one that learns from the accumulated judgement of the organisation.

### The danger

Automating decisions based on historical precedent can **encode bias**. If past decisions were systematically unfair, the context graph will faithfully represent that unfairness as precedent. Continuous evaluation of context graph outputs is essential — testing whether decision patterns reflect policy intent or merely inherited habit.

### Relationship to RAG

Standard RAG pipelines convert documents into embeddings based on what words mean to a foundation model trained on the open internet. "Revenue" is encoded as a generic financial concept.

A context graph built on top of the semantic layer inverts this — retrieval is grounded in **organisational semantics**. Terms carry the canonical definitions established in the semantic layer, not the model's generic interpretation.

> This is the difference between an agent that *sounds* informed and one that actually *is*.

---

## Layer 5: The Trust Layer — Governing It All

**Core question: Should we have?**

The trust layer is not a product or a single technical component. It is an **architectural discipline** — the set of policies, constraints, and enforcement mechanisms that govern how every other layer operates.

### What requires governance at each layer

| Layer | Governance concern |
|---|---|
| Ontology | Access control — who can modify canonical definitions? |
| Knowledge Graph | Provenance — which source is authoritative when two disagree? |
| Semantic Layer | Auditability — how was this metric derived? Can we explain it to a regulator? |
| Context Graph | Policy enforcement — should this precedent be followed, or has policy changed? |

### The laptop analogy

The trust layer is the **permissions model** of the enterprise AI operating system. Without it, any process can read any file, modify any setting, and execute any command. The system is powerful — and ungoverned. This is precisely the state of most enterprise AI deployments today.

### Regulatory context

The EU AI Act, US executive orders on AI, and sector-specific regulations in financial services and healthcare all converge on the same requirement: AI systems must be **explainable, auditable, and governable**. The trust layer is where enterprises meet this requirement architecturally — through embedded constraints — rather than through retroactive compliance bolted on after the fact.

### Governing system evolution

The trust layer must govern not just what the system does, but **how it changes**. Modifications to the ontology cascade through every downstream layer. Updates to the semantic layer change how every agent reasons. New context graph entries shift the precedent base. Each change is individually reasonable and collectively unpredictable.

---

## The Stack as a Cycle

The five layers don't just form a ladder — they form an **operating loop**.

Consider a credit approval decision:

1. Agent consults the **knowledge graph** for the applicant's data
2. References the **semantic layer** for the definition of "creditworthy"
3. Checks the **context graph** for how similar applications were handled
4. Operates within the **trust layer's** policy constraints
5. Approves the application → this becomes a new fact in the **knowledge graph**, a new decision trace in the **context graph**, and may shift **semantic layer** metrics

> The five layers are not a one-time construction project. They are an operating loop.

---

## What's Missing: Three Remaining Concerns

The knowledge architecture describes how intelligence is structured, populated, translated, contextualised, and governed — but says nothing about:

1. **The data substrate** — operational databases, data warehouses, streaming platforms, and SaaS APIs that hydrate the knowledge graph
2. **The action layer** — workflow engines, agent orchestration platforms, and human interfaces where intelligence becomes execution
3. **The learning layer** — mechanisms by which the system evolves: ontology refinement, context graph pattern recognition, trust layer anomaly detection

Add these three, and the five-layer knowledge architecture becomes a complete enterprise AI operating system.

---

## Key Takeaways

- **Don't skip layers.** Building a knowledge graph without an ontology is like populating a database without a schema.
- **Sequence matters.** Each layer depends on the one beneath it — removing any layer causes structural failure, not graceful degradation.
- **The semantic layer is now a guardrail, not a BI convenience.** In an agentic world, it prevents AI systems from generating divergent answers.
- **The context graph is institutional memory.** Without it, every AI decision is made from scratch with no awareness of precedent.
- **The trust layer governs evolution, not just outputs.** Changes cascade — the trust layer must manage this dynamism architecturally.
