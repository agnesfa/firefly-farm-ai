#!/usr/bin/env python3
"""Generate a PDF version of the team briefing document."""

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.colors import HexColor
from reportlab.lib.units import mm, cm
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak,
    HRFlowable, ListFlowable, ListItem, Table, TableStyle
)

# Colors
FOREST_GREEN = HexColor("#2d5016")
DARK_GREEN = HexColor("#1a3a0a")
MID_GREEN = HexColor("#4a7c29")
LIGHT_GREEN = HexColor("#e8f5e0")
ACCENT = HexColor("#6b9e3c")
GREY = HexColor("#555555")
LIGHT_GREY = HexColor("#cccccc")

WIDTH, HEIGHT = A4

def build_styles():
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        "DocTitle", fontName="Helvetica-Bold", fontSize=22,
        textColor=FOREST_GREEN, spaceAfter=4, alignment=TA_CENTER
    ))
    styles.add(ParagraphStyle(
        "DocSubtitle", fontName="Helvetica-Oblique", fontSize=11,
        textColor=GREY, spaceAfter=20, alignment=TA_CENTER, leading=15
    ))
    styles.add(ParagraphStyle(
        "H2", fontName="Helvetica-Bold", fontSize=16,
        textColor=FOREST_GREEN, spaceBefore=20, spaceAfter=8
    ))
    styles.add(ParagraphStyle(
        "H3", fontName="Helvetica-Bold", fontSize=13,
        textColor=MID_GREEN, spaceBefore=14, spaceAfter=6
    ))
    styles.add(ParagraphStyle(
        "Body", fontName="Helvetica", fontSize=10.5,
        textColor=HexColor("#222222"), spaceAfter=6,
        leading=15, alignment=TA_JUSTIFY
    ))
    styles.add(ParagraphStyle(
        "BodyBold", fontName="Helvetica-Bold", fontSize=10.5,
        textColor=HexColor("#222222"), spaceAfter=6, leading=15
    ))
    styles.add(ParagraphStyle(
        "BulletCustom", fontName="Helvetica", fontSize=10.5,
        textColor=HexColor("#222222"), spaceAfter=3,
        leading=14, leftIndent=18, bulletIndent=6
    ))
    styles.add(ParagraphStyle(
        "NumberedItem", fontName="Helvetica", fontSize=10.5,
        textColor=HexColor("#222222"), spaceAfter=5,
        leading=15, leftIndent=18
    ))
    styles.add(ParagraphStyle(
        "Quote", fontName="Helvetica-Oblique", fontSize=10.5,
        textColor=GREY, spaceAfter=4, leading=14, leftIndent=12
    ))
    styles.add(ParagraphStyle(
        "CodeBlock", fontName="Courier", fontSize=9,
        textColor=HexColor("#333333"), spaceAfter=8,
        leading=13, leftIndent=12, backColor=HexColor("#f5f5f5")
    ))
    styles.add(ParagraphStyle(
        "Callout", fontName="Helvetica-Bold", fontSize=11,
        textColor=FOREST_GREEN, spaceAfter=8, spaceBefore=8,
        leading=15, alignment=TA_CENTER
    ))
    styles.add(ParagraphStyle(
        "RoleName", fontName="Helvetica-Bold", fontSize=13,
        textColor=DARK_GREEN, spaceBefore=14, spaceAfter=4
    ))
    styles.add(ParagraphStyle(
        "RoleDesc", fontName="Helvetica-Oblique", fontSize=10.5,
        textColor=GREY, spaceAfter=6, leading=14
    ))
    styles.add(ParagraphStyle(
        "Footer", fontName="Helvetica", fontSize=8,
        textColor=LIGHT_GREY, alignment=TA_CENTER
    ))
    return styles


def hr():
    return HRFlowable(width="100%", thickness=0.5, color=LIGHT_GREEN, spaceAfter=12, spaceBefore=8)


def bullet(text, styles):
    return Paragraph(f"<bullet>&bull;</bullet> {text}", styles["BulletCustom"])


def build_pdf(output_path):
    styles = build_styles()

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=2.2*cm, rightMargin=2.2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
        title="Firefly Corner - Farm Intelligence Team Briefing",
        author="Firefly Corner Farm"
    )

    story = []

    # === TITLE ===
    story.append(Spacer(1, 30))
    story.append(Paragraph("Firefly Corner", styles["DocTitle"]))
    story.append(Paragraph("Farm Intelligence Team Briefing", styles["H2"]))
    story[-1].style = ParagraphStyle("SubTitle", parent=styles["H2"], alignment=TA_CENTER, spaceAfter=12)
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "Read this document to understand how we work together, what the system does,<br/>"
        "and how your interactions with Claude make the farm smarter every day.",
        styles["DocSubtitle"]
    ))
    story.append(hr())

    # === WHAT WE'VE BUILT ===
    story.append(Paragraph("What We've Built", styles["H2"]))
    story.append(Paragraph(
        "Every person at Firefly Corner now has their own Claude \u2014 an AI assistant connected to "
        "farmOS (our farm database) and to each other through a shared memory system.",
        styles["Body"]
    ))
    story.append(Paragraph(
        'When you tell your Claude something \u2014 "I planted 5 tagasaste in P2R3 today" or '
        '"the pigeon peas in Row 2 look frost-damaged" \u2014 it doesn\'t just listen. It records '
        "that knowledge in farmOS, where it becomes part of the farm's permanent intelligence. "
        "And through the Team Memory, everyone else's Claude can see what you did.",
        styles["Body"]
    ))
    story.append(Spacer(1, 4))
    story.append(Paragraph("<b>The system has three layers:</b>", styles["Body"]))
    story.append(Paragraph(
        "<b>1. farmOS</b> \u2014 the source of truth. Every plant, every observation, every activity "
        "is recorded here. Your Claude reads from and writes to farmOS on your behalf.",
        styles["NumberedItem"]
    ))
    story.append(Paragraph(
        "<b>2. Observation Sheet</b> \u2014 field workers submit observations via QR code pages on "
        "section poles. These land in a Google Sheet for review before being imported to farmOS.",
        styles["NumberedItem"]
    ))
    story.append(Paragraph(
        "<b>3. Team Memory</b> \u2014 a shared log where each person's Claude writes session summaries. "
        "This is how the team stays in sync without meetings.",
        styles["NumberedItem"]
    ))

    story.append(hr())

    # === THE KNOWLEDGE LOOP ===
    story.append(Paragraph("The Knowledge Loop", styles["H2"]))
    story.append(Paragraph(
        "This is the core idea: every interaction with the farm and with Claude makes the system smarter.",
        styles["Body"]
    ))
    story.append(Spacer(1, 4))

    loop_data = [
        ["You work in the field / nursery / seed bank"],
        ["\u2193"],
        ["You tell Claude what happened (or scan a QR code)"],
        ["\u2193"],
        ["Claude records it in farmOS + writes a session summary"],
        ["\u2193"],
        ["Other team members' Claudes can read what you did"],
        ["\u2193"],
        ["The farm intelligence grows \u2014 better decisions next time"],
        ["\u2193"],
        ["You benefit from what everyone else has recorded"],
    ]
    loop_table = Table(loop_data, colWidths=[380])
    loop_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (-1, -1), GREY),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("BACKGROUND", (0, 0), (0, 0), LIGHT_GREEN),
        ("BACKGROUND", (0, 2), (0, 2), LIGHT_GREEN),
        ("BACKGROUND", (0, 4), (0, 4), LIGHT_GREEN),
        ("BACKGROUND", (0, 6), (0, 6), LIGHT_GREEN),
        ("BACKGROUND", (0, 8), (0, 8), LIGHT_GREEN),
        ("BACKGROUND", (0, 10), (0, 10), LIGHT_GREEN),
    ]))
    story.append(loop_table)
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "<b>The more you tell Claude, the smarter the farm gets.</b> Not just WHAT happened, but WHY. "
        '"I planted tagasaste here because the soil needs nitrogen" is far more valuable than just '
        '"I planted tagasaste."',
        styles["Callout"]
    ))

    story.append(hr())

    # === HOW TO WORK WITH YOUR CLAUDE ===
    story.append(Paragraph("How to Work With Your Claude", styles["H2"]))

    story.append(Paragraph("Talk naturally", styles["H3"]))
    story.append(Paragraph(
        "You don't need special commands. Just tell Claude what you did, what you see, or what you need:",
        styles["Body"]
    ))
    for ex in [
        '"I planted 12 tagasaste in P2R3.9-14 today as nitrogen fixers"',
        '"The pigeon peas in P2R2.3-7 \u2014 3 have died, probably frost"',
        '"What\'s planted in Row 3?"',
        '"Show me what the team has been doing this week"',
        '"I counted the basil seeds \u2014 about 50g left, packet from Eden Seeds 2024"',
    ]:
        story.append(bullet(f"<i>{ex}</i>", styles))

    story.append(Paragraph("Include the WHY", styles["H3"]))
    story.append(Paragraph(
        "Claude captures what you say in farmOS notes. The reasoning is gold:",
        styles["Body"]
    ))
    for reason in [
        '"Chose tagasaste over pigeon pea because it handles frost better" \u2192 future decision-making',
        '"This section gets waterlogged in winter" \u2192 infrastructure knowledge',
        '"Seeds look degraded, low germination expected" \u2192 quality intelligence',
    ]:
        story.append(bullet(f"<i>{reason}</i>", styles))

    story.append(Paragraph("Session summaries", styles["H3"]))
    story.append(Paragraph(
        "At the end of a work session, your Claude should write a summary of what happened. "
        'This goes to the Team Memory where everyone can see it. If your Claude doesn\'t do it '
        'automatically, just say: <b>"Write a session summary of what we did."</b>',
        styles["Body"]
    ))
    story.append(Paragraph("The summary captures:", styles["Body"]))
    for item in [
        "<b>Topics</b> \u2014 what you worked on",
        "<b>Decisions</b> \u2014 choices made and why",
        "<b>farmOS changes</b> \u2014 what was recorded",
        "<b>Questions</b> \u2014 anything unresolved or needing attention",
    ]:
        story.append(bullet(item, styles))

    story.append(Paragraph("Check what others did", styles["H3"]))
    story.append(Paragraph("You can ask:", styles["Body"]))
    for cmd in [
        '"What has the team been working on?" \u2192 shows recent summaries from everyone',
        '"What did Claire do yesterday?" \u2192 filtered to one person',
        '"Search team memory for seed bank" \u2192 find past decisions on a topic',
    ]:
        story.append(bullet(f"<i>{cmd}</i>", styles))

    story.append(hr())

    # === QR CODE SYSTEM ===
    story.append(Paragraph("The QR Code System", styles["H2"]))
    story.append(Paragraph(
        "Every section pole in Paddock 2 has a QR code. Scanning it shows:",
        styles["Body"]
    ))
    story.append(bullet("<b>What's planted</b> \u2014 species, counts, strata, botanical names", styles))
    story.append(bullet("<b>Record observation</b> button \u2014 submit field observations", styles))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "<b>Anyone can use the QR pages</b> \u2014 no login needed. Observations go to the Google Sheet "
        "for review. Claire reviews them for accuracy, then they get imported to farmOS.",
        styles["Body"]
    ))

    story.append(hr())

    # === WHAT'S HAPPENING NOW ===
    story.append(Paragraph("What's Happening Now (March 2026)", styles["H2"]))
    story.append(Paragraph("Three parallel tracks running simultaneously:", styles["Body"]))

    story.append(Paragraph("1. P2 Autumn Planting (Claire leads)", styles["H3"]))
    story.append(Paragraph(
        "New trees and green manure mixes going into Paddock 2 for autumn/winter. Claire uses QR "
        "observe pages and Claude to record everything. New species get added to the plant type "
        "database as needed.",
        styles["Body"]
    ))

    story.append(Paragraph("2. Seed Bank Inventory (Olivier leads)", styles["H3"]))
    story.append(Paragraph(
        "Complete count of all seed packets \u2014 species, quantities, conditions, sources. This data "
        "will become farmOS Seed assets, enabling the full seed-to-field lifecycle tracking.",
        styles["Body"]
    ))

    story.append(Paragraph("3. Operational Flow Design (James leads)", styles["H3"]))
    story.append(Paragraph(
        "James reviews what Claire and Olivier are doing and designs repeatable workflows. The goal: "
        "when new WWOOFers arrive after March 22, they can follow these flows without expert guidance.",
        styles["Body"]
    ))

    story.append(hr())

    # === THE ROLES ===
    story.append(Paragraph("The Roles", styles["H2"]))

    # Agnes
    story.append(Paragraph("Agnes \u2014 The Architect", styles["RoleName"]))
    story.append(Paragraph(
        "Agnes designs and builds the technical system. She works with Claude Code (the developer tool) "
        "to build scripts, MCP servers, and data pipelines. She doesn't work in the field \u2014 she "
        "makes sure the system captures what everyone else does.",
        styles["Body"]
    ))
    story.append(Paragraph(
        "<b>Agnes's Claude</b> (Claude Code) orchestrates the other Claudes' understanding. When your "
        "Claude flags a question or a missing feature in a session summary, Agnes's Claude reads it "
        "and Agnes builds what's needed.",
        styles["Body"]
    ))
    story.append(Paragraph(
        "<b>How to signal Agnes:</b> When something doesn't work, is missing, or could be better \u2014 "
        "tell your Claude. It goes into the session summary's \"questions\" field. Agnes will see it "
        "and act on it. You don't need to track her down.",
        styles["Body"]
    ))

    # Claire
    story.append(Paragraph("Claire \u2014 The Field Expert", styles["RoleName"]))
    story.append(Paragraph(
        "Claire is the farm's agronomic brain. She knows which species work together, what the soil "
        "needs, which plants are struggling and why. She designs the syntropic rows and manages "
        "planting campaigns.",
        styles["Body"]
    ))
    story.append(Paragraph(
        "<b>Claire's mission with Claude:</b> Capture field knowledge. Every observation, every planting "
        "decision, every piece of expertise that lives in her head \u2014 get it into the system. After "
        "March 22, this knowledge needs to be accessible to whoever is managing the farm.",
        styles["Body"]
    ))
    story.append(Paragraph("<b>What Claire does:</b>", styles["Body"]))
    for item in [
        "Records plantings and observations via QR pages and Claude chat",
        "Adds new plant types when she introduces species",
        "Reviews field observations from the Google Sheet",
        "Shares agronomic reasoning with her Claude (the WHY behind decisions)",
    ]:
        story.append(bullet(item, styles))

    # James
    story.append(Paragraph("James \u2014 The Knowledge Crystallizer", styles["RoleName"]))
    story.append(Paragraph(
        "James owns the farm's continuity. He's responsible for making sure the systems work for "
        "everyone \u2014 especially WWOOFers who arrive knowing nothing about this specific farm.",
        styles["Body"]
    ))
    story.append(Paragraph(
        '<b>James\'s mission with Claude:</b> Design operational flows. Take what Claire and Olivier '
        'produce and ask: "How does a new person follow this? What instructions do they need? What '
        'could go wrong?" James\'s Claude helps him read team activity, review data quality, and '
        "document workflows.",
        styles["Body"]
    ))
    story.append(Paragraph("<b>What James does:</b>", styles["Body"]))
    for item in [
        "Reads team memory daily \u2014 stays informed about what Claire and Olivier are doing",
        "Designs the seed bank \u2192 nursery \u2192 paddock operational flow",
        "Reviews observation data quality (are species names correct? are counts plausible?)",
        "Documents decisions and workflows that need to survive after March 22",
        "Thinks about WWOOFer onboarding and autonomy",
    ]:
        story.append(bullet(item, styles))

    # Olivier
    story.append(Paragraph("Olivier \u2014 The Practical Reporter", styles["RoleName"]))
    story.append(Paragraph(
        "Olivier handles compost, cooking, and is currently leading the seed bank inventory. "
        "His role is hands-on and precise.",
        styles["Body"]
    ))
    story.append(Paragraph(
        "<b>Olivier's mission with Claude:</b> Record accurately and report clearly. Every seed packet "
        "counted, every compost bay monitored \u2014 structured data that James can review and design "
        "workflows around.",
        styles["Body"]
    ))
    story.append(Paragraph("<b>What Olivier does:</b>", styles["Body"]))
    for item in [
        "Counts and records seed bank inventory (species, quantities, conditions, sources)",
        "Logs compost activities (turning, temperature, maturity)",
        "Supports Claire in the field and nursery as directed",
        "Writes session summaries so James knows what was counted/done",
    ]:
        story.append(bullet(item, styles))

    story.append(hr())

    # === KEY CONCEPTS ===
    story.append(Paragraph("Key Concepts (Quick Reference)", styles["H2"]))

    story.append(Paragraph("Section IDs", styles["H3"]))
    story.append(Paragraph(
        "Format: <b>P2R3.14-21</b> = Paddock 2, Row 3, from 14m to 21m mark.",
        styles["Body"]
    ))

    story.append(Paragraph("Plant Strata (height layers)", styles["H3"]))
    strata_data = [
        ["Strata", "Height", "Examples"],
        ["Emergent", "20m+", "Forest Red Gum, Tallowood, Ice Cream Bean"],
        ["High", "8\u201320m", "Macadamia, Apple, Pigeon Pea, Tagasaste"],
        ["Medium", "2\u20138m", "Jaboticaba, Tea Tree, Lemon, Chilli"],
        ["Low", "0\u20132m", "Comfrey, Sweet Potato, Turmeric, Yarrow"],
    ]
    strata_table = Table(strata_data, colWidths=[70, 60, 320])
    strata_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BACKGROUND", (0, 0), (-1, 0), FOREST_GREEN),
        ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#ffffff")),
        ("BACKGROUND", (0, 1), (-1, -1), LIGHT_GREEN),
        ("TEXTCOLOR", (0, 1), (-1, -1), HexColor("#222222")),
        ("GRID", (0, 0), (-1, -1), 0.5, LIGHT_GREY),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(strata_table)
    story.append(Spacer(1, 8))

    story.append(Paragraph("Succession (lifecycle role)", styles["H3"]))
    for item in [
        "<b>Pioneer</b> (0\u20135yr): Fast growth, nitrogen fixing, biomass \u2014 designed to die and make way. Pigeon pea losses are EXPECTED.",
        "<b>Secondary</b> (3\u201315yr): Fill canopy as pioneers decline",
        "<b>Climax</b> (15+yr): Permanent forest structure",
    ]:
        story.append(bullet(item, styles))

    story.append(Paragraph("Important rules", styles["H3"]))
    for rule in [
        "farmOS is always the source of truth",
        "Include the WHY, not just the WHAT",
        "Dead plants stay as records \u2014 never deleted",
        "When unsure about species names, ask Claude to search the taxonomy",
        "When unsure about agronomic decisions, Claire decides",
        "When unsure about workflow design, James decides",
        "When something technical doesn't work, flag it for Agnes",
    ]:
        story.append(bullet(rule, styles))

    story.append(hr())

    # === MARCH 22 DEADLINE ===
    story.append(Paragraph("The March 22 Deadline", styles["H2"]))
    story.append(Paragraph(
        "Claire and Olivier leave on March 22. Everything they know about this farm needs to be "
        "captured before then \u2014 in farmOS, in the Team Memory, and in the workflows James designs. "
        "Every session summary, every observation, every piece of reasoning matters.",
        styles["Body"]
    ))
    story.append(Paragraph(
        "This isn't about creating perfect documentation. It's about making sure the farm intelligence "
        "has enough knowledge that James (with new WWOOFers and Claude) can keep the farm's operations "
        "running and growing.",
        styles["Body"]
    ))
    story.append(Spacer(1, 12))
    story.append(Paragraph(
        "<b>The farm intelligence is only as good as what you feed it. Feed it well.</b>",
        styles["Callout"]
    ))

    # Footer
    story.append(Spacer(1, 30))
    story.append(Paragraph("Firefly Corner Farm \u2014 March 2026", styles["Footer"]))

    doc.build(story)
    return output_path


if __name__ == "__main__":
    output = "/Users/agnes/Repos/FireflyCorner/claude-docs/team-briefing.pdf"
    build_pdf(output)
    print(f"PDF generated: {output}")
