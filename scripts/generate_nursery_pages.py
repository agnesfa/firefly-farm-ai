#!/usr/bin/env python3
"""
Generate observe HTML pages for nursery locations and the seed bank.

These pages are linked from QR codes that workers scan at each nursery zone.
They support Quick Report and Section Note modes (no Full Inventory — we don't
have pre-populated species data for nursery zones yet).

Usage:
    python scripts/generate_nursery_pages.py
    python scripts/generate_nursery_pages.py --output site/public/
"""

import argparse
import csv
import json
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
    ("NURS.GR", "Ground Area", "Firefly Corner \u00b7 Plant Nursery \u00b7 Ground"),
    ("NURS.GL", "Ground Left", "Firefly Corner \u00b7 Plant Nursery \u00b7 Ground"),
    ("NURS.FRT", "Front Area", "Firefly Corner \u00b7 Plant Nursery \u00b7 Front"),
    ("NURS.BCK", "Back Area", "Firefly Corner \u00b7 Plant Nursery \u00b7 Back"),
    ("NURS.HILL", "Hillside", "Firefly Corner \u00b7 Plant Nursery \u00b7 Hill"),
    ("NURS.STRB", "Strawberry Area", "Firefly Corner \u00b7 Plant Nursery \u00b7 Strawberry"),
    # Seed bank
    ("SEED.BANK", "Seed Bank", "Firefly Corner \u00b7 Seed Bank"),
]


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


def is_seed_bank(loc_id):
    return loc_id == "SEED.BANK"


def header_gradient(loc_id):
    """Return a nursery-themed green gradient for the header."""
    if is_seed_bank(loc_id):
        # Seed bank: earthy brown-green
        return "linear-gradient(145deg, #3d6b2e 0%, #5a8a3c 60%, #6b9e4a 100%)"
    # Nursery zones: fresh green
    return "linear-gradient(145deg, #2d6b1a 0%, #4a8c2e 60%, #5da83a 100%)"


def location_icon(loc_id):
    """Return an appropriate icon for the location type."""
    if is_seed_bank(loc_id):
        return "seed"
    if "SH" in loc_id:
        return "shelf"
    return "ground"


def location_badge(loc_id):
    """Return a badge label for the location type."""
    if is_seed_bank(loc_id):
        return "Seed Storage"
    if "SH" in loc_id:
        return "Nursery Shelf"
    return "Nursery Zone"


def render_page(loc_id, display_name, breadcrumb, plant_types_json):
    """Render a single nursery observe page as HTML string."""

    gradient = header_gradient(loc_id)
    badge = location_badge(loc_id)
    escaped_id = escape(loc_id)
    escaped_name = escape(display_name)
    escaped_breadcrumb = escape(breadcrumb)

    # For seed bank, use different hint text
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

  <!-- Mode toggle — Quick Report + Zone Note only (no Full Inventory) -->
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

// Nursery Quick Report: species search (replaces dropdown for better UX with 200+ species)
(function() {{
  var searchInput = document.getElementById("quick-species-search");
  var resultsDiv = document.getElementById("quick-species-results");
  var hiddenSelect = document.getElementById("quick-species");

  if (!searchInput || !resultsDiv) return;

  var selectedSpecies = "";

  searchInput.addEventListener("input", function() {{
    var query = this.value.trim().toLowerCase();
    if (query.length < 2) {{
      resultsDiv.style.display = "none";
      resultsDiv.innerHTML = "";
      return;
    }}

    var plantTypes = typeof PLANT_TYPES_DATA !== "undefined" ? PLANT_TYPES_DATA : [];
    var matches = [];

    // Always offer Unknown option
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

  // Close results when clicking outside
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

  // Set hidden select value so collectQuickData picks it up
  if (hiddenSelect) {{
    // Ensure option exists
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


def main():
    parser = argparse.ArgumentParser(
        description="Generate observe pages for nursery locations and seed bank"
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
    args = parser.parse_args()

    output_dir = Path(args.output)
    plants_csv = Path(args.plants)

    if not output_dir.exists():
        print(f"Error: output directory {output_dir} does not exist")
        return

    # Load plant types for Add New Plant search
    print(f"Loading plant types from {plants_csv}...")
    plant_types = load_plant_types(plants_csv)
    plant_types_json = json.dumps(plant_types, ensure_ascii=False)
    print(f"  Loaded {len(plant_types)} plant types")

    print(f"\nGenerating {len(NURSERY_LOCATIONS)} nursery observe pages...")

    for loc_id, display_name, breadcrumb in NURSERY_LOCATIONS:
        filename = f"{loc_id}-observe.html"
        filepath = output_dir / filename

        html = render_page(loc_id, display_name, breadcrumb, plant_types_json)
        filepath.write_text(html, encoding="utf-8")
        print(f"  {filename}")

    print(f"\nDone: {len(NURSERY_LOCATIONS)} pages generated in {output_dir}")


if __name__ == "__main__":
    main()
