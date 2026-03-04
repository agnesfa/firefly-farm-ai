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
    """Load plant types CSV into a lookup dict keyed by common_name."""
    plants = {}
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("common_name", "").strip()
            if name:
                plants[name] = {
                    "botanical": row.get("botanical_name", ""),
                    "family": row.get("crop_family", ""),
                    "origin": row.get("origin", ""),
                    "description": row.get("description", ""),
                    "lifespan": row.get("lifespan", ""),
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


def render_function_tag(fn):
    fn_key = fn.strip().lower()
    emoji, bg, fg = FUNCTION_STYLES.get(fn_key, ("•", "#f3f4f6", "#374151"))
    return f'<span class="fn-tag" style="background:{bg};color:{fg}">{emoji} {esc(fn)}</span>'


def render_plant_card(planting, plant_db):
    """Render a single plant card HTML."""
    species = planting["species"]
    strata = planting["strata"]
    count = planting.get("count")
    notes = planting.get("notes", "")
    
    plant = plant_db.get(species, {})
    st = STRATA_CONFIG.get(strata, STRATA_CONFIG["medium"])
    
    dead = "all dead" in (notes or "").lower() or count == 0
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
    
    dead_class = " plant-dead" if dead else ""
    dead_marker = ' <span class="dead-marker">✝ lost</span>' if dead else ""
    notes_html = f'<div class="plant-notes">{esc(notes)}</div>' if notes and not dead else ""
    
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
    
    return f"""
    <div class="plant-card{dead_class}" style="border-left-color:{st['color'] if not dead else '#d1d5db'}" onclick="this.classList.toggle('expanded')">
      <div class="plant-header">
        <div class="plant-info">
          <div class="plant-name">{esc(species)}{dead_marker}</div>
          <div class="plant-botanical">{esc(botanical)}</div>
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
      </div>
    </div>"""


def render_strata_group(strata_key, plants, plant_db):
    """Render a strata group with all its plants."""
    st = STRATA_CONFIG.get(strata_key)
    if not st:
        return ""
    
    alive_count = sum(p.get("count", 0) or 0 for p in plants if (p.get("count") or 0) > 0)
    count_badge = f'<span class="strata-count" style="background:{st["color"]}">{alive_count}</span>' if alive_count > 0 else ""
    
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
    
    plants = section.get("plants", [])
    has_trees = section.get("has_trees", False)
    
    # Group by strata
    grouped = {}
    for sk in ["emergent", "high", "medium", "low"]:
        matching = [p for p in plants if p.get("strata") == sk]
        if matching:
            grouped[sk] = matching
    
    # Stats
    alive_species = len([p for p in plants if p.get("count") is None or p.get("count", 0) > 0])
    total_plants = sum(p.get("count", 0) or 0 for p in plants if (p.get("count") or 0) > 0)
    
    # Header gradient
    grad = "linear-gradient(145deg, #1a3a0a 0%, #2d5016 60%, #3d6a20 100%)" if has_trees else "linear-gradient(145deg, #5a8c2a 0%, #7ab33e 60%, #8bb85a 100%)"
    section_type = "🌳 Tree Section" if has_trees else "☀️ Open Cultivation"
    
    strata_html = "\n".join(render_strata_group(sk, ps, plant_db) for sk, ps in grouped.items())
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
<style>
{get_css()}
</style>
</head>
<body>
<div class="page">

  <div class="section-header" style="background:{grad}">
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
.section-header { padding: 20px 20px 18px; color: #fff; }
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
.plant-card.plant-dead { background: #fafafa; opacity: 0.55; }
.plant-header { display: flex; justify-content: space-between; align-items: flex-start; }
.plant-info { flex: 1; min-width: 0; }
.plant-name { font-family: 'Playfair Display', Georgia, serif; font-size: 16px; font-weight: 600; color: #1a1a1a; line-height: 1.2; }
.dead-marker { font-size: 11px; color: #b0b0b0; margin-left: 8px; font-family: 'DM Sans', sans-serif; }
.plant-botanical { font-style: italic; font-size: 13px; color: #8b8b8b; margin-top: 1px; }
.plant-count { font-weight: 700; font-size: 15px; padding: 2px 10px; border-radius: 12px; min-width: 28px; text-align: center; flex-shrink: 0; margin-left: 8px; }
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

/* Succession */
.succession-tag { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 6px; font-size: 11px; font-weight: 600; margin-bottom: 10px; }
.succ-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }

/* Explainer */
.explainer-toggle { margin: 16px; padding: 12px 16px; background: #f7f6f0; border-radius: 10px 10px 0 0; cursor: pointer; display: flex; justify-content: space-between; align-items: center; border: 1px solid #e5e5e0; border-bottom: none; }
.explainer-title { font-family: 'Playfair Display', Georgia, serif; font-size: 15px; font-weight: 600; color: #1a1a1a; }
.explainer-arrow { font-size: 18px; color: #999; transition: transform 0.2s; }
.explainer-content { display: none; margin: 0 16px 16px; padding: 0 16px 16px; background: #f7f6f0; border-radius: 0 0 10px 10px; border: 1px solid #e5e5e0; border-top: none; }
.explainer-content.open { display: block; }
.explainer-content p { font-size: 13px; color: #555; line-height: 1.6; padding-top: 4px; }

/* Footer */
.footer { padding: 16px 16px 24px; text-align: center; font-size: 11px; color: #bbb; }
.footer-sub { color: #d4d4cc; margin-top: 4px; }
"""


def main():
    parser = argparse.ArgumentParser(description="Generate static site from farm data")
    parser.add_argument("--data", default="site/src/data/sections.json", help="Path to sections.json")
    parser.add_argument("--plants", default="knowledge/plant_types.csv", help="Path to plant_types.csv")
    parser.add_argument("--output", default="site/public/", help="Output directory")
    parser.add_argument("--base-url", default="", help="Base URL prefix for links")
    args = parser.parse_args()
    
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("Loading plant database...")
    plant_db = load_plant_db(args.plants)
    print(f"  {len(plant_db)} plant types loaded")
    
    print("Loading section data...")
    sections, rows = load_sections(args.data)
    print(f"  {len(sections)} sections across {len(rows)} rows")
    
    # Generate a page per section
    for section_id, section in sections.items():
        row_id = f"P{section['paddock']}R{section['row']}"
        row_info = rows.get(row_id, {})
        
        page_html = render_section_page(section_id, section, row_info, sections, plant_db, args.base_url)
        
        output_path = output_dir / f"{section_id}.html"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(page_html)
        
        plant_count = len(section.get("plants", []))
        print(f"  Generated: {section_id}.html ({plant_count} species)")
    
    # Generate index page
    index_html = render_index(rows, sections, args.base_url)
    with open(output_dir / "index.html", "w", encoding="utf-8") as f:
        f.write(index_html)
    print(f"  Generated: index.html")
    
    print(f"\nDone! {len(sections) + 1} pages in {output_dir}")


def render_index(rows, sections, base_url=""):
    """Simple index page listing all rows and their sections."""
    rows_html = ""
    for row_id in sorted(rows.keys()):
        row = rows[row_id]
        secs_html = ""
        for sid in row.get("sections", []):
            sec = sections.get(sid, {})
            icon = "🌳" if sec.get("has_trees") else "☀️"
            n_species = len(sec.get("plants", []))
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
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:'DM Sans',sans-serif; background:#f0f0ec; }}
.page {{ max-width:430px; margin:0 auto; background:#fff; min-height:100vh; box-shadow:0 0 60px rgba(0,0,0,0.06); }}
.idx-header {{ background:linear-gradient(145deg,#1a3a0a 0%,#2d5016 60%,#3d6a20 100%); padding:28px 20px 24px; color:#fff; }}
.idx-header h1 {{ font-family:'Playfair Display',Georgia,serif; font-size:26px; font-weight:700; }}
.idx-header p {{ font-size:13px; opacity:0.8; margin-top:6px; line-height:1.5; }}
.idx-row {{ padding:20px 16px; border-bottom:1px solid #e5e5e0; }}
.idx-row-title {{ font-family:'Playfair Display',Georgia,serif; font-size:20px; font-weight:600; color:#1a1a1a; }}
.idx-row-meta {{ font-size:12px; color:#999; margin-top:2px; }}
.idx-sections {{ display:flex; flex-direction:column; gap:6px; margin-top:12px; }}
.idx-section {{ display:flex; align-items:center; gap:8px; padding:10px 14px; background:#f7f6f0; border-radius:8px; text-decoration:none; color:#1a1a1a; font-size:14px; font-weight:500; transition:background 0.15s; }}
.idx-section:hover {{ background:#eeeddf; }}
.idx-count {{ margin-left:auto; font-size:11px; color:#999; font-weight:400; }}
.idx-footer {{ padding:20px 16px; text-align:center; font-size:11px; color:#bbb; }}
</style>
</head>
<body>
<div class="page">
  <div class="idx-header">
    <h1>Firefly Corner Farm</h1>
    <p>Syntropic agroforestry paddock guide. Scan a QR code on any row section pole, or browse below.</p>
  </div>
  {rows_html}
  <div class="idx-footer">Firefly Corner Farm · Krambach, NSW · Syntropic Agroforestry</div>
</div>
</body>
</html>"""


if __name__ == "__main__":
    main()
