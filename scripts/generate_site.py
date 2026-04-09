#!/usr/bin/env python3
"""
Generate static QR code landing pages from farm data.

Input:
    site/src/data/sections.json  — parsed field sheet data
    knowledge/plant_types.csv    — master plant database with botanical info

Output:
    site/public/{section_id}.html — one page per section
    site/public/index.html        — paddock overview / entry point

Usage:
    python scripts/generate_site.py
    python scripts/generate_site.py --data site/src/data/sections.json --plants knowledge/plant_types.csv
"""

import argparse
import csv
import json
import html
import os
from pathlib import Path


def load_plant_db(csv_path):
    """Load plant types CSV into a lookup dict keyed by farmos_name (v7+) or common_name (v6)."""
    plants = {}
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # v7 uses farmos_name as the unique key; fall back to common_name for v6 compat
            key = row.get("farmos_name", "").strip() or row.get("common_name", "").strip()
            if key:
                plants[key] = {
                    "common_name": row.get("common_name", ""),
                    "variety": row.get("variety", ""),
                    "botanical": row.get("botanical_name", ""),
                    "family": row.get("crop_family", ""),
                    "origin": row.get("origin", ""),
                    "description": row.get("description", ""),
                    "lifespan": row.get("lifespan_years", "") or row.get("lifespan", ""),
                    "strata": row.get("strata", ""),
                    "succession": row.get("succession_stage", ""),
                    "functions": [f.strip() for f in row.get("plant_functions", "").split(",") if f.strip()],
                }
    return plants


def load_sections(json_path):
    """Load parsed section data."""
    with open(json_path, "r") as f:
        data = json.load(f)
    return data.get("sections", {}), data.get("rows", {})


def esc(text):
    """HTML-escape text."""
    return html.escape(str(text)) if text else ""


FUNCTION_STYLES = {
    "nitrogen_fixer":       ("⚡", "#fef3c7", "#92400e"),
    "nitrogen fixer":       ("⚡", "#fef3c7", "#92400e"),
    "edible_fruit":         ("🍎", "#fce7f3", "#9d174d"),
    "edible fruit":         ("🍎", "#fce7f3", "#9d174d"),
    "edible_nut":           ("🥜", "#fef3c7", "#92400e"),
    "edible nut":           ("🥜", "#fef3c7", "#92400e"),
    "edible_greens":        ("🥬", "#d1fae5", "#065f46"),
    "edible greens":        ("🥬", "#d1fae5", "#065f46"),
    "edible_root":          ("🥕", "#ffe4e6", "#9f1239"),
    "edible root":          ("🥕", "#ffe4e6", "#9f1239"),
    "edible_seed":          ("🌾", "#fef9c3", "#854d0e"),
    "edible seed":          ("🌾", "#fef9c3", "#854d0e"),
    "biomass_producer":     ("♻️", "#dbeafe", "#1e40af"),
    "biomass producer":     ("♻️", "#dbeafe", "#1e40af"),
    "nutrient_accumulator": ("⬇️", "#e0e7ff", "#3730a3"),
    "nutrient accumulator": ("⬇️", "#e0e7ff", "#3730a3"),
    "native_habitat":       ("🦎", "#d1fae5", "#065f46"),
    "native habitat":       ("🦎", "#d1fae5", "#065f46"),
    "timber":               ("🪵", "#f5f0e6", "#78350f"),
    "nectar_source":        ("🐝", "#fef3c7", "#92400e"),
    "nectar source":        ("🐝", "#fef3c7", "#92400e"),
    "medicinal":            ("💚", "#d1fae5", "#065f46"),
    "pest_management":      ("🛡️", "#ede9fe", "#5b21b6"),
    "pest management":      ("🛡️", "#ede9fe", "#5b21b6"),
    "companion_plant":      ("🤝", "#f0fdf4", "#166534"),
    "companion plant":      ("🤝", "#f0fdf4", "#166534"),
    "beneficial_insects":   ("🦋", "#fdf4ff", "#86198f"),
    "beneficial insects":   ("🦋", "#fdf4ff", "#86198f"),
    "aromatic":             ("🌿", "#f0fdf4", "#166534"),
    "living_mulch":         ("🍃", "#ecfdf5", "#047857"),
    "living mulch":         ("🍃", "#ecfdf5", "#047857"),
    "erosion_control":      ("🏔️", "#f1f5f9", "#475569"),
    "erosion control":      ("🏔️", "#f1f5f9", "#475569"),
    "windbreak":            ("💨", "#f1f5f9", "#475569"),
    "fodder":               ("🐄", "#fef3c7", "#92400e"),
    "ornamental":           ("🌸", "#fce7f3", "#9d174d"),
}

STRATA_CONFIG = {
    "emergent": {"label": "Emergent Canopy", "height": "20m+", "color": "#2d5016", "light": "#e8f0e0", "icon": "🌳"},
    "high":     {"label": "High Canopy",     "height": "8–20m", "color": "#4a7c29", "light": "#edf4e4", "icon": "🌿"},
    "medium":   {"label": "Medium Layer",    "height": "2–8m",  "color": "#6b9e3c", "light": "#f0f6e7", "icon": "🫑"},
    "low":      {"label": "Ground Layer",    "height": "0–2m",  "color": "#8bb85a", "light": "#f4f8ec", "icon": "🌱"},
}


def is_green_manure(species, plant_db):
    """Check if a species is tagged as green_manure in the plant database."""
    plant = plant_db.get(species, {})
    if not plant:
        # Fuzzy match: handles "Millet" matching "Millet (White French)" etc.
        for name, info in plant_db.items():
            if name.startswith(species + " ") or name.startswith(species + "("):
                plant = info
                break
    return "green_manure" in plant.get("functions", [])


def render_green_manure_box(green_manure_plants):
    """Render a lightweight green manure info section."""
    if not green_manure_plants:
        return ""

    species_names = sorted(set(p["species"] for p in green_manure_plants))
    species_list = ", ".join(esc(name) for name in species_names)

    return f"""
    <div class="green-manure-box">
      <div class="gm-header">
        <span class="gm-icon">🌱</span>
        <span class="gm-title">Green Manure Cover Crop</span>
      </div>
      <div class="gm-body">
        <div class="gm-species">{species_list}</div>
        <div class="gm-desc">Temporary cover crops planted for soil building and nitrogen fixation. Slashed and mulched every 2–3 months.</div>
      </div>
    </div>"""


def render_function_tag(fn):
    fn_key = fn.strip().lower()
    emoji, bg, fg = FUNCTION_STYLES.get(fn_key, ("•", "#f3f4f6", "#374151"))
    return f'<span class="fn-tag" style="background:{bg};color:{fg}">{emoji} {esc(fn)}</span>'


def format_planted_date_display(iso_date: str) -> str:
    """Format ISO date for human-readable display: '2025-04-25' → 'Apr 2025'."""
    if not iso_date:
        return ""
    try:
        from datetime import datetime as dt
        d = dt.strptime(iso_date[:10], "%Y-%m-%d")
        return d.strftime("%b %Y")
    except (ValueError, IndexError):
        return iso_date


def render_log_timeline(logs: list) -> str:
    """Render a compact log timeline for expanded plant card view."""
    if not logs:
        return ""

    log_icons = {
        "transplanting": "🌱",
        "observation": "📊",
        "activity": "🔧",
        "harvest": "🧺",
    }

    items = []
    for log in logs:
        icon = log_icons.get(log.get("type", ""), "📋")
        date = log.get("date", "")
        try:
            from datetime import datetime as dt
            d = dt.strptime(date, "%Y-%m-%d")
            date_display = d.strftime("%b %Y")
        except (ValueError, TypeError):
            date_display = date

        log_type = log.get("type", "").replace("_", " ").title()
        name = log.get("name", "")
        # Shorten log name for display
        short = name[:50] + "..." if len(name) > 50 else name

        items.append(
            f'<div class="log-entry">'
            f'<span class="log-icon">{icon}</span>'
            f'<span class="log-date">{esc(date_display)}</span>'
            f'<span class="log-type">{esc(log_type)}</span>'
            f'</div>'
        )

    return f'<div class="log-timeline"><div class="log-timeline-title">History</div>{"".join(items)}</div>'


def render_plant_card(planting, plant_db):
    """Render a single plant card HTML."""
    species = planting["species"]
    strata = planting["strata"]
    count = planting.get("count")
    notes = planting.get("notes", "")
    first_planted = planting.get("first_planted", "")
    logs = planting.get("logs", [])
    photo_url = planting.get("photo_url", "")

    plant = plant_db.get(species, {})
    st = STRATA_CONFIG.get(strata, STRATA_CONFIG["medium"])

    botanical = plant.get("botanical", "")
    desc = plant.get("description", "")
    family = plant.get("family", "")
    origin = plant.get("origin", "")
    lifespan = plant.get("lifespan", "")
    succession = plant.get("succession", "")
    functions = plant.get("functions", [])

    count_html = ""
    if count is not None and count > 0:
        count_html = f'<span class="plant-count" style="background:{st["light"]};color:{st["color"]}">{count}</span>'
    elif count is None:
        count_html = f'<span class="plant-count" style="background:#f0ece4;color:#999">—</span>'

    notes_html = f'<div class="plant-notes">{esc(notes)}</div>' if notes else ""

    # First planted date (shown in collapsed view)
    planted_display = format_planted_date_display(first_planted)
    planted_html = f'<div class="plant-planted">First planted {esc(planted_display)}</div>' if planted_display else ""

    # Function tags (collapsed: show 3)
    tags_html = "".join(render_function_tag(fn) for fn in functions[:3])
    if len(functions) > 3:
        tags_html += f'<span class="fn-more">+{len(functions) - 3}</span>'

    # Expanded detail
    all_tags_html = "".join(render_function_tag(fn) for fn in functions)

    meta_parts = [family, origin]
    if lifespan:
        meta_parts.append(f"Lives {lifespan}")
    meta_html = " · ".join(p for p in meta_parts if p)

    succession_html = ""
    succ_colors = {"pioneer": "#f59e0b", "secondary": "#3b82f6", "climax": "#2d5016"}
    if succession and succession in succ_colors:
        sc = succ_colors[succession]
        succ_labels = {
            "pioneer": "Fast-growing, short-lived species that build soil and create conditions for others",
            "secondary": "Medium-term species that fill the canopy as pioneers decline",
            "climax": "The permanent forest — long-lived trees that define the mature system",
        }
        succession_html = f'<div class="succession-tag" style="background:{sc}18;color:{sc}"><span class="succ-dot" style="background:{sc}"></span>{succession.title()} — {succ_labels.get(succession, "")}</div>'

    # Log timeline (expanded view)
    timeline_html = render_log_timeline(logs)

    # Species reference photo — populated by import_observations latest-wins.
    # Lazy-loaded so collapsed cards don't fetch photos until scrolled to.
    photo_html = ""
    if photo_url:
        photo_html = (
            f'<img class="plant-photo" loading="lazy" decoding="async" '
            f'src="{esc(photo_url)}" alt="{esc(species)} reference photo" '
            f'onerror="this.style.display=\'none\'">'
        )

    return f"""
    <div class="plant-card" style="border-left-color:{st['color']}" onclick="this.classList.toggle('expanded')">
      <div class="plant-header">
        {photo_html}
        <div class="plant-info">
          <div class="plant-name">{esc(species)}</div>
          <div class="plant-botanical">{esc(botanical)}</div>
          {planted_html}
        </div>
        {count_html}
      </div>
      {notes_html}
      <div class="plant-tags-collapsed">{tags_html}</div>
      <div class="plant-detail">
        <p class="plant-desc">{esc(desc)}</p>
        <div class="plant-meta">{esc(meta_html)}</div>
        {succession_html}
        <div class="plant-tags-expanded">{all_tags_html}</div>
        {timeline_html}
      </div>
    </div>"""


def render_strata_group(strata_key, plants, plant_db):
    """Render a strata group with all its plants."""
    st = STRATA_CONFIG.get(strata_key)
    if not st:
        return ""
    
    alive_count = sum(p.get("count") or 0 for p in plants)
    has_uninventoried = any(p.get("count") is None for p in plants)
    if alive_count > 0:
        count_badge = f'<span class="strata-count" style="background:{st["color"]}">{alive_count}</span>'
    elif has_uninventoried:
        count_badge = f'<span class="strata-count" style="background:#999">{len(plants)}</span>'
    else:
        count_badge = ""
    
    cards = "\n".join(render_plant_card(p, plant_db) for p in plants)
    
    return f"""
    <div class="strata-group">
      <div class="strata-header" style="background:{st['light']};border-bottom-color:{st['color']}">
        <span class="strata-icon">{st['icon']}</span>
        <div class="strata-label">
          <span class="strata-name" style="color:{st['color']}">{st['label']}</span>
          <span class="strata-height">{st['height']}</span>
        </div>
        {count_badge}
      </div>
      <div class="strata-plants">{cards}</div>
    </div>"""


def render_row_bar(row_info, sections_data, active_section_id, base_url=""):
    """Render the row navigation bar."""
    total = 0
    for sid in row_info.get("sections", []):
        sec = sections_data.get(sid, {})
        r = sec.get("range", "0-0").replace("–", "-").split("-")
        if len(r) == 2:
            try:
                total = max(total, float(r[1]))
            except ValueError:
                pass
    if total == 0:
        total = 63  # fallback
    
    bars = []
    for sid in row_info.get("sections", []):
        sec = sections_data.get(sid, {})
        length = float(sec.get("length", "1m").replace("m", ""))
        pct = (length / total) * 100
        active = sid == active_section_id
        bg = "#2d5016" if sec.get("has_trees") else "#8bb85a"
        icon = "🌳" if sec.get("has_trees") else "☀️"
        outline = "outline:2px solid #ff9933;outline-offset:-2px;border-radius:3px;" if active else ""
        opacity = "1" if active else "0.5"
        href = f'{base_url}{sid}.html'
        bars.append(f'<a href="{href}" class="rowbar-section" style="flex:0 0 {pct:.1f}%;background:{bg};opacity:{opacity};{outline}">{icon}</a>')
    
    return f"""
    <div class="row-bar">
      <div class="row-bar-label">{esc(row_info.get('paddock', ''))} · {esc(row_info.get('row', ''))} · {esc(row_info.get('total_length', ''))}</div>
      <div class="row-bar-visual">{''.join(bars)}</div>
      <div class="row-bar-scale"><span>0m</span><span>{esc(row_info.get('total_length', ''))}</span></div>
    </div>"""


def render_section_tabs(row_info, sections_data, active_section_id, base_url=""):
    """Render the section tab navigation."""
    tabs = []
    for sid in row_info.get("sections", []):
        sec = sections_data.get(sid, {})
        active = sid == active_section_id
        cls = "tab-active" if active else ""
        href = f'{base_url}{sid}.html'
        tabs.append(f'<a href="{href}" class="section-tab {cls}">{esc(sec.get("range", sid))}</a>')
    return f'<div class="section-tabs">{"".join(tabs)}</div>'


def render_section_page(section_id, section, row_info, sections_data, plant_db, base_url=""):
    """Render a complete section landing page."""
    
    all_plants = section.get("plants", [])
    has_trees = section.get("has_trees", False)

    # Show plants with positive counts OR not-yet-inventoried (count=None)
    # Exclude only confirmed dead (count=0)
    plants_to_show = [p for p in all_plants if p.get("count") is None or (p.get("count") or 0) > 0]

    # Fill in missing strata from plant_db
    for p in plants_to_show:
        if not p.get("strata") and p["species"] in plant_db:
            p["strata"] = plant_db[p["species"]].get("strata", "low")

    # Separate green manure (temporary cover crops) from regular plants
    regular_plants = [p for p in plants_to_show if not is_green_manure(p["species"], plant_db)]
    green_manure_plants = [p for p in plants_to_show if is_green_manure(p["species"], plant_db)]

    # Also include green manure from the dedicated green_manure array in sections.json
    gm_array = section.get("green_manure", [])
    if gm_array:
        # Add species not already in the green_manure_plants list
        existing_gm_species = {p["species"] for p in green_manure_plants}
        for gm in gm_array:
            if gm["species"] not in existing_gm_species:
                green_manure_plants.append({"species": gm["species"], "count": None})
                existing_gm_species.add(gm["species"])

    # Group regular plants by strata
    grouped = {}
    for sk in ["emergent", "high", "medium", "low"]:
        matching = [p for p in regular_plants if p.get("strata") == sk]
        if matching:
            grouped[sk] = matching

    # Stats (exclude green manure from counts)
    alive_species = len(regular_plants)
    total_plants = sum(p.get("count") or 0 for p in regular_plants)
    
    # Header gradient
    grad = "linear-gradient(145deg, #1a3a0a 0%, #2d5016 60%, #3d6a20 100%)" if has_trees else "linear-gradient(145deg, #5a8c2a 0%, #7ab33e 60%, #8bb85a 100%)"
    section_type = "🌳 Tree Section" if has_trees else "☀️ Open Cultivation"
    
    strata_html = "\n".join(render_strata_group(sk, ps, plant_db) for sk, ps in grouped.items())
    green_manure_html = render_green_manure_box(green_manure_plants)
    row_bar_html = render_row_bar(row_info, sections_data, section_id, base_url)
    tabs_html = render_section_tabs(row_info, sections_data, section_id, base_url)
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>{esc(section_id)} — Firefly Corner Farm</title>
<meta name="description" content="Syntropic polyculture section {esc(section.get('range',''))} at Firefly Corner Farm, Krambach NSW">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600;700&family=DM+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{base_url}styles.css">
</head>
<body>
<div class="page">

  <div class="section-header" style="background:{grad}">
    <a href="index.html" class="home-btn" title="Farm Guide"><img src="logo-sm.png" alt="Home"></a>
    <div class="breadcrumb">Firefly Corner · {esc(row_info.get('paddock',''))} · {esc(row_info.get('row',''))}</div>
    <div class="section-title-row">
      <h1 class="section-range">{esc(section.get('range', ''))}</h1>
      <span class="section-type-badge">{section_type}</span>
    </div>
    <div class="section-stats">
      <div class="stat"><div class="stat-value">{alive_species}</div><div class="stat-label">species</div></div>
      <div class="stat"><div class="stat-value">{total_plants}</div><div class="stat-label">plants counted</div></div>
      <div class="stat"><div class="stat-value">{esc(section.get('length', ''))}</div><div class="stat-label">length</div></div>
    </div>
  </div>

  {row_bar_html}
  {tabs_html}

  <div class="plant-inventory">
    {strata_html}
  </div>

  {green_manure_html}

  <div class="explainer-toggle" onclick="document.getElementById('explainer').classList.toggle('open')">
    <span class="explainer-title">🌿 What is Syntropic Agriculture?</span>
    <span class="explainer-arrow">▾</span>
  </div>
  <div id="explainer" class="explainer-content">
    <p>Syntropic agriculture mimics natural forest ecosystems by layering plants at different heights. Instead of clearing land for monocultures, we build <strong>stacked polycultures</strong> where every species has a role — fixing nitrogen, producing biomass, attracting pollinators, or feeding people.</p>
  </div>

  <div class="footer">
    <div>Last inventory: {esc(section.get('inventory_date', 'N/A'))} · First planted: {esc(section.get('first_planted', ''))}</div>
    <div class="footer-sub">Firefly Corner Farm · Krambach, NSW · Syntropic Agroforestry</div>
  </div>

  <a href="{base_url}{section_id}-observe.html" class="observe-fab">
    <span class="observe-fab-icon">📋</span>
    <span>Record Observation</span>
  </a>

</div>
</body>
</html>"""


def get_css():
    """Return the shared CSS for all pages."""
    return """
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'DM Sans', 'Helvetica Neue', sans-serif; background: #f0f0ec; }
.page { max-width: 430px; margin: 0 auto; background: #fff; min-height: 100vh; box-shadow: 0 0 60px rgba(0,0,0,0.06); }

/* Header */
.section-header { padding: 20px 20px 18px; color: #fff; position: relative; }
.breadcrumb { font-size: 11px; font-weight: 500; letter-spacing: 0.08em; opacity: 0.75; margin-bottom: 6px; }
.section-title-row { display: flex; align-items: baseline; gap: 10px; }
.section-range { font-family: 'Playfair Display', Georgia, serif; font-size: 30px; font-weight: 700; line-height: 1; }
.section-type-badge { padding: 3px 10px; border-radius: 5px; font-size: 11px; font-weight: 600; background: rgba(255,255,255,0.18); }
.section-stats { display: flex; gap: 20px; margin-top: 14px; }
.stat-value { font-size: 22px; font-weight: 700; }
.stat-label { font-size: 10px; opacity: 0.65; text-transform: uppercase; letter-spacing: 0.04em; }

/* Row bar */
.row-bar { padding: 12px 16px; background: #f7f6f0; border-bottom: 1px solid #e5e5e0; }
.row-bar-label { font-size: 11px; font-weight: 600; color: #999; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 6px; }
.row-bar-visual { display: flex; gap: 2px; border-radius: 6px; overflow: hidden; }
.rowbar-section { height: 36px; display: flex; align-items: center; justify-content: center; text-decoration: none; font-size: 9px; transition: opacity 0.2s; }
.row-bar-scale { display: flex; justify-content: space-between; margin-top: 3px; font-size: 10px; color: #bbb; }

/* Section tabs */
.section-tabs { display: flex; overflow-x: auto; background: #fff; border-bottom: 1px solid #e5e5e0; position: sticky; top: 0; z-index: 20; -webkit-overflow-scrolling: touch; }
.section-tab { padding: 9px 12px; font-size: 11px; font-weight: 400; color: #bbb; text-decoration: none; white-space: nowrap; flex-shrink: 0; border-bottom: 2px solid transparent; margin-bottom: -1px; font-family: 'DM Sans', sans-serif; }
.section-tab.tab-active { font-weight: 700; color: #2d5016; border-bottom-color: #2d5016; }

/* Strata groups */
.strata-group { margin-bottom: 2px; }
.strata-header { display: flex; align-items: center; gap: 8px; padding: 10px 16px; border-bottom: 2px solid; }
.strata-icon { font-size: 20px; }
.strata-name { font-weight: 700; font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; }
.strata-height { font-size: 11px; color: #aaa; margin-left: 8px; }
.strata-count { margin-left: auto; color: #fff; font-size: 11px; font-weight: 700; padding: 2px 10px; border-radius: 10px; }
.strata-plants { display: flex; flex-direction: column; gap: 1px; background: #f0f0ec; }

/* Plant cards */
.plant-card { padding: 14px 16px; background: #fff; cursor: pointer; border-left: 3px solid; transition: background 0.15s; }
.plant-header { display: flex; justify-content: space-between; align-items: flex-start; }
.plant-info { flex: 1; min-width: 0; }
.plant-name { font-family: 'Playfair Display', Georgia, serif; font-size: 16px; font-weight: 600; color: #1a1a1a; line-height: 1.2; }
.plant-botanical { font-style: italic; font-size: 13px; color: #8b8b8b; margin-top: 1px; }
.plant-count { font-weight: 700; font-size: 15px; padding: 2px 10px; border-radius: 12px; min-width: 28px; text-align: center; flex-shrink: 0; margin-left: 8px; }
.plant-photo { width: 56px; height: 56px; border-radius: 8px; object-fit: cover; flex-shrink: 0; margin-right: 12px; background: #f0ece4; border: 1px solid #e5e1d7; }
.plant-notes { font-size: 12px; color: #aaa; margin-top: 4px; }
.plant-tags-collapsed { display: flex; flex-wrap: wrap; gap: 3px; margin-top: 6px; }
.plant-detail { display: none; margin-top: 12px; padding-top: 12px; border-top: 1px solid #f0f0ec; }
.plant-card.expanded .plant-detail { display: block; }
.plant-card.expanded .plant-tags-collapsed { display: none; }
.plant-desc { font-size: 13px; color: #4b5563; line-height: 1.55; margin-bottom: 10px; }
.plant-meta { font-size: 12px; color: #7b7b7b; margin-bottom: 10px; }
.plant-tags-expanded { display: flex; flex-wrap: wrap; gap: 4px; }

/* Function tags */
.fn-tag { display: inline-flex; align-items: center; gap: 3px; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 500; white-space: nowrap; }
.fn-more { font-size: 11px; color: #bbb; padding: 2px 4px; }

/* Planted date */
.plant-planted { font-size: 11px; color: #9ca3af; margin-top: 1px; }

/* Succession */
.succession-tag { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 6px; font-size: 11px; font-weight: 600; margin-bottom: 10px; }
.succ-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }

/* Log timeline */
.log-timeline { margin-top: 12px; padding-top: 10px; border-top: 1px solid #f0f0ec; }
.log-timeline-title { font-size: 10px; font-weight: 600; color: #9ca3af; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 6px; }
.log-entry { display: flex; align-items: center; gap: 6px; padding: 3px 0; font-size: 12px; color: #6b7280; }
.log-icon { font-size: 13px; flex-shrink: 0; }
.log-date { font-weight: 500; min-width: 65px; color: #4b5563; }
.log-type { color: #9ca3af; }

/* Explainer */
.explainer-toggle { margin: 16px; padding: 12px 16px; background: #f7f6f0; border-radius: 10px 10px 0 0; cursor: pointer; display: flex; justify-content: space-between; align-items: center; border: 1px solid #e5e5e0; border-bottom: none; }
.explainer-title { font-family: 'Playfair Display', Georgia, serif; font-size: 15px; font-weight: 600; color: #1a1a1a; }
.explainer-arrow { font-size: 18px; color: #999; transition: transform 0.2s; }
.explainer-content { display: none; margin: 0 16px 16px; padding: 0 16px 16px; background: #f7f6f0; border-radius: 0 0 10px 10px; border: 1px solid #e5e5e0; border-top: none; }
.explainer-content.open { display: block; }
.explainer-content p { font-size: 13px; color: #555; line-height: 1.6; padding-top: 4px; }

/* Green manure */
.green-manure-box { margin: 12px 16px; padding: 14px 16px; background: #f0f7e8; border: 1px solid #d4e6c3; border-radius: 10px; }
.gm-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.gm-icon { font-size: 18px; }
.gm-title { font-family: 'Playfair Display', Georgia, serif; font-size: 14px; font-weight: 600; color: #3d6a20; }
.gm-species { font-size: 13px; color: #2d5016; font-weight: 500; line-height: 1.5; }
.gm-desc { font-size: 11px; color: #6b8f5a; margin-top: 6px; line-height: 1.5; }

/* Footer */
.footer { padding: 16px 16px 24px; text-align: center; font-size: 11px; color: #bbb; }
.footer-sub { color: #d4d4cc; margin-top: 4px; }

/* Index page */
.idx-header { background: linear-gradient(145deg, #1a3a0a 0%, #2d5016 60%, #3d6a20 100%); padding: 28px 20px 24px; color: #fff; }
.idx-header h1 { font-family: 'Playfair Display', Georgia, serif; font-size: 26px; font-weight: 700; }
.idx-header p { font-size: 13px; opacity: 0.8; margin-top: 6px; line-height: 1.5; }
.idx-row { padding: 20px 16px; border-bottom: 1px solid #e5e5e0; }
.idx-row-title { font-family: 'Playfair Display', Georgia, serif; font-size: 20px; font-weight: 600; color: #1a1a1a; }
.idx-row-meta { font-size: 12px; color: #999; margin-top: 2px; }
.idx-sections { display: flex; flex-direction: column; gap: 6px; margin-top: 12px; }
.idx-section { display: flex; align-items: center; gap: 8px; padding: 10px 14px; background: #f7f6f0; border-radius: 8px; text-decoration: none; color: #1a1a1a; font-size: 14px; font-weight: 500; transition: background 0.15s; }
.idx-section:hover { background: #eeeddf; }
.idx-count { margin-left: auto; font-size: 11px; color: #999; font-weight: 400; }
.idx-footer { padding: 20px 16px; text-align: center; font-size: 11px; color: #bbb; }

/* Observe FAB */
.observe-fab { position: fixed; bottom: 24px; right: max(24px, calc((100vw - 430px)/2 + 16px)); background: #e67e22; color: #fff; padding: 12px 20px; border-radius: 28px; text-decoration: none; font-weight: 600; font-size: 13px; font-family: 'DM Sans', sans-serif; box-shadow: 0 4px 16px rgba(0,0,0,0.25); display: flex; align-items: center; gap: 8px; z-index: 100; transition: transform 0.15s, box-shadow 0.15s; }
.observe-fab:active { transform: scale(0.95); box-shadow: 0 2px 8px rgba(0,0,0,0.2); }
.observe-fab-icon { font-size: 16px; }

/* Home button */
.home-btn {
  position: absolute; top: 14px; right: 14px; z-index: 30;
  width: 34px; height: 34px; border-radius: 50%;
  background: rgba(255,255,255,0.2); backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
  text-decoration: none; transition: background 0.15s;
  overflow: hidden; border: 1.5px solid rgba(255,255,255,0.3);
}
.home-btn:hover { background: rgba(255,255,255,0.35); }
.home-btn:active { transform: scale(0.92); }
.home-btn img { width: 100%; height: 100%; object-fit: cover; border-radius: 50%; }
"""


def render_observe_page(section_id, section, row_info, plant_db, observe_endpoint="", base_url=""):
    """Render the observation form page for a section."""
    has_trees = section.get("has_trees", False)
    grad = "linear-gradient(145deg, #7a4a1a 0%, #b86e2a 60%, #d4872e 100%)" if has_trees else "linear-gradient(145deg, #b86e2a 0%, #d4872e 60%, #e6a040 100%)"
    section_type = "🌳 Tree Section" if has_trees else "☀️ Open Cultivation"

    all_plants = section.get("plants", [])
    # Include plants with counts OR not-yet-inventoried for the form
    plants_to_show = [p for p in all_plants if p.get("count") is None or (p.get("count") or 0) > 0]
    # Fill in missing strata from plant_db
    for p in plants_to_show:
        if not p.get("strata") and p["species"] in plant_db:
            p["strata"] = plant_db[p["species"]].get("strata", "low")
    regular_plants = [p for p in plants_to_show if not is_green_manure(p["species"], plant_db)]

    # Build species options for quick mode dropdown
    species_seen = set()
    species_options = '<option value="">— Select species —</option>'
    for p in regular_plants:
        if p["species"] not in species_seen:
            species_seen.add(p["species"])
            count_display = p.get("count") if p.get("count") is not None else "—"
            species_options += f'<option value="{esc(p["species"])}">{esc(p["species"])} ({count_display})</option>'
    # Add Unknown Plant option
    species_options += '<option value="Unknown">❓ Unknown Plant</option>'

    # Build full inventory rows grouped by strata
    inventory_html = ""
    for strata_key in ["emergent", "high", "medium", "low"]:
        matching = [p for p in regular_plants if p.get("strata") == strata_key]
        if not matching:
            continue
        st = STRATA_CONFIG.get(strata_key, STRATA_CONFIG["medium"])
        rows_html = ""
        for p in matching:
            species = p["species"]
            count = p.get("count", 0)
            botanical = plant_db.get(species, {}).get("botanical", "")
            display_count = count if count is not None else "—"
            data_count = count if count is not None else ""
            rows_html += f"""
            <div class="inv-plant-row" data-species="{esc(species)}" data-strata="{esc(strata_key)}" data-current="{data_count}">
              <div class="inv-plant-info">
                <div class="inv-plant-name">{esc(species)}</div>
                <div class="inv-plant-botanical">{esc(botanical)}</div>
              </div>
              <div class="inv-fields">
                <div class="inv-was">
                  <label>Was</label>
                  <span class="inv-prev-count">{display_count}</span>
                </div>
                <div class="inv-now">
                  <label>Now</label>
                  <input type="number" inputmode="numeric" min="0" step="1"
                         class="inv-count-input" placeholder="—" aria-label="New count for {esc(species)}">
                </div>
                <select class="inv-condition" aria-label="Condition of {esc(species)}">
                  <option value="alive">OK</option>
                  <option value="damaged">⚠️</option>
                  <option value="dead">✝</option>
                </select>
              </div>
              <input type="text" class="inv-note-input" placeholder="Notes..." aria-label="Notes for {esc(species)}">
            </div>"""

        inventory_html += f"""
        <div class="inv-strata-group">
          <div class="inv-strata-header" style="background:{st['light']};border-left:3px solid {st['color']}">
            <span>{st['icon']}</span>
            <span class="inv-strata-name" style="color:{st['color']}">{st['label']}</span>
            <span class="inv-strata-count">{len(matching)}</span>
          </div>
          {rows_html}
        </div>"""

    # Build embedded section data as JSON for JS
    section_plants_json = json.dumps([
        {"species": p["species"], "strata": p.get("strata", ""), "count": p.get("count")}
        for p in regular_plants
    ])

    # Build plant types data for "Add New Plant" search (all species from plant_types.csv)
    plant_types_json = json.dumps([
        {"species": name, "strata": info.get("strata", "low"), "botanical": info.get("botanical", "")}
        for name, info in sorted(plant_db.items())
        if not name.startswith("[ARCHIVED]")
    ])

    endpoint_js = f'const OBSERVE_ENDPOINT = "{observe_endpoint}";' if observe_endpoint else 'const OBSERVE_ENDPOINT = "";'

    # PlantNet API key — optional. If unset, the "What is this plant?"
    # button is hidden at runtime. Free tier at https://my.plantnet.org/
    # (500 requests/day, CORS-enabled so we can call it directly from the
    # browser). The key is injected at build time as a string literal.
    plantnet_key = os.environ.get("PLANTNET_API_KEY", "").strip()
    plantnet_js = f'const PLANTNET_API_KEY = "{plantnet_key}";'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>{esc(section_id)} — Field Observation</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600;700&family=DM+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{base_url}styles.css">
<link rel="stylesheet" href="{base_url}styles-observe.css">
</head>
<body>
<div class="page">

  <div class="section-header" style="background:{grad}">
    <a href="index.html" class="home-btn" title="Farm Guide"><img src="logo-sm.png" alt="Home"></a>
    <div class="breadcrumb">Firefly Corner · {esc(row_info.get('paddock',''))} · {esc(row_info.get('row',''))} · Field Observation</div>
    <div class="section-title-row">
      <h1 class="section-range">{esc(section.get('range', ''))}</h1>
      <span class="section-type-badge">{section_type}</span>
    </div>
    <div class="obs-subtitle">Recording observation for section {esc(section_id)}</div>
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
    <button class="mode-tab active" data-mode="quick">⚡ Quick Report</button>
    <button class="mode-tab" data-mode="inventory">📋 Full Inventory</button>
    <button class="mode-tab" data-mode="comment">💬 Section Note</button>
  </div>

  <!-- QUICK MODE -->
  <div id="mode-quick" class="obs-mode-panel">
    <div class="obs-form-section">
      <div class="obs-field-group">
        <label class="obs-label" for="quick-species">Plant species</label>
        <select id="quick-species" class="obs-select">{species_options}</select>
      </div>

      <div id="quick-plant-info" class="quick-plant-info"></div>

      <div class="obs-field-row">
        <div class="obs-field-group obs-field-small">
          <label class="obs-label" for="quick-count">New count</label>
          <input type="number" id="quick-count" class="obs-input obs-input-number" inputmode="numeric" min="0" placeholder="—">
        </div>
        <div class="obs-field-group obs-field-small">
          <label class="obs-label" for="quick-condition">Condition</label>
          <select id="quick-condition" class="obs-select">
            <option value="alive">Alive ✓</option>
            <option value="damaged">Damaged ⚠️</option>
            <option value="dead">Dead ✝</option>
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
          <span>📷 Add Photo</span>
        </label>
        <div class="obs-photo-previews"></div>
      </div>

      <div class="obs-field-group">
        <label class="obs-label" for="section-notes-quick">Section notes (optional)</label>
        <textarea id="section-notes-quick" class="obs-textarea" rows="2" placeholder="General observations about this section..."></textarea>
      </div>

      <button id="quick-submit" class="obs-submit-btn">Save Observation</button>
      <button id="add-plant-btn-quick" class="add-plant-trigger" onclick="showAddPlantPanel()">➕ Add New Plant to Section</button>
    </div>
  </div>

  <!-- FULL INVENTORY MODE -->
  <div id="mode-inventory" class="obs-mode-panel" style="display:none">
    <div class="obs-form-section">
      <p class="obs-hint">Walk the section and update counts. Only changed plants will be recorded.</p>

      {inventory_html}

      <!-- Photo capture -->
      <div class="obs-media-area">
        <label class="obs-media-btn">
          <input type="file" accept="image/*" capture="environment" class="obs-photo-input" data-target="section" hidden>
          <span>📷 Add Section Photo</span>
        </label>
        <div class="obs-photo-previews"></div>
      </div>

      <div class="obs-field-group">
        <label class="obs-label" for="section-notes-inventory">Section notes</label>
        <textarea id="section-notes-inventory" class="obs-textarea" rows="3" placeholder="Overall section health, weed pressure, weather conditions..."></textarea>
      </div>

      <button id="inventory-submit" class="obs-submit-btn">Save Full Inventory</button>
      <button id="add-plant-btn-inv" class="add-plant-trigger" onclick="showAddPlantPanel()">➕ Add New Plant to Section</button>
    </div>
  </div>

  <!-- SECTION COMMENT MODE -->
  <div id="mode-comment" class="obs-mode-panel" style="display:none">
    <div class="obs-form-section">
      <p class="obs-hint">Leave a general note about this section — no plant selection needed.</p>

      <div class="obs-field-group">
        <label class="obs-label" for="comment-notes">Section notes</label>
        <textarea id="comment-notes" class="obs-textarea" rows="4" placeholder="Overall section health, weed pressure, weather conditions, general observations..."></textarea>
      </div>

      <!-- Photo capture -->
      <div class="obs-media-area">
        <label class="obs-media-btn">
          <input type="file" accept="image/*" capture="environment" class="obs-photo-input" data-target="section" hidden>
          <span>📷 Add Section Photo</span>
        </label>
        <div class="obs-photo-previews"></div>
      </div>

      <button id="comment-submit" class="obs-submit-btn">Save Section Note</button>
    </div>
  </div>

  <!-- ADD NEW PLANT (hidden until triggered) -->
  <div id="add-plant-panel" class="obs-form-section" style="display:none">
    <div class="add-plant-header">
      <span class="obs-label">Add New Plant to Section</span>
      <button id="add-plant-close" class="add-plant-close-btn">✕</button>
    </div>
    <div class="obs-field-group">
      <input type="text" id="plant-search" class="obs-input" placeholder="Search plant types..." autocomplete="off">
      <div id="plant-search-results" class="plant-search-results"></div>
    </div>
    <div class="obs-field-group" id="plantnet-section" style="display:none">
      <label class="obs-media-btn plantnet-btn">
        <input type="file" accept="image/*" capture="environment" id="plantnet-photo-input" hidden>
        <span>🪴 What is this plant? (camera)</span>
      </label>
      <div id="plantnet-results" class="plantnet-results"></div>
    </div>
    <div id="new-plant-fields" style="display:none">
      <div class="obs-field-row">
        <div class="obs-field-group obs-field-small">
          <label class="obs-label">Species</label>
          <div id="new-plant-species" class="new-plant-display"></div>
        </div>
        <div class="obs-field-group obs-field-small">
          <label class="obs-label">Strata</label>
          <div id="new-plant-strata" class="new-plant-display"></div>
        </div>
      </div>
      <div class="obs-field-row">
        <div class="obs-field-group obs-field-small">
          <label class="obs-label" for="new-plant-count">Count</label>
          <input type="number" id="new-plant-count" class="obs-input obs-input-number" inputmode="numeric" min="0" placeholder="—">
        </div>
        <div class="obs-field-group obs-field-small">
          <label class="obs-label" for="new-plant-condition">Condition</label>
          <select id="new-plant-condition" class="obs-select">
            <option value="alive">Alive ✓</option>
            <option value="damaged">Damaged ⚠️</option>
          </select>
        </div>
      </div>
      <div class="obs-field-group">
        <label class="obs-label" for="new-plant-notes">Notes</label>
        <input type="text" id="new-plant-notes" class="obs-input" placeholder="When planted, description, etc.">
      </div>
      <button id="new-plant-submit" class="obs-submit-btn">Save New Plant Observation</button>
    </div>
  </div>

  <!-- Status messages -->
  <div id="obs-status" class="obs-status" style="display:none"></div>

  <!-- Navigation -->
  <div class="obs-nav">
    <a href="{base_url}{section_id}.html" class="obs-back-link">← Back to section view</a>
  </div>

  <div class="footer">
    <div>Last inventory: {esc(section.get('inventory_date', 'N/A'))}</div>
    <div class="footer-sub">Firefly Corner Farm · Field Observation System</div>
  </div>

</div>

<script>
const SECTION_DATA = {{
  id: "{section_id}",
  range: "{esc(section.get('range', ''))}",
  paddock: {section.get('paddock', 0)},
  row: {section.get('row', 0)},
  plants: {section_plants_json}
}};
const PLANT_TYPES_DATA = {plant_types_json};
{endpoint_js}
{plantnet_js}
</script>
<script src="{base_url}observe.js"></script>
</body>
</html>"""


def get_observe_css():
    """Return CSS for observation pages."""
    return """
/* Observation page styles — extends base styles.css */

.obs-subtitle { font-size: 13px; opacity: 0.8; margin-top: 8px; }

/* Queue banner */
.queue-banner { display: flex; align-items: center; justify-content: space-between; padding: 10px 16px; background: #fef3c7; border-bottom: 1px solid #fcd34d; font-size: 13px; color: #92400e; }
.queue-sync-btn { background: #f59e0b; color: #fff; border: none; padding: 6px 14px; border-radius: 6px; font-size: 12px; font-weight: 600; cursor: pointer; font-family: 'DM Sans', sans-serif; }

/* Form sections */
.obs-form-section { padding: 16px; }
.obs-field-group { margin-bottom: 14px; }
.obs-field-row { display: flex; gap: 12px; }
.obs-field-small { flex: 1; }
.obs-label { display: block; font-size: 11px; font-weight: 600; color: #6b7280; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 4px; }
.obs-input, .obs-select, .obs-textarea { width: 100%; padding: 10px 12px; border: 1px solid #d1d5db; border-radius: 8px; font-size: 15px; font-family: 'DM Sans', sans-serif; background: #fff; color: #1a1a1a; -webkit-appearance: none; appearance: none; }
.obs-input:focus, .obs-select:focus, .obs-textarea:focus { outline: none; border-color: #e67e22; box-shadow: 0 0 0 3px rgba(230, 126, 34, 0.15); }
.obs-input-number { width: 80px; text-align: center; font-weight: 600; font-size: 18px; }
.obs-textarea { resize: vertical; min-height: 48px; }
.obs-hint { font-size: 13px; color: #9ca3af; margin-bottom: 16px; line-height: 1.5; }

/* Mode toggle */
.mode-toggle { display: flex; border-bottom: 1px solid #e5e5e0; }
.mode-tab { flex: 1; padding: 12px; font-size: 13px; font-weight: 600; text-align: center; background: #f7f6f0; border: none; cursor: pointer; color: #9ca3af; font-family: 'DM Sans', sans-serif; transition: all 0.15s; }
.mode-tab.active { background: #fff; color: #e67e22; box-shadow: inset 0 -2px 0 #e67e22; }

/* Quick mode plant info */
.quick-plant-info { padding: 10px 14px; background: #f7f6f0; border-radius: 8px; margin-bottom: 14px; }
.quick-info-row { display: flex; justify-content: space-between; font-size: 13px; color: #555; }
.quick-info-label { color: #9ca3af; }
.quick-info-value { font-weight: 600; }

/* Full inventory rows */
.inv-strata-group { margin-bottom: 2px; }
.inv-strata-header { display: flex; align-items: center; gap: 8px; padding: 8px 12px; font-size: 12px; font-weight: 600; }
.inv-strata-name { text-transform: uppercase; letter-spacing: 0.04em; }
.inv-strata-count { margin-left: auto; font-size: 11px; color: #9ca3af; }

.inv-plant-row { padding: 10px 14px; background: #fff; border-bottom: 1px solid #f0f0ec; }
.inv-plant-info { margin-bottom: 6px; }
.inv-plant-name { font-family: 'Playfair Display', Georgia, serif; font-size: 14px; font-weight: 600; color: #1a1a1a; }
.inv-plant-botanical { font-style: italic; font-size: 11px; color: #9ca3af; }
.inv-fields { display: flex; align-items: center; gap: 10px; margin-bottom: 4px; }
.inv-was { display: flex; flex-direction: column; align-items: center; min-width: 44px; }
.inv-was label { font-size: 9px; color: #9ca3af; text-transform: uppercase; letter-spacing: 0.04em; }
.inv-prev-count { font-size: 18px; font-weight: 700; color: #6b7280; }
.inv-now { display: flex; flex-direction: column; align-items: center; min-width: 52px; }
.inv-now label { font-size: 9px; color: #e67e22; text-transform: uppercase; letter-spacing: 0.04em; font-weight: 600; }
.inv-count-input { width: 52px; padding: 6px; border: 2px solid #e5e5e0; border-radius: 8px; font-size: 18px; font-weight: 700; text-align: center; font-family: 'DM Sans', sans-serif; color: #1a1a1a; background: #fff; }
.inv-count-input:focus { border-color: #e67e22; outline: none; box-shadow: 0 0 0 3px rgba(230, 126, 34, 0.15); }
.inv-condition { width: 48px; padding: 6px 2px; border: 1px solid #e5e5e0; border-radius: 6px; font-size: 14px; text-align: center; background: #fff; -webkit-appearance: none; }
.inv-note-input { width: 100%; padding: 6px 10px; border: 1px solid #f0f0ec; border-radius: 6px; font-size: 12px; font-family: 'DM Sans', sans-serif; color: #555; }
.inv-note-input:focus { border-color: #e67e22; outline: none; }

/* Media capture */
.obs-media-area { margin-bottom: 14px; }
.obs-media-btn { display: inline-flex; align-items: center; gap: 6px; padding: 10px 16px; background: #f7f6f0; border: 1px dashed #d1d5db; border-radius: 8px; font-size: 13px; font-weight: 500; color: #555; cursor: pointer; font-family: 'DM Sans', sans-serif; }
.obs-media-btn:active { background: #eeeddf; }
.obs-photo-previews { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.obs-photo-preview { position: relative; width: 72px; height: 72px; border-radius: 8px; overflow: hidden; border: 1px solid #e5e5e0; }
.obs-photo-preview img { width: 100%; height: 100%; object-fit: cover; }
.obs-photo-remove { position: absolute; top: 2px; right: 2px; width: 20px; height: 20px; background: rgba(0,0,0,0.6); color: #fff; border: none; border-radius: 50%; font-size: 10px; cursor: pointer; display: flex; align-items: center; justify-content: center; }

/* Submit button */
.obs-submit-btn { width: 100%; padding: 14px; background: #e67e22; color: #fff; border: none; border-radius: 10px; font-size: 15px; font-weight: 700; cursor: pointer; font-family: 'DM Sans', sans-serif; transition: background 0.15s; }
.obs-submit-btn:active { background: #d35400; }
.obs-submit-btn:disabled { background: #d1d5db; cursor: not-allowed; }

/* Status messages */
.obs-status { margin: 0 16px 12px; padding: 12px 16px; border-radius: 8px; font-size: 13px; font-weight: 500; }
.obs-status-success { background: #d1fae5; color: #065f46; border: 1px solid #6ee7b7; }
.obs-status-error { background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; }
.obs-status-offline { background: #fef3c7; color: #92400e; border: 1px solid #fcd34d; }
.obs-status-sending { background: #dbeafe; color: #1e40af; border: 1px solid #93c5fd; }

/* Add New Plant */
.add-plant-trigger { width: 100%; padding: 12px; margin-top: 10px; background: #f7f6f0; border: 2px dashed #d1d5db; border-radius: 10px; font-size: 13px; font-weight: 600; color: #6b7280; cursor: pointer; font-family: 'DM Sans', sans-serif; transition: all 0.15s; }
.add-plant-trigger:active { background: #eeeddf; border-color: #e67e22; color: #e67e22; }
.add-plant-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.add-plant-close-btn { background: none; border: none; font-size: 18px; color: #9ca3af; cursor: pointer; padding: 4px 8px; }
.plantnet-btn { margin-top: 8px; background: #2d5016; color: #fff; }
.plantnet-results { margin-top: 10px; display: flex; flex-direction: column; gap: 6px; }
.plantnet-match { display: flex; gap: 10px; padding: 8px 10px; background: #f7f6f0; border: 1px solid #e5e5e0; border-radius: 8px; cursor: pointer; align-items: center; }
.plantnet-match:hover { background: #efece0; border-color: #6b9e3c; }
.plantnet-match img { width: 48px; height: 48px; border-radius: 6px; object-fit: cover; flex-shrink: 0; }
.plantnet-match-text { flex: 1; min-width: 0; }
.plantnet-species { font-size: 13px; font-weight: 600; color: #1a1a1a; }
.plantnet-botanical { font-size: 11px; font-style: italic; color: #6b7280; }
.plantnet-confidence { font-size: 11px; font-weight: 700; color: #2d5016; }
.plantnet-status { font-size: 12px; color: #6b7280; padding: 6px 10px; }
.plant-search-results { max-height: 200px; overflow-y: auto; border: 1px solid #e5e5e0; border-radius: 8px; margin-top: 4px; display: none; }
.plant-search-result { padding: 10px 12px; cursor: pointer; border-bottom: 1px solid #f0f0ec; font-size: 13px; }
.plant-search-result:hover { background: #f7f6f0; }
.plant-search-result .search-species { font-weight: 600; color: #1a1a1a; }
.plant-search-result .search-meta { font-size: 11px; color: #9ca3af; font-style: italic; }
.new-plant-display { font-size: 14px; font-weight: 600; color: #1a1a1a; padding: 8px 0; }

/* Navigation */
.obs-nav { padding: 16px; text-align: center; }
.obs-back-link { color: #e67e22; text-decoration: none; font-size: 14px; font-weight: 500; }
"""


def main():
    parser = argparse.ArgumentParser(description="Generate static site from farm data")
    parser.add_argument("--data", default="site/src/data/sections.json", help="Path to sections.json")
    parser.add_argument("--plants", default="knowledge/plant_types.csv", help="Path to plant_types.csv")
    parser.add_argument("--output", default="site/public/", help="Output directory")
    parser.add_argument("--base-url", default="", help="Base URL prefix for links")
    parser.add_argument("--observe-endpoint", default="", help="Google Apps Script URL for observations")
    parser.add_argument("--seedbank-endpoint", default="", help="Google Apps Script URL for seed bank")
    args = parser.parse_args()
    
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("Loading plant database...")
    plant_db = load_plant_db(args.plants)
    print(f"  {len(plant_db)} plant types loaded")
    
    print("Loading section data...")
    sections, rows = load_sections(args.data)
    print(f"  {len(sections)} sections across {len(rows)} rows")
    
    # Write shared CSS files (skip if hand-managed version exists with home-btn)
    css_path = output_dir / "styles.css"
    existing_css = css_path.read_text(encoding="utf-8") if css_path.exists() else ""
    if "home-btn" not in existing_css:
        with open(css_path, "w", encoding="utf-8") as f:
            f.write(get_css())
        print(f"  Generated: styles.css")
    else:
        print(f"  Skipped: styles.css (hand-managed)")

    obs_css_path = output_dir / "styles-observe.css"
    with open(obs_css_path, "w", encoding="utf-8") as f:
        f.write(get_observe_css())
    print(f"  Generated: styles-observe.css")

    observe_endpoint = args.observe_endpoint

    # Update SEED.BANK.html endpoint if provided and file exists
    seedbank_path = output_dir / "SEED.BANK.html"
    if args.seedbank_endpoint and seedbank_path.exists():
        seedbank_html = seedbank_path.read_text(encoding="utf-8")
        # Replace any existing endpoint (placeholder or previous URL)
        import re
        seedbank_html = re.sub(
            r'data-endpoint="[^"]*"',
            f'data-endpoint="{args.seedbank_endpoint}"',
            seedbank_html
        )
        seedbank_path.write_text(seedbank_html, encoding="utf-8")
        print(f"  Updated: SEED.BANK.html endpoint")

    # Generate a page per section (view + observe)
    for section_id, section in sections.items():
        row_id = f"P{section['paddock']}R{section['row']}"
        row_info = rows.get(row_id, {})

        # View page (existing — now with observe FAB)
        page_html = render_section_page(section_id, section, row_info, sections, plant_db, args.base_url)

        output_path = output_dir / f"{section_id}.html"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(page_html)

        visible = [p for p in section.get("plants", [])
                   if (p.get("count") is None or (p.get("count") or 0) > 0)
                   and not is_green_manure(p["species"], plant_db)]
        print(f"  Generated: {section_id}.html ({len(visible)} species)")

        # Observe page (new)
        observe_html = render_observe_page(section_id, section, row_info, plant_db, observe_endpoint, args.base_url)
        obs_path = output_dir / f"{section_id}-observe.html"
        with open(obs_path, "w", encoding="utf-8") as f:
            f.write(observe_html)
        print(f"  Generated: {section_id}-observe.html")

    # Generate index page (skip if hand-managed collapsible version exists)
    idx_path = output_dir / "index.html"
    existing_idx = idx_path.read_text(encoding="utf-8") if idx_path.exists() else ""
    if "toggleLocation" not in existing_idx:
        index_html = render_index(rows, sections, plant_db, args.base_url)
        with open(idx_path, "w", encoding="utf-8") as f:
            f.write(index_html)
        print(f"  Generated: index.html")
    else:
        print(f"  Skipped: index.html (hand-managed)")

    total = len(sections) * 2 + 1  # view + observe + index
    print(f"\nDone! {total} pages in {output_dir} ({len(sections)} view + {len(sections)} observe + index)")


def render_index(rows, sections, plant_db, base_url=""):
    """Simple index page listing all rows and their sections."""
    rows_html = ""
    for row_id in sorted(rows.keys()):
        row = rows[row_id]
        secs_html = ""
        for sid in row.get("sections", []):
            sec = sections.get(sid, {})
            icon = "🌳" if sec.get("has_trees") else "☀️"
            visible = [p for p in sec.get("plants", [])
                       if (p.get("count") is None or (p.get("count") or 0) > 0)
                       and not is_green_manure(p["species"], plant_db)]
            n_species = len(visible)
            secs_html += f'<a href="{base_url}{sid}.html" class="idx-section">{icon} {esc(sec.get("range", sid))}<span class="idx-count">{n_species} species</span></a>'
        rows_html += f"""
        <div class="idx-row">
          <h2 class="idx-row-title">{esc(row.get('paddock',''))} · {esc(row.get('row',''))}</h2>
          <div class="idx-row-meta">{esc(row.get('total_length',''))} · {len(row.get('sections',[]))} sections · Est. {esc(row.get('first_planted',''))}</div>
          <div class="idx-sections">{secs_html}</div>
        </div>"""
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Firefly Corner Farm — Paddock Guide</title>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600;700&family=DM+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{base_url}styles.css">
</head>
<body>
<div class="page">
  <div class="idx-header">
    <h1>Firefly Corner Farm</h1>
    <p>Syntropic agroforestry paddock guide. Scan a QR code on any row section pole, or browse below.</p>
  </div>
  {rows_html}
  <div class="idx-tools">
    <h2 class="idx-row-title">🧰 Farm Tools</h2>
    <div class="idx-sections">
      <a href="{base_url}SEED.BANK.html" class="idx-section">🌱 Seed Bank<span class="idx-count">inventory &amp; transactions</span></a>
    </div>
  </div>
  <div class="idx-footer">Firefly Corner Farm · Krambach, NSW · Syntropic Agroforestry</div>
</div>
</body>
</html>"""


if __name__ == "__main__":
    main()
