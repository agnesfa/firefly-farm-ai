#!/usr/bin/env python3
"""Generate the Farm Intelligence Layer whitepaper as PDF."""

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.lib.units import mm, cm
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether,
)

# ── Colors ────────────────────────────────────────────────

FOREST_GREEN = HexColor("#2d5016")
DARK_GREEN = HexColor("#1a3a0a")
MEDIUM_GREEN = HexColor("#4a7c29")
LIGHT_GREEN = HexColor("#e8f0e0")
WARM_AMBER = HexColor("#8b6914")
SOFT_GREY = HexColor("#f5f5f0")
TEXT_DARK = HexColor("#1a1a1a")
TEXT_MID = HexColor("#444444")
ACCENT_ORANGE = HexColor("#c4722a")

# ── Styles ────────────────────────────────────────────────

styles = getSampleStyleSheet()

styles.add(ParagraphStyle(
    name="WPTitle", fontName="Helvetica-Bold", fontSize=26,
    textColor=DARK_GREEN, alignment=TA_CENTER, spaceAfter=6*mm,
    leading=32,
))
styles.add(ParagraphStyle(
    name="WPSubtitle", fontName="Helvetica", fontSize=14,
    textColor=MEDIUM_GREEN, alignment=TA_CENTER, spaceAfter=4*mm,
    leading=18,
))
styles.add(ParagraphStyle(
    name="WPAuthor", fontName="Helvetica-Oblique", fontSize=10,
    textColor=TEXT_MID, alignment=TA_CENTER, spaceAfter=12*mm,
))
styles.add(ParagraphStyle(
    name="WPH1", fontName="Helvetica-Bold", fontSize=18,
    textColor=FOREST_GREEN, spaceBefore=10*mm, spaceAfter=4*mm,
    leading=22,
))
styles.add(ParagraphStyle(
    name="WPH2", fontName="Helvetica-Bold", fontSize=13,
    textColor=MEDIUM_GREEN, spaceBefore=6*mm, spaceAfter=3*mm,
    leading=16,
))
styles.add(ParagraphStyle(
    name="WPH3", fontName="Helvetica-Bold", fontSize=11,
    textColor=WARM_AMBER, spaceBefore=4*mm, spaceAfter=2*mm,
))
styles.add(ParagraphStyle(
    name="WPBody", fontName="Helvetica", fontSize=10,
    textColor=TEXT_DARK, alignment=TA_JUSTIFY, spaceAfter=3*mm,
    leading=14,
))
styles.add(ParagraphStyle(
    name="WPBodyBold", fontName="Helvetica-Bold", fontSize=10,
    textColor=TEXT_DARK, alignment=TA_JUSTIFY, spaceAfter=3*mm,
    leading=14,
))
styles.add(ParagraphStyle(
    name="WPQuote", fontName="Helvetica-Oblique", fontSize=10,
    textColor=MEDIUM_GREEN, leftIndent=15*mm, rightIndent=15*mm,
    spaceBefore=4*mm, spaceAfter=4*mm, leading=14,
    alignment=TA_CENTER,
))
styles.add(ParagraphStyle(
    name="WPBullet", fontName="Helvetica", fontSize=10,
    textColor=TEXT_DARK, leftIndent=8*mm, bulletIndent=3*mm,
    spaceAfter=1.5*mm, leading=13,
))
styles.add(ParagraphStyle(
    name="WPCaption", fontName="Helvetica-Oblique", fontSize=8.5,
    textColor=TEXT_MID, alignment=TA_CENTER, spaceBefore=2*mm,
    spaceAfter=4*mm,
))
styles.add(ParagraphStyle(
    name="WPFooter", fontName="Helvetica", fontSize=8,
    textColor=TEXT_MID, alignment=TA_CENTER,
))

# ── Helpers ───────────────────────────────────────────────

def h1(text): return Paragraph(text, styles["WPH1"])
def h2(text): return Paragraph(text, styles["WPH2"])
def h3(text): return Paragraph(text, styles["WPH3"])
def body(text): return Paragraph(text, styles["WPBody"])
def bold(text): return Paragraph(text, styles["WPBodyBold"])
def quote(text): return Paragraph(text, styles["WPQuote"])
def bullet(text): return Paragraph(f"\u2022  {text}", styles["WPBullet"])
def caption(text): return Paragraph(text, styles["WPCaption"])
def spacer(h=4): return Spacer(1, h*mm)

def hr():
    return HRFlowable(width="80%", thickness=0.5, color=LIGHT_GREEN,
                       spaceBefore=4*mm, spaceAfter=4*mm)

def make_table(data, col_widths=None):
    """Create a styled table."""
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), FOREST_GREEN),
        ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#ffffff")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("BACKGROUND", (0, 1), (-1, -1), SOFT_GREY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [SOFT_GREY, HexColor("#ffffff")]),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, HexColor("#cccccc")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


# ── Document ──────────────────────────────────────────────

def build_document():
    doc = SimpleDocTemplate(
        "/Users/agnes/Repos/FireflyCorner/claude-docs/farm-intelligence-whitepaper.pdf",
        pagesize=A4,
        leftMargin=22*mm, rightMargin=22*mm,
        topMargin=20*mm, bottomMargin=20*mm,
    )

    story = []

    # ── COVER ──────────────────────────────────────────
    story.append(Spacer(1, 30*mm))
    story.append(Paragraph("Building Farm Intelligence", styles["WPTitle"]))
    story.append(Paragraph(
        "How Five Layers of Cooperative Intelligence<br/>"
        "Connect AI, Humans, and a Living Farm",
        styles["WPSubtitle"]
    ))
    story.append(Spacer(1, 8*mm))
    story.append(hr())
    story.append(Spacer(1, 6*mm))
    story.append(Paragraph(
        "Agnes Schliebitz &amp; Claude  |  Firefly Corner Farm  |  April 2026",
        styles["WPAuthor"]
    ))
    story.append(Spacer(1, 15*mm))
    story.append(body(
        "This paper describes the intelligence architecture we built for Firefly Corner Farm "
        "on April 4, 2026. It is not theoretical. Every concept described here is running in "
        "production, tested against real farm data, and was validated the same day it was built "
        "by processing a WWOOFer's field walk transcript into structured, cross-referenced "
        "farmOS data."
    ))
    story.append(spacer(4))
    story.append(body(
        "The architecture is based on the Valliance AI \"Five Layers of Enterprise Intelligence\" "
        "framework, adapted for a 25-hectare regenerative farm in rural NSW where connectivity is "
        "limited, knowledge walks out the door with every departing volunteer, and the AI system "
        "must work in genuine partnership with humans who have dirt under their fingernails."
    ))
    story.append(spacer(4))
    story.append(body(
        "The pattern is portable. While every example here is from our farm, the same architecture "
        "applies to any domain where entities have lifecycles and humans and AI cooperate to "
        "observe, decide, and act."
    ))

    story.append(PageBreak())

    # ── 1. THE PROBLEM ─────────────────────────────────
    story.append(h1("1. The Problem: Data Without Meaning"))
    story.append(body(
        "By April 2026, the farm had accumulated significant digital infrastructure. farmOS tracked "
        "700+ plant assets, 1,260+ observation logs, 272 plant species, and 93 land sections across "
        "two paddocks and a nursery. Six Google Sheets captured field observations, seed bank "
        "inventory, harvest records, team session summaries, and knowledge base entries. Four team "
        "members each had their own Claude AI assistant connected to the farm's MCP server with "
        "30 tools."
    ))
    story.append(spacer(2))
    story.append(body(
        "And yet, when anyone asked \"How is P2R3 doing?\" the answer was different every time."
    ))
    story.append(spacer(2))
    story.append(body(
        "Each Claude session would read the project context file, query five separate systems, "
        "improvise its own definitions of \"healthy\" and \"at risk,\" and produce a unique, "
        "session-specific response. The data accumulated. The intelligence did not compound. "
        "The same questions got re-answered from scratch because there was no shared understanding "
        "of what the data meant."
    ))
    story.append(spacer(2))
    story.append(body(
        "Worse, when our agronomist Claire left the farm in March, her decision rationale "
        "left with her. Why were tagasaste trees planted next to macadamias? Why was that "
        "section renovated in spring instead of autumn? The farmOS logs recorded what happened. "
        "Nobody recorded why."
    ))

    # ── 2. THE FRAMEWORK ──────────────────────────────
    story.append(h1("2. The Framework: Five Sequential Layers"))
    story.append(body(
        "The Valliance AI article \"Five Layers of Enterprise Intelligence\" provided the "
        "diagnosis. It argues that five concepts commonly treated as interchangeable are "
        "actually sequential and load-bearing. Skip a layer and the architecture fails "
        "structurally, not gracefully."
    ))
    story.append(spacer(3))

    table_data = [
        ["Layer", "Question", "What It Provides"],
        ["1. Ontology", "What exists?", "Entity types, relationships, constraints. The empty blueprint."],
        ["2. Knowledge Graph", "What is true?", "Real entities populating the ontology. Facts."],
        ["3. Semantic Layer", "What does it mean?", "Governed metrics and canonical definitions."],
        ["4. Context Graph", "What did we do?", "Decision traces. Not just what, but why."],
        ["5. Trust Layer", "Should we have?", "Provenance, confidence, governance."],
    ]
    story.append(make_table(table_data, col_widths=[30*mm, 35*mm, 95*mm]))
    story.append(caption("The five layers of intelligence, each answering a question the previous cannot."))

    story.append(body(
        "Applied to the farm, the diagnosis was immediate. We had a working knowledge graph "
        "(Layer 2 \u2014 farmOS full of data), an embryonic context graph (Layer 4 \u2014 team memory "
        "capturing session summaries), and almost nothing else. The ontology was implicit. "
        "The semantic layer was entirely absent. The trust layer was conceptual."
    ))
    story.append(spacer(2))
    story.append(quote(
        "\"Without a semantic layer, every AI agent that queries organisational data must interpret "
        "the knowledge graph on its own terms. The result: different agents produce different "
        "answers to the same question.\""
    ))
    story.append(caption("Valliance AI, \"Five Layers of Enterprise Intelligence\""))

    # ── 3. WHAT WE BUILT ──────────────────────────────
    story.append(h1("3. What We Built in One Day"))

    story.append(h2("Layer 1: The Farm Ontology"))
    story.append(body(
        "We created farm_ontology.yaml \u2014 a structured, human-readable specification of "
        "everything that exists at Firefly Corner. Not code. Not a database schema. "
        "A document that Claire or a future farm manager can read and say \"yes, this is "
        "how our farm works\" or \"no, we have added something new.\""
    ))
    story.append(spacer(2))
    story.append(bold("18 entity types across two categories:"))
    story.append(bullet(
        "<b>farmOS-backed</b>: Plant, Species, Section, Row, Paddock, Water Asset, "
        "Structure, Equipment, Compost Bay, Seed, Material"
    ))
    story.append(bullet(
        "<b>Non-farmOS</b>: Actor (the humans), Task, Observation, Knowledge Entry, "
        "Supplier, Harvest, Session"
    ))
    story.append(spacer(2))
    story.append(body(
        "The ontology includes an evolution protocol: when a new concept appears in a "
        "transcript, CSV, or observation, there is a principled five-step process "
        "(classify, assess, formalize, propagate, validate) for deciding whether it becomes "
        "a new entity type, a new relationship, or an attribute of something that already exists."
    ))

    story.append(h2("Layer 3: The Semantic Layer"))
    story.append(body(
        "This is the critical missing piece we filled. farm_semantics.yaml defines canonical "
        "metrics with governed thresholds:"
    ))
    story.append(spacer(2))

    sem_data = [
        ["Metric", "Definition", "Good", "Concerning"],
        ["Strata Coverage", "Fraction of canopy layers with living plants", "\u2265 75%", "< 50%"],
        ["Survival Rate", "Living plants / total ever planted", "\u2265 70%", "< 50%"],
        ["Activity Recency", "Days since last observation or activity", "\u2264 14 days", "> 30 days"],
        ["Succession Balance", "Pioneer : Secondary : Climax ratio", "Age-appropriate", "Single stage"],
        ["Task Completion", "Completed / created tasks per period", "\u2265 80%", "< 60%"],
    ]
    story.append(make_table(sem_data, col_widths=[32*mm, 55*mm, 30*mm, 30*mm]))
    story.append(caption("Canonical metric definitions from farm_semantics.yaml"))

    story.append(spacer(2))
    story.append(body(
        "The definitions live in a YAML file that humans curate. The code reads the YAML and "
        "computes. When field reality contradicts a threshold, Agnes updates the YAML and every "
        "Claude across the team automatically uses the new values. No code changes. No redeployment."
    ))
    story.append(spacer(2))
    story.append(body(
        "The semantic layer includes feedback loops: when survival rates consistently violate "
        "thresholds for pioneer species, that is a signal to review the ontology (is the "
        "classification correct for this climate?). When transplant readiness predictions fail, "
        "review the definition (is transplant_days accurate for subtropical conditions?)."
    ))

    story.append(h2("The farm_context Tool"))
    story.append(body(
        "The intelligence layers come together in a single MCP tool: farm_context. It cross-references "
        "farmOS, the Knowledge Base, the plant type taxonomy, and team memory in one call, "
        "then applies the semantic layer to return interpreted, governed intelligence."
    ))
    story.append(spacer(2))
    story.append(body(
        "Three query modes:"
    ))
    story.append(bullet(
        "<b>Section</b>: farm_context(section=\"P2R3.15-21\") \u2014 health assessment with strata "
        "coverage, activity recency, succession balance, pending tasks, knowledge gaps"
    ))
    story.append(bullet(
        "<b>Species</b>: farm_context(subject=\"Pigeon Pea\") \u2014 distribution across all "
        "sections, KB coverage, metadata, decision trail"
    ))
    story.append(bullet(
        "<b>Topic</b>: farm_context(topic=\"nursery\") \u2014 domain overview, transplant "
        "readiness, task pipeline health"
    ))
    story.append(spacer(2))
    story.append(body(
        "Every response returns all five layers clearly separated: ontology constraints, "
        "raw facts, semantic interpretation, decision context, and detected gaps. "
        "And critically: a data integrity gate."
    ))

    story.append(PageBreak())

    # ── 4. CATCHING SILENT FAILURES ────────────────────
    story.append(h1("4. Catching What Humans Miss"))

    story.append(h2("The Data Integrity Gate"))
    story.append(body(
        "The farm_context tool cross-references team memory (what people said they did) against "
        "actual farmOS logs (what the system recorded). This is Layer 4 validating Layer 2 \u2014 "
        "the context graph checking the knowledge graph."
    ))
    story.append(spacer(2))
    story.append(body(
        "On the day we built this, we tested it against section P2R4.6-14. The tool immediately "
        "flagged a discrepancy:"
    ))
    story.append(spacer(2))
    story.append(quote(
        "INTEGRITY: James claimed 'Lavender x5 \u2014 P2R4.6-14' (session #89) "
        "but no matching farmOS log found"
    ))
    story.append(spacer(2))
    story.append(body(
        "James had transplanted 5 lavender and 2 geranium into that section on March 24. "
        "His Claude logged the session summary (team memory) including the farmOS changes. "
        "But the actual farmOS API calls had silently failed \u2014 likely a Railway timeout or "
        "stale MCP session. The plants were in the ground. The data was not."
    ))
    story.append(spacer(2))
    story.append(body(
        "Without the integrity gate, this would have remained invisible. The next person to "
        "query P2R4.6-14 would have seen 15 plants instead of 22. Inventory counts would "
        "have been wrong. The QR landing page would have been stale. And nobody would have "
        "known why."
    ))
    story.append(spacer(2))
    story.append(body(
        "The tool's response includes requires_confirmation: true when discrepancies are found. "
        "This tells any Claude on the team: do not trust these facts. Confirm with the human "
        "what actually happened before proceeding."
    ))

    # ── 5. THE REAL TEST ──────────────────────────────
    story.append(h1("5. The Real Test: Maverick's Transcript"))
    story.append(body(
        "The true test came from Maverick, a WWOOFer who had been on the farm for one week. "
        "He walked Paddock 2 Row 5 with his phone recording, narrating what he saw:"
    ))
    story.append(spacer(2))
    story.append(quote(
        "\"I see one sunflower, parsley, wattle plant, some basil, a potato, "
        "lots of basil, a mulberry tree, another tree that I can't identify, "
        "another waddle, another waddle, so that's three waddles total...\""
    ))
    story.append(spacer(2))
    story.append(body(
        "Raw, unstructured, full of phonetic variations (\"waddle\" for wattle), "
        "approximate counts (\"lots of basil\"), and knowledge gaps (\"a tree I can't "
        "identify\"). This is what real farm data looks like before intelligence processes it."
    ))

    story.append(h2("What the Intelligence Layer Produced"))
    story.append(body(
        "Processing the transcript through the system involved:"
    ))
    story.append(bullet(
        "<b>Entity resolution</b>: \"waddle\" \u2192 Wattle - Cootamundra (Baileyana). "
        "\"potato\" \u2192 Sweet Potato (regular potatoes not grown here). "
        "\"long narrow leaves\" \u2192 likely Banagrass."
    ))
    story.append(bullet(
        "<b>Cross-reference via farm_context</b>: P2R5.0-8 has 10 tracked species in farmOS. "
        "Maverick mentioned 9 things. The deltas: Wattle count 1\u21923 (two unlogged), "
        "Mulberry 2\u21923 (one unlogged), plus new Sunflower, Pumpkin, and Jacaranda."
    ))
    story.append(bullet(
        "<b>Source origin tracing</b>: Pumpkin = self-seeded from compost. "
        "Sunflower = likely from winter garden mix James sowed March 31. "
        "Jacaranda = tree species, cannot self-seed \u2014 flagged as possible "
        "unlogged nursery transplant."
    ))
    story.append(bullet(
        "<b>Gap detection</b>: P2R5.8-14 and P2R5.22-29 are \"gap sections\" with zero "
        "farmOS assets but real plants growing. Maverick counted pumpkin, basil, sweet potato, "
        "okra, sunflowers, and trees that were never registered."
    ))
    story.append(bullet(
        "<b>Missing log detection</b>: Tree species in gap sections (mulberry, possible "
        "banagrass, papaya, eucalypt) imply transplanting events that were never logged."
    ))
    story.append(spacer(3))
    story.append(bold("Result: 9 new plant assets created, 2 inventory counts updated, "
                      "5 pending review tasks generated for James."))
    story.append(spacer(2))
    story.append(body(
        "But the most important output was the knowledge gap detection. Maverick could not "
        "identify native trees that farmOS knew were there: Tallowood, Prickly-leaved Paperbark, "
        "Rough Barked Apple. He described \"a tree I can't identify\" while the system knew "
        "exactly what it was. This led directly to the design of species photos on QR landing "
        "pages and PlantNet AI identification \u2014 closing the loop between what the system "
        "knows and what the human in the field can see."
    ))

    story.append(PageBreak())

    # ── 6. THE COMPOUNDING TEST ────────────────────────
    story.append(h1("6. The Compounding Intelligence Test"))
    story.append(body(
        "The Valliance article argues that intelligence should compound, not just accumulate. "
        "Here is the test:"
    ))
    story.append(spacer(2))
    story.append(bold(
        "Ask \"How is the farm doing?\" in session 1 and again in session 50."
    ))
    story.append(spacer(2))
    story.append(bullet(
        "<b>If compounding</b>: Session 50 is faster, more precise, uses established "
        "definitions, references past decisions, identifies patterns session 1 could not see."
    ))
    story.append(bullet(
        "<b>If not compounding</b>: Each session reads the project context, queries five "
        "systems, improvises definitions, produces a unique response. Data grows. "
        "Intelligence does not."
    ))
    story.append(spacer(3))
    story.append(body(
        "Before April 4, the farm was in the second state. After: governed metrics mean every "
        "Claude produces the same health assessment. The semantic layer locks in meaning. "
        "The context graph locks in decisions. The integrity gate catches failures. "
        "And the process-transcript skill means any future transcript gets the same quality "
        "treatment Maverick's received \u2014 without anyone having to re-learn the workflow."
    ))

    # ── 7. WHAT COMES NEXT ─────────────────────────────
    story.append(h1("7. What Comes Next"))

    story.append(h2("Species Photos + AI Plant Identification"))
    story.append(body(
        "Maverick's knowledge gap \u2014 unable to identify native trees \u2014 exposed the need "
        "for visual species references on QR landing pages. The design combines farm-taken photos "
        "(from observation submissions, already captured but stuck in Google Drive) with PlantNet "
        "AI identification as a fallback. A WWOOFer takes a photo of an unknown plant, PlantNet "
        "identifies it against 78,000 species, and the result is matched against our farm's "
        "272-species taxonomy. The farm's own photo appears alongside the AI match for human "
        "confirmation."
    ))

    story.append(h2("Graph Visualization"))
    story.append(body(
        "The ontology and live data need a visual interface \u2014 a way to see the farm's "
        "entity graph, navigate relationships, and spot patterns that tables cannot show. "
        "We have selected Cytoscape.js for an interactive graph page on our existing GitHub Pages "
        "site, with nodes colored by semantic health status and TheBrain-style focus navigation."
    ))

    story.append(h2("Interaction Intelligence"))
    story.append(body(
        "Every human-AI conversation is a signal. What questions people ask, what data they pull "
        "repeatedly, whether answers lead to actions or get ignored \u2014 these patterns reveal "
        "where the system works and where it fails. High correction rates signal semantic layer "
        "gaps. Recurring questions signal missing persistence. The conversations themselves "
        "become the learning mechanism that the five-layer framework identifies as essential "
        "but leaves unnamed."
    ))

    story.append(PageBreak())

    # ── 8. THE PORTABLE PATTERN ────────────────────────
    story.append(h1("8. The Portable Pattern"))
    story.append(body(
        "This architecture is not farm-specific. The abstract pattern applies wherever entities "
        "have lifecycles and humans and AI cooperate:"
    ))
    story.append(spacer(3))

    port_data = [
        ["Abstract", "Farm", "Commerce (COIP)"],
        ["Subject (type)", "Species", "Product"],
        ["Instance", "Plant", "Order"],
        ["Location", "Section", "Warehouse"],
        ["Task", "Pending activity", "Action Required"],
        ["Observation", "Field report", "Customer interaction"],
        ["Knowledge", "Tutorial / SOP", "Resolution playbook"],
        ["Actor", "Claire, Maverick", "CSR, Customer, Agent"],
        ["Session", "Team memory", "Conversation thread"],
    ]
    story.append(make_table(port_data, col_widths=[35*mm, 50*mm, 55*mm]))
    story.append(caption("The same five-layer pattern, instantiated for two different domains."))

    story.append(spacer(3))
    story.append(body(
        "The core insight is simple: intelligence compounds when the system tracks not just "
        "what happened, but what it means and why decisions were made. The five layers "
        "provide the structure. The human-AI cooperation provides the energy. "
        "And the farm \u2014 with its daily cycles of observation, decision, and action \u2014 "
        "provides the proof."
    ))

    story.append(spacer(10))
    story.append(hr())
    story.append(spacer(4))
    story.append(Paragraph(
        "Firefly Corner Farm  \u00b7  Krambach, NSW  \u00b7  April 2026",
        styles["WPFooter"]
    ))
    story.append(Paragraph(
        "Built with Claude Code  \u00b7  farmOS  \u00b7  Syntropic Agroforestry",
        styles["WPFooter"]
    ))
    story.append(spacer(3))
    story.append(Paragraph(
        "300 tests. 31 tools. 18 entity types. 5 layers. 1 day.",
        styles["WPFooter"]
    ))

    doc.build(story)
    print("Whitepaper generated: claude-docs/farm-intelligence-whitepaper.pdf")


if __name__ == "__main__":
    build_document()
