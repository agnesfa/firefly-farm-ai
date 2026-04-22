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
import sys
from dotenv import load_dotenv as _load_dotenv
# Load .env before argparse default values are computed — otherwise the
# OBSERVE_ENDPOINT fallback below resolves to empty and every QR observe
# page ships with the "Observation endpoint not configured" regression.
_load_dotenv()
import csv
import json
import html
import os
import re
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


def log_detail_page_name(section_id: str, log: dict) -> str:
    """Build the detail page filename for a single log.

    Uses the first 8 chars of the log UUID so filenames stay short and stable.
    """
    uuid = log.get("uuid", "")
    short = uuid.split("-")[0] if uuid else (log.get("date", "") + "-" + log.get("type", ""))
    return f"{section_id}-log-{short}.html"


def render_log_timeline(logs: list, section_id: str = "", base_url: str = "") -> str:
    """Render a compact log timeline for expanded plant card view.

    Each entry is a link to a per-log detail page showing the full farmOS
    log record with provenance (InteractionStamp). This gives Claire and
    WWOOFers a way to click through and trust what's in the data.
    """
    if not logs:
        return ""

    log_icons = {
        "transplanting": "🌱",
        "observation": "📊",
        "activity": "🔧",
        "harvest": "🧺",
        "seeding": "🌰",
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

        if log.get("uuid") and section_id:
            href = base_url + log_detail_page_name(section_id, log)
            items.append(
                f'<a class="log-entry log-entry-link" href="{esc(href)}">'
                f'<span class="log-icon">{icon}</span>'
                f'<span class="log-date">{esc(date_display)}</span>'
                f'<span class="log-type">{esc(log_type)}</span>'
                f'<span class="log-arrow">›</span>'
                f'</a>'
            )
        else:
            items.append(
                f'<div class="log-entry">'
                f'<span class="log-icon">{icon}</span>'
                f'<span class="log-date">{esc(date_display)}</span>'
                f'<span class="log-type">{esc(log_type)}</span>'
                f'</div>'
            )

    return f'<div class="log-timeline"><div class="log-timeline-title">History</div>{"".join(items)}</div>'


def parse_interaction_stamp(stamp_line: str) -> dict:
    """Parse a [ontology:InteractionStamp] line into its key=value fields."""
    out: dict = {}
    if not stamp_line or "[ontology:InteractionStamp]" not in stamp_line:
        return out
    # Strip the prefix
    body = stamp_line.split("[ontology:InteractionStamp]", 1)[1].strip()
    for part in body.split("|"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def render_log_detail_page(
    section_id: str,
    section: dict,
    row_info: dict,
    log: dict,
    plant_db: dict,
    base_url: str = "",
) -> str:
    """Render a standalone HTML page for a single farmOS log record.

    Shows: type, date, species, full notes, parsed InteractionStamp
    (initiator, role, channel, executor, action, target, outcome, ts),
    and a "back to section" link. This is the first piece of the provenance
    layer — every fact in the farm now has a URL you can click through to.
    """
    has_trees = section.get("has_trees", False)
    grad = (
        "linear-gradient(145deg, #7a4a1a 0%, #b86e2a 60%, #d4872e 100%)"
        if has_trees
        else "linear-gradient(145deg, #b86e2a 0%, #d4872e 60%, #e6a040 100%)"
    )

    species = log.get("species", "")
    log_type = log.get("type", "observation").replace("_", " ").title()
    date = log.get("date", "")
    log_name = log.get("name", "")
    notes_full = log.get("notes_full", "") or log.get("notes", "")
    uuid = log.get("uuid", "")

    # Parse the InteractionStamp if present; otherwise derive what we can from notes
    stamp_line = log.get("interaction_stamp", "")
    stamp = parse_interaction_stamp(stamp_line)

    # Strip the stamp line out of the visible notes (it's shown separately)
    visible_notes = "\n".join(
        ln for ln in notes_full.splitlines() if "[ontology:InteractionStamp]" not in ln
    ).strip()

    # Plant metadata (for context)
    plant_meta = plant_db.get(species, {})
    botanical = plant_meta.get("botanical", "")
    strata = plant_meta.get("strata", "")

    provenance_rows = ""
    if stamp:
        def row(label: str, key: str, icon: str) -> str:
            val = stamp.get(key, "")
            if not val:
                return ""
            return (
                f'<div class="prov-row">'
                f'<span class="prov-icon">{icon}</span>'
                f'<span class="prov-label">{label}:</span>'
                f'<span class="prov-value">{esc(val)}</span>'
                f'</div>'
            )
        provenance_rows = (
            row("Initiated by", "initiator", "👤")
            + row("Role", "role", "🏷")
            + row("Channel", "channel", "📡")
            + row("Executed by", "executor", "⚙️")
            + row("Action", "action", "▶")
            + row("Target", "target", "🎯")
            + row("Outcome", "outcome", "✓")
            + row("Timestamp", "ts", "🕒")
        )

    provenance_block = ""
    if provenance_rows:
        provenance_block = (
            '<div class="log-detail-section">'
            '<h3 class="log-detail-h3">Provenance</h3>'
            '<div class="prov-card">' + provenance_rows + '</div>'
            '</div>'
        )
    elif stamp_line:
        provenance_block = (
            '<div class="log-detail-section">'
            '<h3 class="log-detail-h3">Provenance</h3>'
            '<div class="prov-card prov-raw">' + esc(stamp_line) + '</div>'
            '</div>'
        )

    notes_block = ""
    if visible_notes:
        notes_html = esc(visible_notes).replace("\n", "<br>")
        notes_block = (
            '<div class="log-detail-section">'
            '<h3 class="log-detail-h3">Notes</h3>'
            '<div class="log-notes-body">' + notes_html + '</div>'
            '</div>'
        )

    # Field photos attached to the log. Each thumbnail filename has a
    # sibling -full.jpg variant for the lightbox view.
    photo_paths = log.get("photos") or []
    photos_block = ""
    if photo_paths:
        thumbs = []
        for p in photo_paths:
            full = p.replace(".jpg", "-full.jpg")
            thumbs.append(
                f'<a class="log-photo-thumb" href="{base_url}{esc(full)}" '
                f'onclick="event.preventDefault();openLogLightbox(this);">'
                f'<img src="{base_url}{esc(p)}" alt="Field photo for {esc(species)}" '
                f'loading="lazy" decoding="async">'
                f'</a>'
            )
        photos_block = (
            '<div class="log-detail-section">'
            f'<h3 class="log-detail-h3">Field photos ({len(photo_paths)})</h3>'
            '<div class="log-photo-grid">' + "".join(thumbs) + '</div>'
            '</div>'
        )

    meta_rows = (
        f'<div class="prov-row"><span class="prov-icon">📅</span><span class="prov-label">Date:</span><span class="prov-value">{esc(date)}</span></div>'
        f'<div class="prov-row"><span class="prov-icon">🏷</span><span class="prov-label">Type:</span><span class="prov-value">{esc(log_type)}</span></div>'
        f'<div class="prov-row"><span class="prov-icon">🌿</span><span class="prov-label">Species:</span><span class="prov-value">{esc(species)}{" · " + esc(botanical) if botanical else ""}</span></div>'
        + (f'<div class="prov-row"><span class="prov-icon">🌱</span><span class="prov-label">Strata:</span><span class="prov-value">{esc(strata)}</span></div>' if strata else "")
        + f'<div class="prov-row"><span class="prov-icon">📜</span><span class="prov-label">Log name:</span><span class="prov-value mono">{esc(log_name)}</span></div>'
        + (f'<div class="prov-row"><span class="prov-icon">#</span><span class="prov-label">UUID:</span><span class="prov-value mono">{esc(uuid)}</span></div>' if uuid else "")
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>{esc(species)} · {esc(date)} · {esc(section_id)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600;700&family=DM+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{base_url}styles.css">
<link rel="stylesheet" href="{base_url}styles-observe.css">
</head>
<body>
<div class="page">

  <div class="section-header" style="background:{grad}">
    <a href="index.html" class="home-btn" title="Farm Guide"><img src="logo-sm.png" alt="Home"></a>
    <div class="breadcrumb">Firefly Corner · {esc(row_info.get('paddock',''))} · {esc(row_info.get('row',''))} · Log Detail</div>
    <div class="section-title-row">
      <h1 class="section-range">{esc(section.get('range', ''))}</h1>
    </div>
    <div class="obs-subtitle">{esc(log_type)} · {esc(date)} · {esc(species)}</div>
  </div>

  <div class="log-detail-wrap">
    <div class="log-detail-section">
      <h3 class="log-detail-h3">Record</h3>
      <div class="prov-card">
        {meta_rows}
      </div>
    </div>

    {photos_block}

    {notes_block}

    {provenance_block}
  </div>

  <div id="log-lightbox" class="log-lightbox" onclick="closeLogLightbox()">
    <img src="" alt="">
  </div>

  <div class="obs-nav">
    <a href="{base_url}{section_id}.html" class="obs-back-link">← Back to section view</a>
  </div>

  <div class="footer">
    <div class="footer-sub">Firefly Corner Farm · Log Detail</div>
  </div>

</div>
<script>
  function openLogLightbox(anchor) {{
    var box = document.getElementById("log-lightbox");
    if (!box) return;
    box.querySelector("img").src = anchor.href;
    box.classList.add("open");
  }}
  function closeLogLightbox() {{
    var box = document.getElementById("log-lightbox");
    if (box) box.classList.remove("open");
  }}
  document.addEventListener("keydown", function (e) {{
    if (e.key === "Escape") closeLogLightbox();
  }});
</script>
</body>
</html>"""


def render_care_tips(plant):
    """Generate practical care tips from function tags and succession stage."""
    functions = plant.get("functions", [])
    succession = plant.get("succession", "")
    tips = []

    fn_set = set(f.lower().replace(" ", "_") for f in functions)

    if "nitrogen_fixer" in fn_set:
        tips.append(("⚡", "Chop-and-drop: cut and leave as mulch to feed the soil"))
    if "edible_fruit" in fn_set:
        tips.append(("🍎", "Produces edible fruit — check for ripe fruit regularly"))
    if "edible_nut" in fn_set:
        tips.append(("🥜", "Produces edible nuts — harvest when mature and falling"))
    if "edible_seed" in fn_set:
        tips.append(("🌾", "Produces edible seeds — harvest when pods are dry and brown"))
    if "edible_greens" in fn_set:
        tips.append(("🥬", "Edible leaves — harvest outer leaves, leave the crown to regrow"))
    if "edible_root" in fn_set:
        tips.append(("🥕", "Edible root — harvest when top growth signals maturity"))
    if "living_mulch" in fn_set:
        tips.append(("🍃", "Living mulch — do not remove, it protects the soil"))
    if "biomass_producer" in fn_set and "nitrogen_fixer" not in fn_set:
        tips.append(("♻️", "Biomass producer — prune regularly and use cuttings as mulch"))

    if succession == "pioneer":
        tips.append(("🔶", "Pioneer — short-lived by design. Expected to die back as the system matures"))
    elif succession == "climax":
        tips.append(("🌲", "Climax species — permanent. Protect from damage and give space to grow"))

    if not tips:
        return ""

    items = "".join(
        f'<div class="care-tip"><span class="care-icon">{icon}</span><span>{esc(text)}</span></div>'
        for icon, text in tips
    )
    return f'<div class="care-tips"><div class="care-tips-title">Field Guide</div>{items}</div>'


def render_plant_card(planting, plant_db, section_id="", base_url=""):
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

    # Per-plant camera button (observe shortcut)
    import urllib.parse
    observe_url = f'{base_url}{section_id}-observe.html?plant={urllib.parse.quote(species)}&camera=1'
    camera_btn_html = (
        f'<a href="{observe_url}" class="plant-observe-btn" '
        f'onclick="event.stopPropagation()" title="Record observation for {esc(species)}">'
        f'📷</a>'
    ) if section_id else ""

    # I10 — QR render hygiene: strip InteractionStamp + submission= lines
    # from asset notes (those belong on the log, not the asset per I8) and
    # truncate to 120 chars. Omit block entirely if stripped content is
    # trivial. See ADR 0008 amendment 2026-04-20.
    notes_html = ""
    if notes:
        stripped_lines = [
            ln for ln in notes.splitlines()
            if "[ontology:InteractionStamp]" not in ln
            and not ln.strip().lower().startswith("submission=")
            and not ln.strip().lower().startswith("reporter:")
            and not ln.strip().lower().startswith("submitted:")
            and not ln.strip().lower().startswith("mode:")
            and not ln.strip().lower().startswith("count:")
        ]
        stripped = " ".join(ln.strip() for ln in stripped_lines if ln.strip())
        # Remove common import-boilerplate phrases
        for boilerplate in (
            "New plant added via field observation",
            "Plant notes:",
        ):
            stripped = stripped.replace(boilerplate, "").strip()
        stripped = " ".join(stripped.split())  # collapse whitespace
        if len(stripped) >= 3:
            display = stripped if len(stripped) <= 120 else stripped[:117] + "..."
            notes_html = f'<div class="plant-notes">{esc(display)}</div>'

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

    # Care tips (expanded view)
    care_html = render_care_tips(plant)

    # Log timeline (expanded view) — each entry links to a log detail page
    timeline_html = render_log_timeline(logs, section_id=section_id, base_url=base_url)

    # Species reference photo
    photo_html = ""
    if photo_url:
        photo_html = (
            f'<img class="plant-photo" loading="lazy" decoding="async" '
            f'src="{esc(photo_url)}" alt="{esc(species)} reference photo" '
            f'onclick="event.stopPropagation();openLightbox(this)" '
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
        {camera_btn_html}
        {count_html}
      </div>
      {notes_html}
      <div class="plant-tags-collapsed">{tags_html}</div>
      <div class="plant-detail">
        <p class="plant-desc">{esc(desc)}</p>
        <div class="plant-meta">{esc(meta_html)}</div>
        {succession_html}
        {care_html}
        <div class="plant-tags-expanded">{all_tags_html}</div>
        {timeline_html}
      </div>
    </div>"""


def render_strata_group(strata_key, plants, plant_db, section_id="", base_url=""):
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

    cards = "\n".join(render_plant_card(p, plant_db, section_id, base_url) for p in plants)
    
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


def render_section_log_block(section_logs, section_id, base_url=""):
    """Render a section-level log block (ADR 0008 I10 / Phase 3c).

    section-level logs have asset_ids=[] and carry submission-level
    evidence (section_notes + photos). They render at the top of the
    section page so visitors see field observations before the plant
    inventory.
    """
    if not section_logs:
        return ""
    entries_html = []
    for log in section_logs[:5]:  # cap to latest 5
        date = log.get("date", "") or ""
        notes_full = log.get("notes_full") or log.get("notes") or ""
        visible = "\n".join(
            ln for ln in notes_full.splitlines()
            if "[ontology:InteractionStamp]" not in ln
            and not ln.strip().lower().startswith("submission=")
        ).strip()
        # Extract reporter if present, then strip the header line for display
        reporter = ""
        reporter_m = re.search(r"^Reporter:\s*(.+)$", visible, re.M | re.I)
        if reporter_m:
            reporter = reporter_m.group(1).strip()
            visible = re.sub(r"^Reporter:.*$\n?", "", visible, count=1, flags=re.M | re.I).strip()
        # Trim to first ~200 chars
        snippet = visible if len(visible) <= 240 else visible[:237] + "..."
        photos = log.get("photos", []) or []
        # Photos in sections.json may be str paths (from export_farmos.py)
        # OR dicts with {thumb, url}. Handle both.
        def _photo_src(ph):
            if isinstance(ph, str):
                return ph
            return ph.get("thumb") or ph.get("url", "")
        photo_thumbs = "".join(
            f'<img class="sec-log-thumb" loading="lazy" '
            f'src="{esc(_photo_src(ph))}" '
            f'alt="Field photo" onclick="openLightbox(this)">'
            for ph in photos[:6]
        )
        log_uuid = log.get("uuid", "")
        detail_link = (
            f'<a href="{base_url}{section_id}-log-{log_uuid[:8]}.html" class="sec-log-more">Details →</a>'
            if log_uuid else ""
        )
        reporter_html = (
            f'<span class="sec-log-reporter">· {esc(reporter)}</span>' if reporter else ""
        )
        entries_html.append(f"""
        <div class="sec-log-entry">
          <div class="sec-log-head">
            <span class="sec-log-date">{esc(date)}</span>
            {reporter_html}
            {detail_link}
          </div>
          {f'<div class="sec-log-notes">{esc(snippet)}</div>' if snippet else ""}
          {f'<div class="sec-log-photos">{photo_thumbs}</div>' if photo_thumbs else ""}
        </div>""")
    return f"""
  <div class="section-log-block">
    <div class="section-log-title">🗒 Field observations for this section</div>
    {''.join(entries_html)}
  </div>
  <style>
    .section-log-block {{ margin: 16px 0; padding: 12px 14px; background: #fbfaf5; border-left: 3px solid #6b9e3c; border-radius: 8px; }}
    .section-log-title {{ font-weight: 600; font-family: 'Playfair Display', serif; color: #2d5016; margin-bottom: 8px; }}
    .sec-log-entry {{ margin: 6px 0 10px; padding-top: 6px; border-top: 1px solid #eee; }}
    .sec-log-entry:first-of-type {{ border-top: none; padding-top: 0; }}
    .sec-log-head {{ display: flex; gap: 8px; align-items: baseline; font-size: 13px; color: #555; }}
    .sec-log-date {{ font-weight: 600; color: #333; }}
    .sec-log-reporter {{ color: #888; font-size: 12px; }}
    .sec-log-more {{ margin-left: auto; color: #2d5016; text-decoration: none; font-size: 12px; }}
    .sec-log-notes {{ font-size: 14px; line-height: 1.4; color: #222; margin-top: 4px; }}
    .sec-log-photos {{ display: flex; gap: 6px; margin-top: 6px; flex-wrap: wrap; }}
    .sec-log-thumb {{ width: 72px; height: 72px; object-fit: cover; border-radius: 6px; cursor: pointer; border: 1px solid #e5e5e0; }}
  </style>"""


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
    
    strata_html = "\n".join(render_strata_group(sk, ps, plant_db, section_id, base_url) for sk, ps in grouped.items())
    green_manure_html = render_green_manure_box(green_manure_plants)
    row_bar_html = render_row_bar(row_info, sections_data, section_id, base_url)
    tabs_html = render_section_tabs(row_info, sections_data, section_id, base_url)
    # I10 / Phase 3c — section-level log block (submission-level
    # evidence: section_notes + photos, asset_ids=[]).
    section_logs_html = render_section_log_block(
        section.get("section_logs", []) or [], section_id, base_url,
    )
    
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

  {section_logs_html}

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

  <a href="{base_url}{section_id}-observe.html?camera=1" class="identify-fab" title="Identify a plant">
    <span>🔍</span>
  </a>
  <a href="{base_url}{section_id}-observe.html" class="observe-fab">
    <span class="observe-fab-icon">📋</span>
    <span>Record Observation</span>
  </a>

</div>

<div class="photo-lightbox" id="photo-lightbox" onclick="this.classList.remove('active')">
  <img id="lightbox-img" src="" alt="Species photo">
</div>
<script>
function openLightbox(el) {{
  var lb = document.getElementById('photo-lightbox');
  var img = document.getElementById('lightbox-img');
  var fullSrc = el.src.replace('.jpg', '-full.jpg');
  // Preload the full image, fall back to thumbnail if missing
  var preload = new Image();
  preload.onload = function() {{
    img.src = fullSrc;
    img.alt = el.alt;
    lb.classList.add('active');
  }};
  preload.onerror = function() {{
    // -full.jpg not available, show thumbnail
    img.src = el.src;
    img.alt = el.alt;
    lb.classList.add('active');
  }};
  preload.src = fullSrc;
}}
</script>

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

/* Log timeline — base styles used on section view pages.
   NOTE: Additions for log-entry-link / log-arrow / log-detail-page layout
   live in styles-observe.css because styles.css is hand-managed and this
   generator skips overwriting it — the section-level styles below keep
   working, and new rules ship via the always-regenerated observe CSS.   */
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
    """Render the observation form page for a section (v2 — camera-first)."""
    has_trees = section.get("has_trees", False)
    grad = "linear-gradient(145deg, #7a4a1a 0%, #b86e2a 60%, #d4872e 100%)" if has_trees else "linear-gradient(145deg, #b86e2a 0%, #d4872e 60%, #e6a040 100%)"
    section_type = "🌳 Tree Section" if has_trees else "☀️ Open Cultivation"

    all_plants = section.get("plants", [])
    plants_to_show = [p for p in all_plants if p.get("count") is None or (p.get("count") or 0) > 0]
    for p in plants_to_show:
        if not p.get("strata") and p["species"] in plant_db:
            p["strata"] = plant_db[p["species"]].get("strata", "low")
    regular_plants = [p for p in plants_to_show if not is_green_manure(p["species"], plant_db)]

    # Visual plant picker cards
    species_seen = set()
    picker_cards = ""
    for p in regular_plants:
        if p["species"] in species_seen:
            continue
        species_seen.add(p["species"])
        species = p["species"]
        count = p.get("count")
        photo_url = p.get("photo_url", "")
        st = STRATA_CONFIG.get(p.get("strata", "medium"), STRATA_CONFIG["medium"])
        count_display = count if count is not None else "—"
        photo_img = f'<img src="{esc(photo_url)}" alt="" onerror="this.style.display=\'none\'">' if photo_url else ""
        picker_cards += f"""
        <div class="plant-pick-card" data-species="{esc(species)}">
          <div class="pick-photo">{photo_img}</div>
          <div class="pick-name">{esc(species)}</div>
          <div class="pick-count" style="color:{st['color']}">{count_display}</div>
        </div>"""
    # Unknown plant card
    picker_cards += """
        <div class="plant-pick-card" data-species="Unknown">
          <div class="pick-photo"><span class="pick-unknown-icon">?</span></div>
          <div class="pick-name">Unknown</div>
          <div class="pick-count"></div>
        </div>"""

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
            # Prefill the "Now" input with the current count so that if the
            # observer doesn't change it, submission is a no-op on inventory.
            # Observers focused on photos don't accidentally zero counts.
            count_value_attr = f'value="{data_count}"' if data_count != "" else ""
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
                         class="inv-count-input" placeholder="—" {count_value_attr} aria-label="New count for {esc(species)}">
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

    plant_types_json = json.dumps([
        {"species": name, "strata": info.get("strata", "low"), "botanical": info.get("botanical", "")}
        for name, info in sorted(plant_db.items())
        if not name.startswith("[ARCHIVED]")
    ])

    endpoint_js = f'const OBSERVE_ENDPOINT = "{observe_endpoint}";' if observe_endpoint else 'const OBSERVE_ENDPOINT = "";'

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
    <div class="obs-subtitle">Section {esc(section_id)}</div>
  </div>

  <!-- Offline queue banner -->
  <div id="queue-banner" class="queue-banner" style="display:none">
    <span class="queue-count"></span>
    <button onclick="syncPendingQueue()" class="queue-sync-btn">Sync Now</button>
  </div>

  <!-- Observer info (sticky) -->
  <div class="obs-form-section obs-observer-bar">
    <div class="obs-field-row">
      <div class="obs-field-group" style="flex:2">
        <label class="obs-label" for="observer-name">Your name</label>
        <input type="text" id="observer-name" class="obs-input" placeholder="e.g. Claire, James" autocomplete="name">
      </div>
      <div class="obs-field-group" style="flex:1">
        <label class="obs-label" for="obs-datetime">Date</label>
        <input type="datetime-local" id="obs-datetime" class="obs-input">
      </div>
    </div>
  </div>

  <!-- TWO-TAB MODE TOGGLE -->
  <div class="mode-toggle-v2">
    <button class="mode-tab active" data-mode="single">🌱 Single Plant</button>
    <button class="mode-tab" data-mode="section">📋 Full Section</button>
  </div>

  <!-- ═══ SINGLE PLANT MODE ═══ -->
  <div id="mode-single" class="obs-mode-panel">
    <div class="obs-form-section">

      <!-- Camera Hero -->
      <div class="camera-hero">
        <input type="file" accept="image/*" capture="environment" id="camera-hero-input" hidden>
        <button type="button" id="camera-hero-btn" class="camera-hero-btn">
          <span class="camera-hero-icon">📷</span>
          <span class="camera-hero-text">Snap a photo to identify</span>
        </button>
        <div id="camera-hero-preview" class="camera-hero-preview" style="display:none"></div>
      </div>

      <!-- Multi-photo strip for PlantNet ID -->
      <div id="id-photo-strip" class="id-photo-strip" style="display:none"></div>
      <button type="button" id="plantnet-add-more" class="plantnet-add-more" style="display:none">
        <input type="file" accept="image/*" capture="environment" id="plantnet-more-input" hidden>
        📷 Add another angle
      </button>

      <!-- PlantNet results -->
      <div id="plantnet-results" class="plantnet-results" style="display:none"></div>

      <!-- Visual plant picker -->
      <div id="plant-picker-section" class="plant-picker-section">
        <div class="picker-label">or select a plant</div>
        <div class="plant-picker-grid">
          {picker_cards}
        </div>
      </div>

      <!-- Single plant observation form (hidden until plant selected) -->
      <div id="single-obs-form" class="single-obs-form" style="display:none">
        <div class="selected-plant-bar">
          <span id="selected-plant-name" class="selected-plant-name"></span>
          <span id="selected-plant-count" class="selected-plant-count"></span>
        </div>

        <!-- ADR 0008 I11: log type + status are derived from notes
             content by the importer's classifier, not by a UI radio.
             Previous "I observed / I did / Action needed" radios were
             dead UI — ignored by the pipeline — and absent from Full-
             Section mode. Dropped 2026-04-20. -->

        <div class="obs-field-row">
          <div class="obs-field-group obs-field-small">
            <label class="obs-label" for="single-count">New count</label>
            <input type="number" id="single-count" class="obs-input obs-input-number" inputmode="numeric" min="0" placeholder="—">
          </div>
          <div class="obs-field-group obs-field-small">
            <label class="obs-label" for="single-condition">Condition</label>
            <select id="single-condition" class="obs-select">
              <option value="alive">Alive</option>
              <option value="damaged">Damaged</option>
              <option value="dead">Dead</option>
            </select>
          </div>
        </div>

        <div class="obs-field-group">
          <label class="obs-label" for="single-notes">Notes</label>
          <textarea id="single-notes" class="obs-textarea" rows="2" placeholder="What did you see? (condition, growth, pests...)"></textarea>
        </div>

        <!-- Additional photos -->
        <div class="obs-media-area">
          <label class="obs-media-btn">
            <input type="file" accept="image/*" capture="environment" class="obs-photo-input" data-target="plant" hidden>
            <span>📷 Add more photos</span>
          </label>
          <div class="obs-photo-previews"></div>
        </div>

        <button id="single-submit" class="obs-submit-btn">Save Observation</button>
      </div>

      <button class="add-plant-trigger" onclick="showAddPlantPanel()">+ Add New Plant to Section</button>
    </div>
  </div>

  <!-- ═══ FULL SECTION MODE ═══ -->
  <div id="mode-section" class="obs-mode-panel" style="display:none">
    <div class="obs-form-section">

      <!-- Section notes at TOP (standalone) -->
      <div class="obs-field-group">
        <label class="obs-label" for="section-notes">Section notes</label>
        <textarea id="section-notes" class="obs-textarea" rows="3" placeholder="Overall section health, weed pressure, weather conditions, general observations..."></textarea>
      </div>

      <!-- Photo capture -->
      <div class="obs-media-area">
        <label class="obs-media-btn">
          <input type="file" accept="image/*" capture="environment" class="obs-photo-input" data-target="section" hidden>
          <span>📷 Add section photos</span>
        </label>
        <div class="obs-photo-previews"></div>
      </div>

      <!-- Collapsible plant inventory -->
      <div id="inventory-toggle" class="inventory-toggle">
        <span class="inv-toggle-arrow">▸</span>
        <span>Plant inventory ({len(regular_plants)} species)</span>
      </div>
      <div id="inventory-panel" style="display:none">
        {inventory_html}
      </div>

      <button id="section-submit" class="obs-submit-btn">Save Section Report</button>
      <button class="add-plant-trigger" onclick="showAddPlantPanel()">+ Add New Plant to Section</button>
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
            <option value="alive">Alive</option>
            <option value="damaged">Damaged</option>
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
    """Return CSS for observation pages (v2 — camera-first)."""
    return """
/* Observation page styles v2 — camera-first, two-tab */

.obs-subtitle { font-size: 13px; opacity: 0.8; margin-top: 8px; }

/* Queue banner */
.queue-banner { display: flex; align-items: center; justify-content: space-between; padding: 10px 16px; background: #fef3c7; border-bottom: 1px solid #fcd34d; font-size: 13px; color: #92400e; }
.queue-sync-btn { background: #f59e0b; color: #fff; border: none; padding: 6px 14px; border-radius: 6px; font-size: 12px; font-weight: 600; cursor: pointer; font-family: 'DM Sans', sans-serif; }

/* Observer bar */
.obs-observer-bar { background: #f7f6f0; border-bottom: 1px solid #e5e5e0; padding: 12px 16px; }

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

/* ── TWO-TAB MODE TOGGLE (v2, prominent) ── */
.mode-toggle-v2 { display: flex; gap: 4px; padding: 8px 16px; background: #f0f0ec; }
.mode-toggle-v2 .mode-tab {
  flex: 1; padding: 14px 12px; font-size: 15px; font-weight: 700; text-align: center;
  border: none; border-radius: 12px; cursor: pointer; font-family: 'DM Sans', sans-serif;
  transition: all 0.15s; color: #6b7280; background: #fff;
}
.mode-toggle-v2 .mode-tab.active[data-mode="single"] { background: #c17a2f; color: #fff; }
.mode-toggle-v2 .mode-tab.active[data-mode="section"] { background: #5a7a3a; color: #fff; }
.mode-toggle-v2 .mode-tab:not(.active):active { background: #eeeddf; }

/* ── CAMERA HERO ── */
.camera-hero { margin-bottom: 16px; }
.camera-hero-btn {
  width: 100%; padding: 28px 20px; background: linear-gradient(145deg, #2d5016, #4a7c29);
  border: none; border-radius: 16px; cursor: pointer; display: flex; flex-direction: column;
  align-items: center; gap: 8px; transition: transform 0.1s;
}
.camera-hero-btn:active { transform: scale(0.97); }
.camera-hero-icon { font-size: 40px; }
.camera-hero-text { color: #fff; font-size: 16px; font-weight: 600; font-family: 'DM Sans', sans-serif; }
.camera-hero-preview { border-radius: 12px; overflow: hidden; margin-bottom: 8px; }
.hero-preview-img { width: 100%; max-height: 200px; object-fit: cover; border-radius: 12px; }

/* ── MULTI-PHOTO ID STRIP ── */
.id-photo-strip { display: flex; gap: 8px; overflow-x: auto; padding: 8px 0; -webkit-overflow-scrolling: touch; }
.id-photo-item { position: relative; flex-shrink: 0; width: 80px; }
.id-photo-item img { width: 80px; height: 80px; object-fit: cover; border-radius: 8px; border: 1px solid #e5e5e0; }
.id-photo-remove { position: absolute; top: 2px; right: 2px; width: 20px; height: 20px; background: rgba(0,0,0,0.6); color: #fff; border: none; border-radius: 50%; font-size: 10px; cursor: pointer; display: flex; align-items: center; justify-content: center; }
.organ-chips { display: flex; flex-wrap: wrap; gap: 2px; margin-top: 4px; }
.organ-chip { padding: 1px 5px; border-radius: 6px; font-size: 9px; font-weight: 600; background: #f0f0ec; color: #6b7280; cursor: pointer; border: 1px solid transparent; }
.organ-chip.active { background: #2d5016; color: #fff; }
.plantnet-add-more { display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px; background: #f7f6f0; border: 1px dashed #d1d5db; border-radius: 8px; font-size: 12px; font-weight: 500; color: #555; cursor: pointer; font-family: 'DM Sans', sans-serif; margin-bottom: 10px; }

/* ── PLANTNET RESULTS ── */
.plantnet-results { margin-bottom: 14px; display: flex; flex-direction: column; gap: 6px; }
.plantnet-match { display: flex; gap: 10px; padding: 10px 12px; background: #f7f6f0; border: 1px solid #e5e5e0; border-radius: 10px; cursor: pointer; align-items: center; }
.plantnet-match:active { background: #efece0; border-color: #6b9e3c; }
.plantnet-match img { width: 48px; height: 48px; border-radius: 8px; object-fit: cover; flex-shrink: 0; }
.pn-no-img { width: 48px; height: 48px; border-radius: 8px; background: #e5e5e0; display: flex; align-items: center; justify-content: center; color: #999; font-size: 20px; flex-shrink: 0; }
.plantnet-match-text { flex: 1; min-width: 0; }
.plantnet-species { font-size: 14px; font-weight: 600; color: #1a1a1a; }
.plantnet-botanical { font-size: 11px; font-style: italic; color: #6b7280; }
.plantnet-confidence { font-size: 13px; font-weight: 700; color: #2d5016; flex-shrink: 0; }
.plantnet-status { font-size: 12px; color: #6b7280; padding: 8px 10px; background: #f7f6f0; border-radius: 8px; }
.pn-badge { display: inline-block; font-size: 10px; font-weight: 600; padding: 1px 6px; border-radius: 4px; margin-top: 2px; }
.pn-badge-section { background: #d1fae5; color: #065f46; }
.pn-badge-farm { background: #dbeafe; color: #1e40af; }
.pn-badge-unknown { background: #f3f4f6; color: #6b7280; }

/* ── VISUAL PLANT PICKER ── */
.plant-picker-section { margin-bottom: 16px; }
.picker-label { font-size: 12px; color: #9ca3af; text-align: center; margin-bottom: 10px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.06em; }
.plant-picker-grid { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; }
.plant-pick-card {
  width: 90px; padding: 8px 4px; background: #fff; border: 2px solid #e5e5e0; border-radius: 10px;
  cursor: pointer; text-align: center; transition: all 0.15s; display: flex; flex-direction: column; align-items: center; gap: 4px;
}
.plant-pick-card:active, .plant-pick-card.selected { border-color: #e67e22; background: #fff8f0; }
.pick-photo { width: 48px; height: 48px; border-radius: 8px; overflow: hidden; background: #f5f0e8; display: flex; align-items: center; justify-content: center; }
.pick-photo img { width: 100%; height: 100%; object-fit: cover; }
.pick-unknown-icon { font-size: 24px; color: #999; }
.pick-name { font-size: 11px; font-weight: 600; color: #1a1a1a; line-height: 1.2; word-break: break-word; }
.pick-count { font-size: 10px; font-weight: 700; }

/* ── SINGLE PLANT OBSERVATION FORM ── */
.single-obs-form { border-top: 2px solid #e67e22; padding-top: 16px; margin-top: 12px; }
.selected-plant-bar { display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; background: #fff8f0; border-radius: 10px; margin-bottom: 14px; border: 1px solid #f5dcc0; }
.selected-plant-name { font-family: 'Playfair Display', Georgia, serif; font-size: 16px; font-weight: 700; color: #1a1a1a; }
.selected-plant-count { font-size: 13px; color: #6b7280; }

/* Observation type radios */
.obs-type-group { display: flex; gap: 6px; margin-bottom: 14px; }
.obs-type-radio { flex: 1; }
.obs-type-radio input { display: none; }
.obs-type-label {
  display: block; text-align: center; padding: 10px 6px; border: 2px solid #e5e5e0; border-radius: 10px;
  font-size: 12px; font-weight: 600; color: #6b7280; cursor: pointer; transition: all 0.15s; font-family: 'DM Sans', sans-serif;
}
.obs-type-radio input:checked + .obs-type-label { border-color: #e67e22; background: #fff8f0; color: #c17a2f; }

/* ── FULL INVENTORY ROWS ── */
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

/* Inventory toggle */
.inventory-toggle { display: flex; align-items: center; gap: 8px; padding: 12px 0; cursor: pointer; font-size: 14px; font-weight: 600; color: #4a7c29; }
.inv-toggle-arrow { font-size: 14px; transition: transform 0.2s; }

/* Media capture */
.obs-media-area { margin-bottom: 14px; }
.obs-media-btn { display: inline-flex; align-items: center; gap: 6px; padding: 10px 16px; background: #f7f6f0; border: 1px dashed #d1d5db; border-radius: 8px; font-size: 13px; font-weight: 500; color: #555; cursor: pointer; font-family: 'DM Sans', sans-serif; }
.obs-media-btn:active { background: #eeeddf; }
.obs-photo-previews { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.obs-photo-preview { position: relative; width: 72px; height: 72px; border-radius: 8px; overflow: hidden; border: 1px solid #e5e5e0; }
.obs-photo-preview img { width: 100%; height: 100%; object-fit: cover; }
.obs-photo-remove { position: absolute; top: 2px; right: 2px; width: 20px; height: 20px; background: rgba(0,0,0,0.6); color: #fff; border: none; border-radius: 50%; font-size: 10px; cursor: pointer; display: flex; align-items: center; justify-content: center; }

/* Submit button */
.obs-submit-btn { width: 100%; padding: 14px; background: #e67e22; color: #fff; border: none; border-radius: 10px; font-size: 15px; font-weight: 700; cursor: pointer; font-family: 'DM Sans', sans-serif; transition: background 0.15s; margin-top: 4px; }
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
.plant-search-results { max-height: 200px; overflow-y: auto; border: 1px solid #e5e5e0; border-radius: 8px; margin-top: 4px; display: none; }
.plant-search-result { padding: 10px 12px; cursor: pointer; border-bottom: 1px solid #f0f0ec; font-size: 13px; }
.plant-search-result:hover { background: #f7f6f0; }
.plant-search-result .search-species { font-weight: 600; color: #1a1a1a; }
.plant-search-result .search-meta { font-size: 11px; color: #9ca3af; font-style: italic; }
.new-plant-display { font-size: 14px; font-weight: 600; color: #1a1a1a; padding: 8px 0; }

/* Navigation */
.obs-nav { padding: 16px; text-align: center; }
.obs-back-link { color: #e67e22; text-decoration: none; font-size: 14px; font-weight: 500; }

/* Recent submissions (pending-review cards) */
.recent-submissions { padding: 12px 16px 4px; background: #fefbea; border-bottom: 1px solid #f3e8bf; }
.recent-header { display: flex; align-items: center; gap: 8px; font-weight: 600; color: #92400e; font-size: 14px; margin-bottom: 4px; }
.recent-icon { font-size: 16px; }
.recent-intro { font-size: 12px; color: #78350f; line-height: 1.4; margin-bottom: 10px; opacity: 0.85; }
.recent-card { background: #fff; border: 1px solid #f3e8bf; border-radius: 10px; padding: 10px 12px; margin-bottom: 8px; font-size: 13px; }
.recent-card-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.recent-when { font-size: 11px; color: #6b7280; flex: 1; }
.recent-state-badge { font-size: 10px; font-weight: 600; padding: 2px 8px; border-radius: 12px; letter-spacing: 0.02em; }
.recent-state-badge.pending { background: #fef3c7; color: #92400e; }
.recent-state-badge.offline { background: #e0e7ff; color: #3730a3; }
.recent-dismiss { background: transparent; border: none; color: #9ca3af; font-size: 14px; cursor: pointer; padding: 2px 6px; border-radius: 4px; }
.recent-dismiss:hover { background: #f3f4f6; color: #4b5563; }
.recent-thumbs { display: flex; gap: 6px; margin-bottom: 8px; flex-wrap: wrap; }
.recent-thumb { width: 56px; height: 56px; border-radius: 6px; overflow: hidden; background: #f3f4f6; position: relative; }
.recent-thumb img { width: 100%; height: 100%; object-fit: cover; }
.recent-thumb.more { display: flex; align-items: center; justify-content: center; color: #6b7280; font-size: 12px; font-weight: 600; }
.recent-card-body { display: flex; flex-direction: column; gap: 6px; }
.recent-obs-row { font-size: 13px; color: #1a1a1a; line-height: 1.4; }
.recent-kind { margin-right: 2px; }
.recent-count-change { color: #d97706; font-weight: 600; font-variant-numeric: tabular-nums; }
.recent-count { color: #374151; font-variant-numeric: tabular-nums; }
.recent-note { font-size: 12px; color: #6b7280; font-style: italic; margin-top: 2px; padding-left: 20px; }

/* ── Log detail page ──────────────────────────────────────────
   These live in styles-observe.css (not styles.css) because the
   main stylesheet is hand-managed and skipped by the generator —
   new rules need a regenerated-every-run home. */
.log-detail-wrap { padding: 16px; max-width: 430px; margin: 0 auto; }
.log-detail-section { margin-bottom: 20px; }
.log-detail-h3 { font-size: 12px; font-weight: 600; color: #9ca3af; text-transform: uppercase; letter-spacing: 0.06em; margin: 0 0 10px; }
.prov-card { background: #f7f6f0; border: 1px solid #e5e5e0; border-radius: 10px; padding: 12px 14px; }
.prov-card.prov-raw { font-family: 'SF Mono', monospace; font-size: 11px; color: #6b7280; word-break: break-word; }
.prov-row { display: flex; align-items: baseline; gap: 10px; padding: 8px 0; font-size: 13px; line-height: 1.4; border-bottom: 1px solid #eceae2; }
.prov-row:last-child { border-bottom: none; }
.prov-icon { font-size: 14px; flex-shrink: 0; width: 22px; text-align: center; }
.prov-label { color: #9ca3af; min-width: 80px; font-size: 10px; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 700; flex-shrink: 0; }
.prov-value { color: #1a1a1a; flex: 1; word-break: break-word; }
.prov-value.mono { font-family: 'SF Mono', Consolas, monospace; font-size: 11px; color: #6b7280; }
.log-notes-body { background: #fff; border: 1px solid #e5e5e0; border-radius: 10px; padding: 14px; font-size: 14px; line-height: 1.5; color: #1a1a1a; white-space: pre-wrap; }

/* Clickable log entries on section view pages (upgrades the base
   .log-entry rule in styles.css with hover + link affordances). */
.log-entry-link { display: flex; align-items: center; gap: 6px; padding: 6px 8px; font-size: 12px; color: #6b7280; border-radius: 6px; text-decoration: none; transition: background 0.15s; cursor: pointer; }
.log-entry-link:hover, .log-entry-link:focus { background: #f7f6f0; color: #1a1a1a; }
.log-entry-link:hover .log-type, .log-entry-link:focus .log-type { color: #e67e22; }
.log-entry-link .log-type { color: #9ca3af; flex: 1; }
.log-arrow { color: #d1d5db; font-size: 16px; font-weight: 300; }

/* Log photo grid + lightbox */
.log-photo-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(112px, 1fr)); gap: 8px; }
.log-photo-thumb { display: block; border-radius: 8px; overflow: hidden; background: #f3f4f6; aspect-ratio: 1 / 1; cursor: zoom-in; transition: transform 0.15s, box-shadow 0.15s; }
.log-photo-thumb:hover { transform: scale(1.02); box-shadow: 0 4px 12px rgba(0,0,0,0.12); }
.log-photo-thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
.log-lightbox { position: fixed; inset: 0; background: rgba(0,0,0,0.92); display: none; align-items: center; justify-content: center; z-index: 1000; cursor: zoom-out; padding: 20px; }
.log-lightbox.open { display: flex; }
.log-lightbox img { max-width: 100%; max-height: 100%; object-fit: contain; border-radius: 4px; }
"""


def main():
    parser = argparse.ArgumentParser(description="Generate static site from farm data")
    parser.add_argument("--data", default="site/src/data/sections.json", help="Path to sections.json")
    parser.add_argument("--plants", default="knowledge/plant_types.csv", help="Path to plant_types.csv")
    parser.add_argument("--output", default="site/public/", help="Output directory")
    parser.add_argument("--base-url", default="", help="Base URL prefix for links")
    parser.add_argument(
        "--observe-endpoint",
        default=os.environ.get("OBSERVE_ENDPOINT", ""),
        help="Google Apps Script URL for observations. "
             "Defaults to $OBSERVE_ENDPOINT from env/.env — regenerating without "
             "this wired up is the 2026-04-15 / 2026-04-20 Kacper regression "
             "(all observe pages get empty endpoint, every QR submission "
             "returns 'Observation endpoint not configured').",
    )
    parser.add_argument(
        "--seedbank-endpoint",
        default=os.environ.get("SEED_BANK_ENDPOINT", os.environ.get("SEEDBANK_ENDPOINT", "")),
        help="Google Apps Script URL for seed bank (defaults to env)",
    )
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

        # Log detail pages — one per observation/activity/transplanting log.
        # Each page is the click target from the HISTORY row on the section
        # view and surfaces full notes + InteractionStamp provenance. First
        # piece of the Farm Intelligence Navigator Claire asked for.
        section_log_count = 0
        seen_log_uuids: set = set()
        for plant in section.get("plants", []):
            for log in plant.get("logs", []) or []:
                uuid = log.get("uuid")
                if not uuid or uuid in seen_log_uuids:
                    continue
                seen_log_uuids.add(uuid)
                log_html = render_log_detail_page(
                    section_id, section, row_info, log, plant_db, args.base_url
                )
                log_filename = log_detail_page_name(section_id, log)
                log_path = output_dir / log_filename
                with open(log_path, "w", encoding="utf-8") as f:
                    f.write(log_html)
                section_log_count += 1
        if section_log_count:
            print(f"  Generated: {section_log_count} log detail pages for {section_id}")

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

    # Post-gen assertion: every observe page must have a non-empty
    # OBSERVE_ENDPOINT. This is the last line of defence against the
    # 2026-04-15 / 2026-04-20 regression where every QR submission
    # returned "Observation endpoint not configured." because the env
    # fallback was silently empty.
    observe_pages = sorted(Path(output_dir).glob("*-observe.html"))
    empty = []
    for p in observe_pages:
        text = p.read_text(encoding="utf-8")
        if 'const OBSERVE_ENDPOINT = ""' in text or 'const OBSERVE_ENDPOINT = "";' in text:
            empty.append(p.name)
    if empty:
        print(
            f"\nFATAL: {len(empty)}/{len(observe_pages)} observe pages have "
            f"empty OBSERVE_ENDPOINT — QR submissions will fail.\n"
            f"       Set OBSERVE_ENDPOINT in .env OR pass --observe-endpoint.\n"
            f"       First few affected: {empty[:3]}",
            file=sys.stderr,
        )
        sys.exit(2)
    print(f"✓ All {len(observe_pages)} observe pages have OBSERVE_ENDPOINT wired.")


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
