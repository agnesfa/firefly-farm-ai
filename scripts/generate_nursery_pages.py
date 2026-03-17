#!/usr/bin/env python3
"""
Generate view + observe HTML pages for nursery locations and the seed bank.

Each nursery zone gets:
1. A VIEW page ({LOC_ID}.html) — shows current plant inventory with nursery details
   (process, seeding date, viable count, RTT status, destination)
2. An OBSERVE page ({LOC_ID}-observe.html) — Quick Report + Zone Note form

The view pages load inventory data from knowledge/nursery_inventory_sheet_march2026.csv.
The observe pages use the same form as before but link from view pages via FAB.

Usage:
    python scripts/generate_nursery_pages.py
    python scripts/generate_nursery_pages.py --output site/public/
"""

import argparse
import csv
import json
from collections import defaultdict
from html import escape
from pathlib import Path

# ─── CONFIGURATION ───────────────────────────────────────────────────────────

OBSERVE_ENDPOINT = "https://script.google.com/macros/s/AKfycbwxz3n9MSH45tQ1KX1_MacGAheIP_KcFMmlX_AWnYMI4-wwQ0ZNjYO5U8DJqHebcGPa/exec"

# Nursery locations — same as in generate_nursery_qrcodes.py
# Format: (id, display_name, breadcrumb)
NURSERY_LOCATIONS = [
    # Shelving unit 1
    ("NURS.SH1-1", "Shelf 1-1", "Firefly Corner \u00b7 Plant Nursery \u00b7 Shelving Unit 1"),
    ("NURS.SH1-2", "Shelf 1-2", "Firefly Corner \u00b7 Plant Nursery \u00b7 Shelving Unit 1"),
    ("NURS.SH1-3", "Shelf 1-3", "Firefly Corner \u00b7 Plant Nursery \u00b7 Shelving Unit 1"),
    ("NURS.SH1-4", "Shelf 1-4", "Firefly Corner \u00b7 Plant Nursery \u00b7 Shelving Unit 1"),
    # Shelving unit 2
    ("NURS.SH2-1", "Shelf 2-1", "Firefly Corner \u00b7 Plant Nursery \u00b7 Shelving Unit 2"),
    ("NURS.SH2-2", "Shelf 2-2", "Firefly Corner \u00b7 Plant Nursery \u00b7 Shelving Unit 2"),
    ("NURS.SH2-3", "Shelf 2-3", "Firefly Corner \u00b7 Plant Nursery \u00b7 Shelving Unit 2"),
    ("NURS.SH2-4", "Shelf 2-4", "Firefly Corner \u00b7 Plant Nursery \u00b7 Shelving Unit 2"),
    # Shelving unit 3
    ("NURS.SH3-1", "Shelf 3-1", "Firefly Corner \u00b7 Plant Nursery \u00b7 Shelving Unit 3"),
    ("NURS.SH3-2", "Shelf 3-2", "Firefly Corner \u00b7 Plant Nursery \u00b7 Shelving Unit 3"),
    ("NURS.SH3-3", "Shelf 3-3", "Firefly Corner \u00b7 Plant Nursery \u00b7 Shelving Unit 3"),
    ("NURS.SH3-4", "Shelf 3-4", "Firefly Corner \u00b7 Plant Nursery \u00b7 Shelving Unit 3"),
    # Ground areas
    ("NURS.GR", "Ground Right", "Firefly Corner \u00b7 Plant Nursery \u00b7 Ground Right"),
    ("NURS.GL", "Ground Left", "Firefly Corner \u00b7 Plant Nursery \u00b7 Ground Left"),
    ("NURS.FRT", "Front Area", "Firefly Corner \u00b7 Plant Nursery \u00b7 Front"),
    ("NURS.BCK", "Back Area", "Firefly Corner \u00b7 Plant Nursery \u00b7 Back"),
    ("NURS.HILL", "Hillside", "Firefly Corner \u00b7 Plant Nursery \u00b7 Hill"),
    ("NURS.STRB", "Strawberry Area", "Firefly Corner \u00b7 Plant Nursery \u00b7 Strawberry"),
    # Seed bank
    ("SEED.BANK", "Seed Bank", "Firefly Corner \u00b7 Seed Bank"),
]

# Process type styling
PROCESS_STYLES = {
    "cutting": {"icon": "✂️", "label": "Cuttings", "bg": "#edf4e4", "color": "#2d5016"},
    "seedling": {"icon": "🌱", "label": "Seedlings", "bg": "#e8f4fd", "color": "#1e40af"},
    "root": {"icon": "🌿", "label": "Root Division", "bg": "#fef3c7", "color": "#92400e"},
    "grafted": {"icon": "🔗", "label": "Grafted", "bg": "#fce7f3", "color": "#9d174d"},
    "given plant": {"icon": "🎁", "label": "Given Plants", "bg": "#f3e8ff", "color": "#6b21a8"},
    "plant": {"icon": "🪴", "label": "Plants", "bg": "#d1fae5", "color": "#065f46"},
    "mother plant": {"icon": "👑", "label": "Mother Plants", "bg": "#fef3c7", "color": "#78350f"},
    "spontaneous": {"icon": "🌾", "label": "Spontaneous", "bg": "#f1f5f9", "color": "#475569"},
}

DEFAULT_PROCESS_STYLE = {"icon": "🌿", "label": "Other", "bg": "#f1f5f9", "color": "#475569"}


def load_plant_types(csv_path):
    """Load plant types from CSV for the Add New Plant search."""
    plant_types = []
    if not csv_path.exists():
        print(f"  Warning: plant_types.csv not found at {csv_path}")
        return plant_types

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            farmos_name = row.get("farmos_name", "").strip()
            strata = row.get("strata", "").strip()
            botanical = row.get("botanical_name", "").strip()
            if farmos_name:
                plant_types.append({
                    "species": farmos_name,
                    "strata": strata,
                    "botanical": botanical,
                })

    plant_types.sort(key=lambda x: x["species"])
    return plant_types


def load_nursery_inventory(csv_path):
    """Load nursery inventory grouped by location ID."""
    by_location = defaultdict(list)
    if not csv_path.exists():
        print(f"  Warning: nursery inventory not found at {csv_path}")
        return by_location

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            loc_id = row.get("Location ID", "").strip()
            if not loc_id:
                continue
            by_location[loc_id].append({
                "species": row.get("Species (farmOS)", "").strip(),
                "common_name": row.get("Common Name", "").strip(),
                "variety": row.get("Variety", "").strip(),
                "botanical": row.get("Botanical Name", "").strip(),
                "strata": row.get("Strata", "").strip(),
                "succession": row.get("Succession", "").strip(),
                "source": row.get("Source", "").strip(),
                "process": row.get("Process", "").strip(),
                "seeding_date": row.get("Seeding/Planting Date", "").strip(),
                "pots_planted": row.get("Pots Planted", "").strip(),
                "viable": row.get("Viable (Mar 17)", "").strip(),
                "success_rate": row.get("Success Rate %", "").strip(),
                "nrtt": row.get("Not RTT", "").strip(),
                "rtt": row.get("RTT", "").strip(),
                "destination": row.get("Destination", "").strip(),
                "how_many": row.get("How Many", "").strip(),
                "when": row.get("When", "").strip(),
            })

    return by_location


def is_seed_bank(loc_id):
    return loc_id == "SEED.BANK"


def header_gradient(loc_id):
    if is_seed_bank(loc_id):
        return "linear-gradient(145deg, #3d6b2e 0%, #5a8a3c 60%, #6b9e4a 100%)"
    return "linear-gradient(145deg, #2d6b1a 0%, #4a8c2e 60%, #5da83a 100%)"


def location_badge(loc_id):
    if is_seed_bank(loc_id):
        return "Seed Storage"
    if "SH" in loc_id:
        return "Nursery Shelf"
    return "Nursery Zone"


def render_plant_card(plant, plant_db):
    """Render a single plant card HTML."""
    species = escape(plant["species"])
    botanical = escape(plant["botanical"])
    process = escape(plant["process"])
    viable = plant["viable"]
    pots = plant["pots_planted"]
    seeding_date = escape(plant["seeding_date"])
    source = escape(plant["source"])
    rtt = plant["rtt"]
    nrtt = plant["nrtt"]
    destination = escape(plant["destination"])
    how_many = plant["how_many"]
    when = escape(plant["when"])
    success_rate = plant["success_rate"]
    strata = escape(plant["strata"])
    succession = escape(plant["succession"])

    ps = PROCESS_STYLES.get(process.lower(), DEFAULT_PROCESS_STYLE)

    # Count badge
    try:
        viable_int = int(float(viable)) if viable else 0
    except ValueError:
        viable_int = 0

    count_color = ps["color"]
    count_bg = ps["bg"]
    if viable_int == 0:
        count_color = "#9ca3af"
        count_bg = "#f3f4f6"

    # RTT badge
    rtt_html = ""
    try:
        rtt_int = int(float(rtt)) if rtt else 0
    except ValueError:
        rtt_int = 0
    if rtt_int > 0:
        dest_text = f" → {destination}" if destination else ""
        rtt_html = f'<span class="rtt-badge">\U0001f4e6 {rtt_int} ready{dest_text}</span>'

    # Detail meta items
    meta_parts = []
    if seeding_date:
        meta_parts.append(f"Seeded: {seeding_date}")
    if pots:
        meta_parts.append(f"Pots: {pots}")
    if success_rate:
        meta_parts.append(f"Success: {success_rate}%")
    if source:
        meta_parts.append(f"Source: {source}")
    meta_html = " · ".join(meta_parts) if meta_parts else ""

    # Strata + succession tags
    tags_html = ""
    if strata:
        tags_html += f'<span class="nursery-tag">{strata}</span>'
    if succession:
        tags_html += f'<span class="nursery-tag">{succession}</span>'

    # Transplant planning detail
    transplant_html = ""
    if rtt_int > 0:
        parts = []
        if destination:
            parts.append(f"Destination: {destination}")
        if how_many:
            parts.append(f"How many: {how_many}")
        if when:
            parts.append(f"When: {when}")
        try:
            nrtt_int = int(float(nrtt)) if nrtt else 0
        except ValueError:
            nrtt_int = 0
        if nrtt_int > 0:
            parts.append(f"Not ready yet: {nrtt_int}")
        if parts:
            transplant_html = f'<div class="transplant-plan"><div class="transplant-title">\U0001f4cb Transplant Plan</div>{"".join(f"<div>{p}</div>" for p in parts)}</div>'

    # Look up description from plant_db
    desc_html = ""
    db_entry = plant_db.get(plant["species"])
    if db_entry:
        desc = db_entry.get("description", "")
        if desc:
            desc_html = f'<p class="plant-desc">{escape(desc)}</p>'

    return f"""
    <div class="plant-card nursery-card" style="border-left-color:{ps['color']}" onclick="this.classList.toggle('expanded')">
      <div class="plant-header">
        <div class="plant-info">
          <div class="plant-name">{species}</div>
          <div class="plant-botanical">{botanical}</div>
          <div class="plant-process">{ps['icon']} {escape(process)}{f' · {seeding_date}' if seeding_date else ''}</div>
        </div>
        <span class="plant-count" style="background:{count_bg};color:{count_color}">{viable_int if viable_int > 0 else '✝'}</span>
      </div>
      {rtt_html}
      <div class="plant-detail">
        {desc_html}
        <div class="plant-meta">{meta_html}</div>
        <div class="nursery-tags">{tags_html}</div>
        {transplant_html}
      </div>
    </div>"""


def render_inventory_section(plants, plant_db):
    """Render the plant inventory section for a nursery zone."""
    if not plants:
        return '<div class="empty-zone"><p>No plants recorded at this location yet.</p></div>'

    # Group by process type
    by_process = defaultdict(list)
    for p in plants:
        proc = p["process"].lower() if p["process"] else "other"
        by_process[proc].append(p)

    # Sort process groups by count (most first)
    sorted_processes = sorted(by_process.items(), key=lambda x: -len(x[1]))

    total_plants = 0
    for p in plants:
        try:
            total_plants += int(float(p["viable"])) if p["viable"] else 0
        except ValueError:
            pass

    html = '<div class="plant-inventory">\n'

    for proc_key, proc_plants in sorted_processes:
        ps = PROCESS_STYLES.get(proc_key, DEFAULT_PROCESS_STYLE)

        html += f"""
    <div class="strata-group">
      <div class="strata-header" style="background:{ps['bg']};border-bottom-color:{ps['color']}">
        <span class="strata-icon">{ps['icon']}</span>
        <div class="strata-label">
          <span class="strata-name" style="color:{ps['color']}">{ps['label']}</span>
          <span class="strata-height">{len(proc_plants)} {'entry' if len(proc_plants) == 1 else 'entries'}</span>
        </div>
        <span class="strata-count" style="background:{ps['color']}">{sum(int(float(p['viable'] or 0)) for p in proc_plants)}</span>
      </div>
      <div class="strata-plants">"""

        for p in sorted(proc_plants, key=lambda x: x["species"]):
            html += render_plant_card(p, plant_db)

        html += """
      </div>
    </div>\n"""

    html += '</div>\n'
    return html


def render_view_page(loc_id, display_name, breadcrumb, plants, plant_db):
    """Render a nursery VIEW page showing plant inventory."""
    gradient = header_gradient(loc_id)
    badge = location_badge(loc_id)
    escaped_id = escape(loc_id)
    escaped_name = escape(display_name)
    escaped_breadcrumb = escape(breadcrumb)

    if is_seed_bank(loc_id):
        footer_label = "Firefly Corner Farm \u00b7 Seed Bank"
    else:
        footer_label = "Firefly Corner Farm \u00b7 Plant Nursery"

    # Stats
    total_species = len(set(p["species"] for p in plants))
    total_viable = 0
    total_rtt = 0
    for p in plants:
        try:
            total_viable += int(float(p["viable"])) if p["viable"] else 0
        except ValueError:
            pass
        try:
            total_rtt += int(float(p["rtt"])) if p["rtt"] else 0
        except ValueError:
            pass

    stats_html = f"""
    <div class="section-stats">
      <div class="stat"><div class="stat-value">{total_species}</div><div class="stat-label">species</div></div>
      <div class="stat"><div class="stat-value">{total_viable}</div><div class="stat-label">viable plants</div></div>
      <div class="stat"><div class="stat-value">{total_rtt}</div><div class="stat-label">ready to transplant</div></div>
    </div>""" if plants else ""

    inventory_html = render_inventory_section(plants, plant_db)

    # Zone navigation bar — shelves in one group, ground areas in another
    zone_nav = render_zone_nav(loc_id)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>{escaped_name} — Firefly Corner Nursery</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600;700&family=DM+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="styles.css">
<style>
.nursery-card .plant-process {{ font-size: 0.82rem; color: #6b7280; margin-top: 2px; }}
.rtt-badge {{ display: inline-block; background: #fef3c7; color: #92400e; font-size: 0.78rem; font-weight: 600;
  padding: 3px 10px; border-radius: 12px; margin: 4px 0 0 0; }}
.nursery-tag {{ display: inline-block; background: #f1f5f9; color: #475569; font-size: 0.75rem;
  padding: 2px 8px; border-radius: 8px; margin: 2px 4px 2px 0; }}
.nursery-tags {{ margin-top: 6px; }}
.transplant-plan {{ background: #fffbeb; border-left: 3px solid #f59e0b; padding: 8px 12px; margin-top: 8px;
  border-radius: 0 6px 6px 0; font-size: 0.82rem; color: #78350f; }}
.transplant-title {{ font-weight: 600; margin-bottom: 4px; }}
.empty-zone {{ text-align: center; padding: 40px 20px; color: #9ca3af; font-style: italic; }}
.zone-nav {{ display: flex; flex-wrap: wrap; gap: 4px; padding: 8px 16px; background: #f8faf5; }}
.zone-nav-group {{ display: flex; flex-wrap: wrap; gap: 4px; width: 100%; margin-bottom: 4px; }}
.zone-nav-label {{ font-size: 0.7rem; color: #9ca3af; text-transform: uppercase; letter-spacing: 0.05em;
  width: 100%; padding: 2px 0; }}
.zone-tab {{ font-size: 0.75rem; padding: 4px 8px; background: white; border: 1px solid #d1d5db;
  border-radius: 6px; text-decoration: none; color: #374151; white-space: nowrap; }}
.zone-tab:hover {{ background: #f0fdf4; border-color: #4a8c2e; }}
.zone-tab.active {{ background: #2d6b1a; color: white; border-color: #2d6b1a; font-weight: 600; }}
.obs-fab {{ position: fixed; bottom: 24px; right: 24px; width: 56px; height: 56px;
  background: #2d6b1a; color: white; border: none; border-radius: 50%;
  font-size: 24px; cursor: pointer; box-shadow: 0 4px 12px rgba(0,0,0,0.25);
  z-index: 100; display: flex; align-items: center; justify-content: center;
  text-decoration: none; }}
.obs-fab:hover {{ background: #1a5010; transform: scale(1.05); }}
</style>
</head>
<body>
<div class="page">

  <div class="section-header" style="background:{gradient}">
    <div class="breadcrumb">{escaped_breadcrumb}</div>
    <div class="section-title-row">
      <h1 class="section-range">{escaped_name}</h1>
      <span class="section-type-badge">{'🌱' if not is_seed_bank(loc_id) else '🌰'} {badge}</span>
    </div>
    {stats_html}
  </div>

  {zone_nav}

  <div style="padding: 0 0 80px 0;">
    {inventory_html}
  </div>

  <div class="footer">
    <div class="footer-sub">Inventory date: March 17, 2026</div>
    <div class="footer-sub">{footer_label}</div>
  </div>

</div>

<!-- Floating action button → observe page -->
<a href="{escaped_id}-observe.html" class="obs-fab" title="Record Observation">📋</a>

</body>
</html>"""
    return html


def render_zone_nav(current_loc_id):
    """Render navigation tabs for all nursery zones."""
    shelves_1 = [l for l in NURSERY_LOCATIONS if l[0].startswith("NURS.SH1")]
    shelves_2 = [l for l in NURSERY_LOCATIONS if l[0].startswith("NURS.SH2")]
    shelves_3 = [l for l in NURSERY_LOCATIONS if l[0].startswith("NURS.SH3")]
    ground = [l for l in NURSERY_LOCATIONS if l[0].startswith("NURS.") and "SH" not in l[0]]
    seed = [l for l in NURSERY_LOCATIONS if l[0] == "SEED.BANK"]

    def tab(loc_id, label):
        active = " active" if loc_id == current_loc_id else ""
        return f'<a href="{loc_id}.html" class="zone-tab{active}">{escape(label)}</a>'

    html = '<div class="zone-nav">\n'

    html += '<div class="zone-nav-group"><span class="zone-nav-label">Shelving Unit I</span>'
    html += "".join(tab(l[0], l[1]) for l in shelves_1)
    html += '</div>\n'

    html += '<div class="zone-nav-group"><span class="zone-nav-label">Shelving Unit II</span>'
    html += "".join(tab(l[0], l[1]) for l in shelves_2)
    html += '</div>\n'

    html += '<div class="zone-nav-group"><span class="zone-nav-label">Shelving Unit III</span>'
    html += "".join(tab(l[0], l[1]) for l in shelves_3)
    html += '</div>\n'

    html += '<div class="zone-nav-group"><span class="zone-nav-label">Ground & Zones</span>'
    html += "".join(tab(l[0], l[1]) for l in ground)
    html += '</div>\n'

    if seed:
        html += '<div class="zone-nav-group"><span class="zone-nav-label">Storage</span>'
        html += "".join(tab(l[0], l[1]) for l in seed)
        html += '</div>\n'

    html += '</div>\n'
    return html


def render_observe_page(loc_id, display_name, breadcrumb, plant_types_json):
    """Render a nursery OBSERVE page (Quick Report + Zone Note form)."""

    gradient = header_gradient(loc_id)
    badge = location_badge(loc_id)
    escaped_id = escape(loc_id)
    escaped_name = escape(display_name)
    escaped_breadcrumb = escape(breadcrumb)

    if is_seed_bank(loc_id):
        quick_hint = "Record a seed observation — select species, note quantity or condition."
        note_hint = "Leave a general note about the seed bank — stock levels, organisation, etc."
        note_placeholder = "Seed bank condition, restocking needs, organisation notes..."
        species_label = "Seed species"
        count_label = "Quantity"
        quick_submit_label = "Save Seed Observation"
        note_submit_label = "Save Seed Bank Note"
        footer_label = "Firefly Corner Farm \u00b7 Seed Bank"
    else:
        quick_hint = "Record a plant observation — select species, note count and condition."
        note_hint = "Leave a general note about this nursery zone — no plant selection needed."
        note_placeholder = "Overall zone condition, watering needs, pest observations, space availability..."
        species_label = "Plant species"
        count_label = "Count"
        quick_submit_label = "Save Observation"
        note_submit_label = "Save Zone Note"
        footer_label = "Firefly Corner Farm \u00b7 Plant Nursery"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>{escaped_name} — Field Observation</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600;700&family=DM+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="styles.css">
<link rel="stylesheet" href="styles-observe.css">
</head>
<body>
<div class="page">

  <div class="section-header" style="background:{gradient}">
    <div class="breadcrumb">{escaped_breadcrumb} \u00b7 Field Observation</div>
    <div class="section-title-row">
      <h1 class="section-range">{escaped_name}</h1>
      <span class="section-type-badge">{"&#x1f331;" if not is_seed_bank(loc_id) else "&#x1f330;"} {badge}</span>
    </div>
    <div class="obs-subtitle">Recording observation for {escaped_id}</div>
  </div>

  <!-- Back to view link -->
  <div style="padding: 8px 16px; background: #f8faf5;">
    <a href="{escaped_id}.html" style="color: #2d6b1a; font-size: 0.85rem; text-decoration: none;">← Back to {escaped_name} inventory</a>
  </div>

  <!-- Offline queue banner -->
  <div id="queue-banner" class="queue-banner" style="display:none">
    <span class="queue-count"></span>
    <button onclick="syncPendingQueue()" class="queue-sync-btn">Sync Now</button>
  </div>

  <!-- Observer info -->
  <div class="obs-form-section">
    <div class="obs-field-group">
      <label class="obs-label" for="observer-name">Your name</label>
      <input type="text" id="observer-name" class="obs-input" placeholder="e.g. Claire, James, WWOOFer name" autocomplete="name">
    </div>
    <div class="obs-field-group">
      <label class="obs-label" for="obs-datetime">Date & time</label>
      <input type="datetime-local" id="obs-datetime" class="obs-input">
    </div>
  </div>

  <!-- Mode toggle -->
  <div class="mode-toggle">
    <button class="mode-tab active" data-mode="quick">Quick Report</button>
    <button class="mode-tab" data-mode="comment">Zone Note</button>
  </div>

  <!-- QUICK REPORT MODE -->
  <div id="mode-quick" class="obs-mode-panel">
    <div class="obs-form-section">
      <p class="obs-hint">{quick_hint}</p>

      <div class="obs-field-group">
        <label class="obs-label" for="quick-species">{species_label}</label>
        <input type="text" id="quick-species-search" class="obs-input" placeholder="Type to search species..." autocomplete="off">
        <div id="quick-species-results" class="plant-search-results" style="display:none"></div>
        <select id="quick-species" class="obs-select" style="display:none">
          <option value="">— Select species —</option>
          <option value="Unknown">Unknown / Not sure</option>
        </select>
      </div>

      <div id="quick-plant-info"></div>

      <div class="obs-field-row">
        <div class="obs-field-group obs-field-small">
          <label class="obs-label" for="quick-count">{count_label}</label>
          <input type="number" id="quick-count" class="obs-input obs-input-number" inputmode="numeric" min="0" placeholder="&#x2014;">
        </div>
        <div class="obs-field-group obs-field-small">
          <label class="obs-label" for="quick-condition">Condition</label>
          <select id="quick-condition" class="obs-select">
            <option value="alive">Alive &#x2713;</option>
            <option value="damaged">Damaged &#x26a0;&#xfe0f;</option>
            <option value="dead">Dead &#x271d;</option>
          </select>
        </div>
      </div>

      <div class="obs-field-group">
        <label class="obs-label" for="quick-notes">Notes</label>
        <input type="text" id="quick-notes" class="obs-input" placeholder="What did you observe?">
      </div>

      <!-- Photo capture -->
      <div class="obs-media-area">
        <label class="obs-media-btn">
          <input type="file" accept="image/*" capture="environment" class="obs-photo-input" data-target="section" hidden>
          <span>&#x1f4f7; Add Photo</span>
        </label>
        <div class="obs-photo-previews"></div>
      </div>

      <div class="obs-field-group">
        <label class="obs-label" for="section-notes-quick">Zone notes (optional)</label>
        <textarea id="section-notes-quick" class="obs-textarea" rows="2" placeholder="General observations about this zone..."></textarea>
      </div>

      <button id="quick-submit" class="obs-submit-btn">{quick_submit_label}</button>
    </div>
  </div>

  <!-- ZONE NOTE MODE -->
  <div id="mode-comment" class="obs-mode-panel" style="display:none">
    <div class="obs-form-section">
      <p class="obs-hint">{note_hint}</p>

      <div class="obs-field-group">
        <label class="obs-label" for="comment-notes">Zone notes</label>
        <textarea id="comment-notes" class="obs-textarea" rows="4" placeholder="{note_placeholder}"></textarea>
      </div>

      <!-- Photo capture -->
      <div class="obs-media-area">
        <label class="obs-media-btn">
          <input type="file" accept="image/*" capture="environment" class="obs-photo-input" data-target="section" hidden>
          <span>&#x1f4f7; Add Photo</span>
        </label>
        <div class="obs-photo-previews"></div>
      </div>

      <button id="comment-submit" class="obs-submit-btn">{note_submit_label}</button>
    </div>
  </div>

  <!-- Status messages -->
  <div id="obs-status" class="obs-status" style="display:none"></div>

  <!-- Navigation -->
  <div class="obs-nav">
    <a href="{escaped_id}.html" class="obs-back-link">&#x2190; Back to {escaped_name}</a>
    <a href="index.html" class="obs-back-link">&#x2190; Back to farm overview</a>
  </div>

  <div class="footer">
    <div class="footer-sub">{footer_label}</div>
  </div>

</div>

<script>
const SECTION_DATA = {{
  id: {json.dumps(loc_id)},
  range: {json.dumps(display_name)},
  plants: []
}};
const PLANT_TYPES_DATA = {plant_types_json};
const OBSERVE_ENDPOINT = {json.dumps(OBSERVE_ENDPOINT)};

// Nursery Quick Report: species search
(function() {{
  var searchInput = document.getElementById("quick-species-search");
  var resultsDiv = document.getElementById("quick-species-results");
  var hiddenSelect = document.getElementById("quick-species");

  if (!searchInput || !resultsDiv) return;

  searchInput.addEventListener("input", function() {{
    var query = this.value.trim().toLowerCase();
    if (query.length < 2) {{
      resultsDiv.style.display = "none";
      resultsDiv.innerHTML = "";
      return;
    }}

    var plantTypes = typeof PLANT_TYPES_DATA !== "undefined" ? PLANT_TYPES_DATA : [];
    var matches = [];

    if ("unknown".indexOf(query) !== -1) {{
      matches.push({{ species: "Unknown", strata: "", botanical: "Not sure / describe in notes" }});
    }}

    for (var i = 0; i < plantTypes.length; i++) {{
      var pt = plantTypes[i];
      var sLower = (pt.species || "").toLowerCase();
      var bLower = (pt.botanical || "").toLowerCase();
      if (sLower.indexOf(query) !== -1 || bLower.indexOf(query) !== -1) {{
        matches.push(pt);
        if (matches.length >= 15) break;
      }}
    }}

    if (matches.length === 0) {{
      resultsDiv.innerHTML = '<div class="plant-search-result" style="color:#9ca3af;cursor:default">No matches found</div>';
      resultsDiv.style.display = "block";
      return;
    }}

    var html = "";
    for (var j = 0; j < matches.length; j++) {{
      var m = matches[j];
      var esc = function(t) {{ var d = document.createElement("div"); d.appendChild(document.createTextNode(t)); return d.innerHTML; }};
      html += '<div class="plant-search-result" data-species="' + esc(m.species) +
        '" data-strata="' + esc(m.strata || "") +
        '" onclick="selectQuickSpecies(this)">' +
        '<div class="search-species">' + esc(m.species) + '</div>' +
        '<div class="search-meta">' + esc(m.botanical || "") +
        (m.strata ? " \\u00b7 " + esc(m.strata) : "") + '</div></div>';
    }}

    resultsDiv.innerHTML = html;
    resultsDiv.style.display = "block";
  }});

  document.addEventListener("click", function(e) {{
    if (!searchInput.contains(e.target) && !resultsDiv.contains(e.target)) {{
      resultsDiv.style.display = "none";
    }}
  }});
}})();

function selectQuickSpecies(el) {{
  var species = el.dataset.species;
  var searchInput = document.getElementById("quick-species-search");
  var resultsDiv = document.getElementById("quick-species-results");
  var hiddenSelect = document.getElementById("quick-species");

  if (searchInput) searchInput.value = species;
  if (resultsDiv) resultsDiv.style.display = "none";

  if (hiddenSelect) {{
    var exists = false;
    for (var i = 0; i < hiddenSelect.options.length; i++) {{
      if (hiddenSelect.options[i].value === species) {{ exists = true; break; }}
    }}
    if (!exists) {{
      var opt = document.createElement("option");
      opt.value = species;
      opt.textContent = species;
      hiddenSelect.appendChild(opt);
    }}
    hiddenSelect.value = species;
  }}

  updateQuickPlantInfo(species);
}}
</script>
<script src="observe.js"></script>
</body>
</html>"""
    return html


def load_plant_db(csv_path):
    """Load plant type descriptions keyed by farmos_name."""
    db = {}
    if not csv_path.exists():
        return db
    with open(csv_path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = row.get("farmos_name", "").strip()
            if name:
                db[name] = row
    return db


def main():
    parser = argparse.ArgumentParser(
        description="Generate view + observe pages for nursery locations and seed bank"
    )
    parser.add_argument(
        "--output",
        default="site/public/",
        help="Output directory for HTML files (default: site/public/)",
    )
    parser.add_argument(
        "--plants",
        default="knowledge/plant_types.csv",
        help="Path to plant_types.csv (default: knowledge/plant_types.csv)",
    )
    parser.add_argument(
        "--inventory",
        default="knowledge/nursery_inventory_sheet_march2026.csv",
        help="Path to nursery inventory CSV",
    )
    args = parser.parse_args()

    output_dir = Path(args.output)
    plants_csv = Path(args.plants)
    inventory_csv = Path(args.inventory)

    if not output_dir.exists():
        print(f"Error: output directory {output_dir} does not exist")
        return

    # Load plant types for species search
    print(f"Loading plant types from {plants_csv}...")
    plant_types = load_plant_types(plants_csv)
    plant_types_json = json.dumps(plant_types, ensure_ascii=False)
    print(f"  Loaded {len(plant_types)} plant types")

    # Load plant type descriptions
    plant_db = load_plant_db(plants_csv)

    # Load nursery inventory
    print(f"Loading nursery inventory from {inventory_csv}...")
    nursery_data = load_nursery_inventory(inventory_csv)
    total_entries = sum(len(v) for v in nursery_data.values())
    print(f"  Loaded {total_entries} entries across {len(nursery_data)} locations")

    print(f"\nGenerating {len(NURSERY_LOCATIONS)} nursery pages (view + observe)...")

    for loc_id, display_name, breadcrumb in NURSERY_LOCATIONS:
        plants = nursery_data.get(loc_id, [])

        # VIEW page
        view_file = f"{loc_id}.html"
        view_path = output_dir / view_file
        view_html = render_view_page(loc_id, display_name, breadcrumb, plants, plant_db)
        view_path.write_text(view_html, encoding="utf-8")

        # OBSERVE page
        obs_file = f"{loc_id}-observe.html"
        obs_path = output_dir / obs_file
        obs_html = render_observe_page(loc_id, display_name, breadcrumb, plant_types_json)
        obs_path.write_text(obs_html, encoding="utf-8")

        plant_count = sum(1 for p in plants if p.get("viable"))
        print(f"  {view_file} ({plant_count} plants) + {obs_file}")

    print(f"\nDone: {len(NURSERY_LOCATIONS) * 2} pages generated in {output_dir}")


if __name__ == "__main__":
    main()
