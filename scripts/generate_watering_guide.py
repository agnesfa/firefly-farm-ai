#!/usr/bin/env python3
"""Generate a printable nursery watering one-pager for Firefly Corner Farm.

Combines Olivier's watering zones/levels with actual farmOS inventory data.
Output: A4 landscape, fills the page with balanced 3-column layout.
"""

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, white, black
from reportlab.pdfgen import canvas

# --- Colors ---
FOREST_GREEN = HexColor("#2d5016")
DARK_GREEN = HexColor("#1a3409")
LIGHT_GREEN = HexColor("#e8f5e0")
ACCENT_GREEN = HexColor("#6b9e3c")
WARM_AMBER = HexColor("#b8860b")
MED_GREY = HexColor("#888888")
LIGHT_BORDER = HexColor("#d8e4ce")
RED_ALERT = HexColor("#c0392b")
ZONE_BG = HexColor("#fafdf7")

# Water level colors
HIGH_COLOR = HexColor("#2980b9")
MEDIUM_COLOR = HexColor("#27ae60")
LOW_COLOR = HexColor("#e67e22")
MONITOR_COLOR = HexColor("#7f8c8d")

# --- Nursery Zones with farmOS inventory (March 30, 2026) ---
ZONES = [
    {
        "name": "SHELVING I  \u2014  Seedlings & Young Plants",
        "level": "HIGH",
        "level_color": HIGH_COLOR,
        "passes": "3 passes",
        "sections": [
            ("SH1-1", "Avocado (23)"),
            ("SH1-2", "Cabbage Red (16), Cabbage Savoy (16), Leek (10), Chilli Bird Eye (23), Chilli Cayenne (26), Finger Lime (1)"),
            ("SH1-3", "Black She-oak (10), Capsicum Red (23), Mango (9), Onion (28), Pigeon Pea (56), Spring Onion (28), Tagasaste (1)"),
            ("SH1-4", "Lemon (10), Papaya (9), Passionfruit (78)"),
        ],
        "total": 367,
        "note": "Small pots dry out fast in heat \u2014 prioritise on hot days.",
    },
    {
        "name": "SHELVING II  \u2014  Herbs & Berries",
        "level": "HIGH",
        "level_color": HIGH_COLOR,
        "passes": "3 passes",
        "sections": [
            ("SH2-1", "Mint (9)"),
            ("SH2-2", "Basil Thai (7), Blueberry (21), Lemon Balm (15), Mint (21)"),
            ("SH2-3", "Lavender (24), Oregano (4), Grape Vine (4), Rosemary (9), Thyme (1)"),
        ],
        "total": 115,
        "note": "Mint and blueberry love moisture.",
    },
    {
        "name": "SHELVING III  \u2014  Fruit Tree Cuttings",
        "level": "MEDIUM",
        "level_color": MEDIUM_COLOR,
        "passes": "2 passes",
        "sections": [
            ("SH3-1", "Lemon (90)"),
            ("SH3-2", "Melaleuca (2), Peach (3), Pear Nashi (4), Pear Williams (6), Apple (20), Guava Strawberry (3)"),
            ("SH3-3", "Apple (12), Guava Hawaiian (10)"),
        ],
        "total": 150,
        "note": "Established roots \u2014 less water needed.",
    },
    {
        "name": "GROUND RIGHT  \u2014  Pre-transplant Staging",
        "level": "MEDIUM",
        "level_color": MEDIUM_COLOR,
        "passes": "2 passes",
        "sections": [
            (None, "Rosemary (8), Aloe Vera (15), Lavender (35), Prickly Pear (1), Tomato (1), Turmeric (1), Geranium (1), Ice Cream Bean (2), Okinawa Spinach (5)"),
        ],
        "total": 69,
        "note": "Ready-to-plant stock.",
    },
    {
        "name": "GROUND LEFT",
        "level": "MEDIUM",
        "level_color": MEDIUM_COLOR,
        "passes": "2 passes",
        "sections": [
            (None, "Geranium (5), Lemongrass (14)"),
        ],
        "total": 19,
        "note": "",
    },
    {
        "name": "BACK ZONE  \u2014  Hardy Cuttings & Roots",
        "level": "LOW",
        "level_color": LOW_COLOR,
        "passes": "1 pass",
        "sections": [
            (None, "Tansy (150), Banagrass (56), Quince (36), Comfrey (24), Sweet Potato (21), Rosemary (15), Basil Perennial (10), Olive (8), Nettle (6), Lavender (5), Sugar Cane (5), Finger Lime (2), Aloe Vera (1), Vacoa (1)"),
        ],
        "total": 340,
        "note": "Drought-tolerant species. Don\u2019t overwater.",
    },
    {
        "name": "THE HILL  \u2014  Sandy Free-draining",
        "level": "2x/WEEK",
        "level_color": MONITOR_COLOR,
        "passes": "15\u201320 min hose",
        "sections": [
            (None, "Geranium (45), Banagrass (12)"),
        ],
        "total": 57,
        "note": "Use extended hose. Sandy soil drains fast.",
    },
]


def wrap_text(c, text, font, size, max_width):
    """Word-wrap comma-separated text. Returns list of lines."""
    c.setFont(font, size)
    words = text.split(", ")
    lines = []
    current = ""
    for word in words:
        test = f"{current}, {word}" if current else word
        if c.stringWidth(test, font, size) > max_width and current:
            lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)
    return lines


def draw_zone_block(c, zone, x, y, block_width, font_size=6.0, line_h=3.3*mm):
    """Draw a single zone block. Returns total height consumed."""
    header_h = 6 * mm
    padding = 2.2 * mm

    # Pre-calculate content
    has_sub = any(sec_id is not None for sec_id, _ in zone["sections"])
    section_data = []
    total_lines = 0
    for sec_id, text in zone["sections"]:
        text_width = block_width - (18 * mm if has_sub and sec_id else 6 * mm)
        lines = wrap_text(c, text, "Helvetica", font_size, text_width)
        section_data.append((sec_id, lines))
        total_lines += len(lines)

    note_h = (line_h + 1 * mm) if zone["note"] else 0
    total_h = header_h + padding + (total_lines * line_h) + note_h + 2 * mm

    # Content background with border
    c.setFillColor(ZONE_BG)
    c.setStrokeColor(LIGHT_BORDER)
    c.setLineWidth(0.4)
    body_h = total_h - header_h
    c.roundRect(x, y - total_h, block_width, body_h, 0, fill=1, stroke=1)

    # Header bar — color-coded by water level
    level_color = zone["level_color"]
    c.setFillColor(level_color)
    c.roundRect(x, y - header_h, block_width, header_h, 2 * mm, fill=1, stroke=0)
    c.rect(x, y - header_h, block_width, 2 * mm, fill=1, stroke=0)
    # Thin accent stripe at top for visual punch
    c.setFillColor(level_color)
    c.roundRect(x, y - 1.5 * mm, block_width, 1.5 * mm, 0.75 * mm, fill=1, stroke=0)

    # Zone name (truncate if needed to leave room for badge)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 7)
    name_max_w = block_width - 28 * mm
    name = zone["name"]
    while c.stringWidth(name, "Helvetica-Bold", 7) > name_max_w and len(name) > 10:
        name = name[:-1]
    c.drawString(x + 3 * mm, y - 4.5 * mm, name)

    # Badge: level + total plants — right-aligned with safe margin
    badge_text = f"{zone['level']}  \u2022  {zone['total']}"
    c.setFont("Helvetica-Bold", 6.5)
    bw = c.stringWidth(badge_text, "Helvetica-Bold", 6.5)
    c.drawRightString(x + block_width - 3 * mm, y - 4.5 * mm, badge_text)

    # Species content
    cy = y - header_h - padding
    for sec_id, lines in section_data:
        for i, line in enumerate(lines):
            if has_sub and sec_id and i == 0:
                c.setFont("Helvetica-Bold", font_size - 0.5)
                c.setFillColor(MED_GREY)
                c.drawString(x + 2.5 * mm, cy, sec_id)
                text_x = x + 15 * mm
            elif has_sub:
                text_x = x + 15 * mm
            else:
                text_x = x + 3 * mm
            c.setFont("Helvetica", font_size)
            c.setFillColor(DARK_GREEN)
            c.drawString(text_x, cy, line)
            cy -= line_h

    # Note
    if zone["note"]:
        cy -= 0.5 * mm
        c.setFont("Helvetica-Oblique", font_size - 0.8)
        c.setFillColor(MED_GREY)
        c.drawString(x + 3 * mm, cy, zone["note"])

    return total_h


def generate_guide(output_path):
    width, height = landscape(A4)
    c = canvas.Canvas(output_path, pagesize=landscape(A4))

    margin = 8 * mm
    content_width = width - 2 * margin

    # ══════════════════════════════════════════
    # HEADER
    # ══════════════════════════════════════════
    header_h = 18 * mm
    c.setFillColor(FOREST_GREEN)
    c.rect(0, height - header_h, width, header_h, fill=1, stroke=0)

    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(12 * mm, height - 12.5 * mm, "NURSERY WATERING GUIDE")
    c.setFont("Helvetica", 8)
    c.drawString(12 * mm, height - 17 * mm,
                 "Firefly Corner Farm  |  Olivier\u2019s SOP + live farmOS inventory  |  30 March 2026  |  1,117 plants across 14 zones")

    # ══════════════════════════════════════════
    # INFO BAR: Five Senses + Temperature
    # ══════════════════════════════════════════
    bar_y = height - header_h - 2 * mm
    bar_h = 10 * mm

    # Five senses — left half
    senses_w = content_width * 0.55
    c.setFillColor(LIGHT_GREEN)
    c.roundRect(margin, bar_y - bar_h, senses_w, bar_h, 2 * mm, fill=1, stroke=0)
    c.setFillColor(DARK_GREEN)
    c.setFont("Helvetica-Bold", 7)
    c.drawString(margin + 3 * mm, bar_y - 4.5 * mm, "BEFORE YOU START \u2014 THE FIVE SENSES")
    c.setFont("Helvetica", 6.5)
    c.setFillColor(black)
    c.drawString(margin + 3 * mm, bar_y - 8.5 * mm,
                 "LOOK: wilting, yellowing?   LISTEN: pump ok?   SMELL: ammonia = problem   TOUCH: soil moisture   TEMP: check thermometer")

    # Temperature — right half
    temp_x = margin + senses_w + 3 * mm
    temp_w = content_width - senses_w - 3 * mm
    c.setFillColor(LIGHT_GREEN)
    c.roundRect(temp_x, bar_y - bar_h, temp_w, bar_h, 2 * mm, fill=1, stroke=0)
    c.setFillColor(DARK_GREEN)
    c.setFont("Helvetica-Bold", 7)
    c.drawString(temp_x + 3 * mm, bar_y - 4.5 * mm, "TEMPERATURE TRIGGERS")

    temp_items = [
        (ACCENT_GREEN, "<25\u00b0C  Normal", temp_x + 3 * mm),
        (WARM_AMBER, "25\u00b0C  Misting ON", temp_x + 42 * mm),
        (RED_ALERT, "30\u00b0C+  Small pots first!", temp_x + 82 * mm),
    ]
    for color, text, tx in temp_items:
        c.setFillColor(color)
        c.circle(tx + 1.2 * mm, bar_y - 7.5 * mm, 1.5 * mm, fill=1, stroke=0)
        c.setFillColor(black)
        c.setFont("Helvetica", 6.5)
        c.drawString(tx + 4 * mm, bar_y - 8.5 * mm, text)

    # ══════════════════════════════════════════
    # WATER LEVEL LEGEND
    # ══════════════════════════════════════════
    legend_y = bar_y - bar_h - 4 * mm
    c.setFont("Helvetica-Bold", 7)
    c.setFillColor(DARK_GREEN)
    c.drawString(margin, legend_y, "WATER LEVELS:")

    legend_items = [
        (HIGH_COLOR, "HIGH  =  3 slow passes with hose gun", margin + 27 * mm),
        (MEDIUM_COLOR, "MEDIUM  =  2 passes", margin + 95 * mm),
        (LOW_COLOR, "LOW  =  1 pass", margin + 145 * mm),
        (MONITOR_COLOR, "2x/WEEK  =  15\u201320 min with extended hose", margin + 185 * mm),
    ]
    for color, text, lx in legend_items:
        c.setFillColor(color)
        c.roundRect(lx, legend_y - 1.8 * mm, 5 * mm, 5 * mm, 1 * mm, fill=1, stroke=0)
        c.setFillColor(black)
        c.setFont("Helvetica", 6.5)
        c.drawString(lx + 6.5 * mm, legend_y - 0.3 * mm, text)

    # ══════════════════════════════════════════
    # ZONE BLOCKS — 3 columns, balanced
    # ══════════════════════════════════════════
    col_gap = 4 * mm
    col_width = (content_width - 2 * col_gap) / 3
    col_x = [margin, margin + col_width + col_gap, margin + 2 * (col_width + col_gap)]
    zones_start_y = legend_y - 7 * mm

    # Column layout — balanced by visual weight:
    # Col 1: Shelving I (big), Ground Left (tiny)
    # Col 2: Shelving II, Shelving III
    # Col 3: Ground Right, Back Zone, The Hill
    columns = [
        [ZONES[0], ZONES[4]],            # Shelving I + Ground Left
        [ZONES[1], ZONES[2]],            # Shelving II + III
        [ZONES[3], ZONES[5], ZONES[6]],  # Ground Right + Back Zone + The Hill
    ]

    zone_gap = 3 * mm
    col_bottoms = []
    for col_idx, col_zones in enumerate(columns):
        cy = zones_start_y
        for zone in col_zones:
            h = draw_zone_block(c, zone, col_x[col_idx], cy, col_width,
                                font_size=6.2, line_h=3.5 * mm)
            cy -= h + zone_gap
        col_bottoms.append(cy + zone_gap)

    # ══════════════════════════════════════════
    # TIPS BOX — directly below zones
    # ══════════════════════════════════════════
    lowest = min(col_bottoms)
    tips_h = 22 * mm
    tips_y = lowest - tips_h - 3 * mm

    # If tips would go below margin, push up
    if tips_y < 6 * mm:
        tips_y = 6 * mm

    c.setFillColor(LIGHT_GREEN)
    c.roundRect(margin, tips_y, content_width, tips_h, 2.5 * mm, fill=1, stroke=0)

    c.setFillColor(DARK_GREEN)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(margin + 4 * mm, tips_y + tips_h - 5.5 * mm, "WATERING ESSENTIALS")

    # Tips in 3 columns
    tip_font = 6.2
    tip_line_h = 3.5 * mm
    tip_col_w = content_width / 3

    tips_col1 = [
        "Water ROOT ZONE, not leaves.",
        "Gentle flow \u2014 never blast seedlings from above.",
        "Morning is best. Avoid midday on hot days.",
    ]
    tips_col2 = [
        "Check soil 2\u20133cm down: wet = skip, dry = water.",
        "Squeeze larger pots to feel moisture depth.",
        "For seedlings: water slowly at pot edge.",
    ]
    tips_col3 = [
        "Johnsons: bypass valve INTO tank before pump.",
        "Hot rose fitting? Run water briefly first.",
        "Watch for rats (onions) & white butterflies (brassicas).",
    ]

    for col_idx, tips in enumerate([tips_col1, tips_col2, tips_col3]):
        tx = margin + col_idx * tip_col_w + 5 * mm
        ty = tips_y + tips_h - 10 * mm
        for tip in tips:
            c.setFont("Helvetica", tip_font)
            c.setFillColor(black)
            c.drawString(tx, ty, f"\u2022  {tip}")
            ty -= tip_line_h

    # ══════════════════════════════════════════
    # FOOTER
    # ══════════════════════════════════════════
    c.setFont("Helvetica", 4.5)
    c.setFillColor(MED_GREY)
    footer_y = tips_y - 4 * mm if tips_y > 10 * mm else 2 * mm
    c.drawString(margin, footer_y,
                 "Generated from farmOS live data + Olivier\u2019s Nursery Operations SOP  |  Firefly Corner Farm, Krambach NSW  |  Print & pin in nursery")

    c.save()
    print(f"Generated: {output_path}")


if __name__ == "__main__":
    output = "/Users/agnes/Repos/FireflyCorner/claude-docs/nursery-watering-guide.pdf"
    generate_guide(output)
