#!/usr/bin/env python3
"""
Parse Claire's field sheet Excel files into structured JSON.

Handles two spreadsheet formats:
- v2 format (P2R2, P2R3): 10-column inventory layout with farmos_name species
- P2R1 format: Old renovation layout with lifecycle columns, species in Col C

Species names are normalized to match the farmos_name convention in plant_types.csv.
Section IDs are extracted from sheet content (not tab names) to handle boundary updates.

Usage:
    python scripts/parse_fieldsheets.py --input fieldsheets/ --output site/src/data/
    python scripts/parse_fieldsheets.py  # uses defaults
"""

import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path

import openpyxl

# ─── Section ID remapping (spreadsheet → farmOS) ─────────────────────────
# For sections where the spreadsheet has a different ID than farmOS
SECTION_ID_MAP = {
    "P2R1.13-22": "P2R1.16-25",
}

# ─── Species name mapping ────────────────────────────────────────────────
# Manual overrides for names that can't be auto-resolved
SPECIES_NAME_OVERRIDES = {
    # P2R1 uppercase/informal names
    "CITRUS yuzu": "Citrus (Yuzu)",
    "COMFREY FFC": "Comfrey",
    "CORIANDER FFC": "Coriander",
    "EUCALYPT": "Eucalypt-Gum (Generic)",
    "FIG TREE": "Fig",
    "FINGER LIME": "Finger Lime",
    "GINGER FFC": "Ginger",
    "GRAPE vine": "Grape Vine",
    "GRAPES": "Grape Vine",
    "GUAVA": "Guava",
    "ICE CREAM BEAN": "Ice Cream Bean",
    "LAVENDER": "Lavender",
    "LEMON TREE FFC cut": "Lemon",
    "LEMON TREE FFC seedl": "Lemon",
    "OLIVE TREE": "Olive",
    "OREGANO": "Oregano",
    "PIGEON PEA": "Pigeon Pea",
    "ROSEMARY": "Rosemary",
    "SAGE": "Sage",
    "TANSY": "Tansy",
    "THYME FFC": "Thyme",
    "borage": "Borage",
    "bush mint": "Mint",
    "chives": "Chives",
    "cow pea": "Cowpea",
    "geranium cuttings": "Geranium",
    "hyssop": "Hyssop",
    "lemon balm": "Lemon Balm",
    "lemon scented tea tree cutting": "Tea Tree Oil (Melaleuca) (Alternifolia)",
    "sweet potatoes": "Sweet Potato",
    "Parsley": "Parsley (Italian)",
    "oat": "Oat",
    "millet": "Millet",
    "sunn hemp": "Sunn Hemp",
    # P2R2/P2R3 names that differ from farmos_name
    "Cherry Guava": "Guava (Strawberry)",
    "Cherry Guava (Strawberry)": "Guava (Strawberry)",
    "Cootamundra Wattle": "Wattle - Cootamundra (Baileyana)",
    "Silver Wattle": "Silver Wattle (Dealbata)",
    "White Mulberry": "Mulberry (White)",
    "Basil (Sweet)": "Basil - Sweet (Classic)",
    "Basil (Thai)": "Basil - Perennial (Thai)",
    "Basil (Greek)": "Basil - Perennial (Greek)",
    "Plum": "Plum (Generic)",
    "Pumpkin": "Pumpkin (Generic)",
    "Tea Tree": "Tea Tree Oil (Melaleuca) (Alternifolia)",
    "Tagasaste": "Tagasaste - Tree Lucerne",
    "Tallowood": "Tallowood (Gum)",
    # Green manure species
    "Bean (Climbing) Epicure": "Bean - Climbing",
    "Bean (Dwarf) Borlotti": "Bean - Dwarf",
    "Buck wheat": "Buckwheat",
    "Butternut ffc": "Butternut Pumpkin",
    "Cow pea": "Cowpea",
    "Pea (Snow/Sugar Snap)": "Pea-Snow",
    "Pigeon Pea (seeds)": "Pigeon Pea",
    "Pumpkin ffc": "Pumpkin (Generic)",
    "Sunn hemp": "Sunn Hemp",
    "White Clover": "Clover (White)",
    "Corn": "Corn",
    "Spring Onion": "Spring Onion",
    "Sunflower": "Sunflower",
}

# Suffixes to strip during normalization
STRIP_SUFFIXES = [" FFC", " ffc", " tree", " Tree", " vine", " cuttings", " cutting", " seedl"]

# Non-plant rows to skip
SKIP_SPECIES = {
    "LIME g/m2", "lime g/m2", "LIME", "lime", "TOTALS", "totals",
    "GM TOTAL", "gm total", "GREEN MANURE", "green manure",
    "None", "", "SUMMER GREEN MANURE", "WINTER GREEN MANURE",
    "1 lm= 1sqm",
}


def load_farmos_names(csv_path="knowledge/plant_types.csv"):
    """Load all farmos_name values from plant_types.csv for matching."""
    names = set()
    csv_file = Path(csv_path)
    if not csv_file.exists():
        print(f"  Warning: {csv_path} not found, name matching disabled")
        return names
    with open(csv_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("farmos_name", "").strip()
            if name:
                names.add(name)
    return names


def normalize_species(raw_name, farmos_names):
    """Normalize a species name to match farmos_name convention.

    Resolution order:
    1. Exact match in overrides dict
    2. Stripped/trimmed exact match in farmos_names
    3. Case-insensitive match in farmos_names
    4. Strip common suffixes and try again
    5. Title-case and try
    6. Return raw name with flag if no match
    """
    if not raw_name or raw_name.strip() in SKIP_SPECIES:
        return None

    name = raw_name.strip()

    # 1. Manual override (exact)
    if name in SPECIES_NAME_OVERRIDES:
        return SPECIES_NAME_OVERRIDES[name]

    # 2. Direct match in farmos_names
    if name in farmos_names:
        return name

    # 3. Case-insensitive match
    name_lower = name.lower()
    for fn in farmos_names:
        if fn.lower() == name_lower:
            return fn

    # 4. Strip suffixes and retry
    stripped = name
    for suffix in STRIP_SUFFIXES:
        if stripped.endswith(suffix):
            stripped = stripped[:-len(suffix)].strip()
    if stripped != name:
        if stripped in farmos_names:
            return stripped
        for fn in farmos_names:
            if fn.lower() == stripped.lower():
                return fn

    # 5. Title case
    titled = name.strip().title()
    if titled in farmos_names:
        return titled

    # 6. No match found — return as-is (will be flagged)
    return name


def parse_count(val):
    """Parse a numeric count from a cell value."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        n = float(val)
        return int(n) if n == int(n) else n
    try:
        n = float(str(val).strip())
        return int(n) if n == int(n) else n
    except (ValueError, TypeError):
        return None


def format_date(val):
    """Format a datetime or string value as YYYY-MM-DD."""
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d")
    if isinstance(val, str):
        m = re.search(r'(\d{4}-\d{2}-\d{2})', val)
        if m:
            return m.group(1)
    return ""


# ─── v2 format parser (P2R2, P2R3) ──────────────────────────────────────

def parse_v2_section(ws, farmos_names):
    """Parse a v2 format section sheet (P2R2/P2R3 inventory format).

    Row 1: "P2 — R{n} — Section {start}-{end} (was {old})"
    Row 2: "{length}m | WITH/NO TREES | First planted: {date} | {climate}"
    Row 3: Length: {n}  Date: {first_planted} {last_inventory}
    Row 4: Headers
    Row 5+: Plant data (Col A=strata, B=species, C=notes, D=planted, E=last inventory)
    """
    title = str(ws.cell(1, 1).value or "")
    meta = str(ws.cell(2, 1).value or "")

    # Extract section range from title — use FIRST range (before any "(was ...)")
    title_clean = title.replace("\u2014", "-").replace("\u2013", "-").replace("—", "-").replace("–", "-")
    m = re.search(r'P(\d+)\s*-\s*R(\d+)\s*-\s*Section\s+([\d.]+-[\d.]+)', title_clean)
    if not m:
        return None

    paddock = int(m.group(1))
    row = int(m.group(2))
    section_range = m.group(3)
    section_id = f"P{paddock}R{row}.{section_range}"

    # Remap if needed
    section_id = SECTION_ID_MAP.get(section_id, section_id)

    # Metadata from Row 2
    has_trees = "WITH TREES" in meta.upper()
    first_planted_m = re.search(r'First planted:\s*([^|]+)', meta, re.IGNORECASE)
    first_planted = first_planted_m.group(1).strip() if first_planted_m else ""

    # Structured data from Row 3
    length_val = ws.cell(3, 2).value  # B3
    length = f"{int(length_val)}m" if length_val else ""
    inventory_date = format_date(ws.cell(3, 5).value)  # E3
    first_planted_date = format_date(ws.cell(3, 4).value)  # D3 — exact date
    if first_planted_date:
        first_planted = first_planted_date  # Prefer exact date over text

    # Parse plant data from Row 5+
    plants = []
    green_manure = []
    current_strata = None
    in_green_manure = False
    unmapped = []

    for row_idx in range(5, ws.max_row + 1):
        a_val = str(ws.cell(row_idx, 1).value or "").strip()
        b_val = str(ws.cell(row_idx, 2).value or "").strip()

        # Detect end of plant data / start of green manure
        if a_val.upper().startswith("TOTALS"):
            continue
        if "GREEN MANURE" in a_val.upper():
            in_green_manure = True
            continue
        if a_val.upper().startswith("GM TOTAL"):
            continue
        if "Firefly Corner Farm" in a_val:
            break

        if in_green_manure:
            # Green manure row: A=Placenta, B=species, E=last seeded quantity
            if not b_val or b_val.lower() in ("species", ""):
                continue
            gm_name = normalize_species(b_val, farmos_names)
            if gm_name:
                gm_qty = parse_count(ws.cell(row_idx, 5).value)
                green_manure.append({
                    "species": gm_name,
                    "quantity_grams": gm_qty,
                })
            continue

        # Regular plant data
        if not b_val:
            continue

        # Update strata
        if a_val:
            a_lower = a_val.lower()
            if a_lower in ("emergent", "high", "medium", "low"):
                current_strata = a_lower
            elif a_lower == "placenta":
                continue  # Skip inline placenta markers

        if not current_strata:
            continue

        # Normalize species name
        species = normalize_species(b_val, farmos_names)
        if not species:
            continue

        if species not in farmos_names and species == b_val:
            unmapped.append(b_val)

        notes = str(ws.cell(row_idx, 3).value or "").strip()
        count = parse_count(ws.cell(row_idx, 5).value)  # Col E = Last Inventory

        plants.append({
            "species": species,
            "strata": current_strata,
            "count": count,
            "notes": notes if notes and notes != "None" else "",
        })

    if unmapped:
        for name in unmapped:
            print(f"    ⚠ Unmapped species: '{name}'")

    result = {
        "id": section_id,
        "paddock": paddock,
        "row": row,
        "range": section_range.replace("-", "\u2013"),
        "length": length,
        "has_trees": has_trees,
        "first_planted": first_planted,
        "inventory_date": inventory_date,
        "plants": plants,
    }
    if green_manure:
        result["green_manure"] = green_manure
    return result


# ─── P2R1 format parser ─────────────────────────────────────────────────

def parse_r1_section(ws, farmos_names):
    """Parse a P2R1 renovation format section sheet.

    Tab names: R1.{range}.2025 spring renovation
    Row 2: H2='LENGTH m', I2=length, J2=inventory date
    Row 3: H3='Portion name', I3=range, J3=farmOS section ID
    Row 4: Headers (Lifecycle columns)
    Row 5: Sub-headers (strata, % surface)
    Row 6+: Data (Col A=strata, Col C=species, Col M=total count)
    """
    # Section ID from J3
    section_id = str(ws.cell(3, 10).value or "").strip()  # J3
    if not section_id or not section_id.startswith("P2R1"):
        return None

    # Remap if needed
    section_id = SECTION_ID_MAP.get(section_id, section_id)

    # Extract paddock, row, range from section_id
    m = re.match(r'P(\d+)R(\d+)\.([\d]+-[\d]+)', section_id)
    if not m:
        return None
    paddock = int(m.group(1))
    row = int(m.group(2))
    section_range = m.group(3)

    # Metadata
    length_val = ws.cell(2, 9).value  # I2
    length = f"{int(length_val)}m" if length_val else ""
    inventory_date = format_date(ws.cell(2, 10).value)  # J2
    has_trees = str(ws.cell(4, 9).value or "").strip().upper() == "TREES"  # I4

    # First planted from A1 text — extract and normalize to ISO date
    a1 = str(ws.cell(1, 1).value or "")
    first_planted = ""
    fp_m = re.search(r'PLANTATION/SOWING DATE\s*:\s*(.+)', a1, re.IGNORECASE)
    if fp_m:
        raw_date = fp_m.group(1).strip()
        # Parse "2025-MARCH-20 to 24TH" → "2025-03-20"
        date_m = re.match(r'(\d{4})[/-](\w+)[/-](\d+)', raw_date)
        if date_m:
            month_names = {
                "JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "APRIL": 4,
                "MAY": 5, "JUNE": 6, "JULY": 7, "AUGUST": 8,
                "SEPTEMBER": 9, "OCTOBER": 10, "NOVEMBER": 11, "DECEMBER": 12,
            }
            month_num = month_names.get(date_m.group(2).upper(), 0)
            if month_num:
                first_planted = f"{date_m.group(1)}-{month_num:02d}-{int(date_m.group(3)):02d}"
            else:
                first_planted = raw_date
        else:
            first_planted = raw_date

    # Parse plant data from Row 6+
    plants = []
    current_strata = None
    unmapped = []

    for row_idx in range(6, ws.max_row + 1):
        a_val = str(ws.cell(row_idx, 1).value or "").strip()
        c_val = str(ws.cell(row_idx, 3).value or "").strip()  # Species in Col C

        if not c_val:
            continue

        # Skip non-plant entries
        if c_val in SKIP_SPECIES or c_val.startswith("SUMMER GREEN") or c_val.startswith("WINTER GREEN"):
            continue
        if c_val.upper().startswith("LIME G/M"):
            continue

        # Update strata from Col A
        if a_val:
            a_lower = a_val.lower().rstrip(".")
            if a_lower in ("emergent", "high", "medium", "low"):
                current_strata = a_lower
            elif a_lower in ("pionneer", "pionneer.", "pioneer", "placenta"):
                continue  # Skip these markers

        if not current_strata:
            continue

        # Normalize species
        species = normalize_species(c_val, farmos_names)
        if not species:
            continue

        if species not in farmos_names and species == c_val:
            unmapped.append(c_val)

        # Count from Col M (total) — fallback to Col J (inventory) or Col I (initial)
        count = parse_count(ws.cell(row_idx, 13).value)  # Col M
        if count is None:
            count = parse_count(ws.cell(row_idx, 10).value)  # Col J
        if count is None:
            count = parse_count(ws.cell(row_idx, 9).value)  # Col I

        plants.append({
            "species": species,
            "strata": current_strata,
            "count": count,
            "notes": "",
        })

    if unmapped:
        for name in unmapped:
            print(f"    ⚠ Unmapped species: '{name}'")

    return {
        "id": section_id,
        "paddock": paddock,
        "row": row,
        "range": section_range.replace("-", "\u2013"),
        "length": length,
        "has_trees": has_trees,
        "first_planted": first_planted,
        "inventory_date": inventory_date,
        "plants": plants,
    }


# ─── File-level parsing ─────────────────────────────────────────────────

def is_r1_section_tab(name):
    """Check if tab name matches P2R1 section pattern."""
    return bool(re.match(r'R1\.\d+-\d+\.', name))


def is_v2_section_tab(name):
    """Check if tab name matches v2 section pattern (P2R2.x-y or P2R3.x-y)."""
    return bool(re.match(r'P2R[23]\.\d+-\d+', name))


def parse_fieldsheet_file(filepath, farmos_names):
    """Parse all section sheets from a single field sheet Excel file."""
    wb = openpyxl.load_workbook(filepath, data_only=True)
    sections = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]

        if is_r1_section_tab(sheet_name):
            section = parse_r1_section(ws, farmos_names)
            if section:
                sections.append(section)
                plant_count = sum(1 for p in section["plants"] if p.get("count") and p["count"] > 0)
                print(f"  Parsed: {section['id']} — {len(section['plants'])} species ({plant_count} with count)")
            else:
                print(f"  Skipped: {sheet_name} (could not parse P2R1 format)")

        elif is_v2_section_tab(sheet_name):
            section = parse_v2_section(ws, farmos_names)
            if section:
                sections.append(section)
                plant_count = sum(1 for p in section["plants"] if p.get("count") and p["count"] > 0)
                print(f"  Parsed: {section['id']} — {len(section['plants'])} species ({plant_count} with count)")
            else:
                print(f"  Skipped: {sheet_name} (could not parse v2 format)")

        else:
            # Skip non-section tabs (mapping, recap, planning, etc.)
            pass

    return sections


def build_row_info(sections):
    """Build row-level summary from parsed sections."""
    rows = {}
    for sec in sections:
        row_id = f"P{sec['paddock']}R{sec['row']}"
        if row_id not in rows:
            rows[row_id] = {
                "id": row_id,
                "paddock": f"Paddock {sec['paddock']}",
                "row": f"Row {sec['row']}",
                "sections": [],
                "first_planted": sec.get("first_planted", ""),
            }
        rows[row_id]["sections"].append(sec["id"])

    # Sort sections within each row by start position
    for row in rows.values():
        row["sections"].sort(key=lambda sid: float(sid.split(".")[-1].split("\u2013")[0].split("-")[0]))
        # Calculate total length from last section endpoint
        last_sec = [s for s in sections if s["id"] == row["sections"][-1]][0]
        range_parts = last_sec["range"].replace("\u2013", "-").split("-")
        if len(range_parts) == 2:
            row["total_length"] = f"{range_parts[1]}m"

    return rows


def main():
    parser = argparse.ArgumentParser(description="Parse field sheet Excel files into JSON")
    parser.add_argument("--input", default="fieldsheets/", help="Directory containing .xlsx files")
    parser.add_argument("--output", default="site/src/data/", help="Output directory for JSON")
    parser.add_argument("--plants-csv", default="knowledge/plant_types.csv",
                        help="Plant types CSV for name matching")
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load farmos_names for species matching
    farmos_names = load_farmos_names(args.plants_csv)
    print(f"Loaded {len(farmos_names)} plant type names for matching")

    all_sections = []

    # Find and parse all field sheet files
    xlsx_files = sorted(input_dir.glob("*.xlsx"))
    if not xlsx_files:
        print(f"No .xlsx files found in {input_dir}")
        return

    for filepath in xlsx_files:
        print(f"\nParsing: {filepath.name}")
        sections = parse_fieldsheet_file(filepath, farmos_names)
        all_sections.extend(sections)

    if not all_sections:
        print("\nNo sections parsed!")
        return

    # Build row summaries
    rows = build_row_info(all_sections)

    # Collect all species for summary
    all_species = set()
    for s in all_sections:
        for p in s["plants"]:
            all_species.add(p["species"])

    unmatched = all_species - farmos_names
    matched = all_species & farmos_names

    # Write sections.json
    output_file = output_dir / "sections.json"
    output_data = {
        "generated": True,
        "sections": {s["id"]: s for s in all_sections},
        "rows": rows,
    }

    with open(output_file, "w") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"PARSE SUMMARY")
    print(f"{'='*60}")
    print(f"  Sections parsed:  {len(all_sections)}")
    for row_id, row_info in sorted(rows.items()):
        print(f"    {row_id}: {len(row_info['sections'])} sections")
    print(f"  Unique species:   {len(all_species)}")
    print(f"  Matched to CSV:   {len(matched)}")
    if unmatched:
        print(f"  UNMATCHED:        {len(unmatched)}")
        for name in sorted(unmatched):
            print(f"    - {name}")
    print(f"\n  Output: {output_file}")


if __name__ == "__main__":
    main()
