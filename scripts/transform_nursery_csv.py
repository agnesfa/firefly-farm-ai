#!/usr/bin/env python3
"""
Transform Claire/Olivier's raw nursery inventory CSV into the enriched format
that generate_nursery_pages.py expects.

Input:  Raw CSV with columns: Location, Common Name, Variety, Growing Process,
        Seeding/Planting Date, Pots Planted, Viable Plants, Not RTT, RTT, Colonne2, Notes

Output: Enriched CSV with columns matching load_nursery_inventory() expectations:
        Location ID, Species (farmOS), Common Name, Variety, Botanical Name, Strata,
        Succession, Source, Process, Seeding/Planting Date, Pots Planted,
        Viable (Mar 20), Success Rate %, Not RTT, RTT, Destination, How Many, When

Usage:
    python scripts/transform_nursery_csv.py
    python scripts/transform_nursery_csv.py --input path/to/raw.csv --output path/to/enriched.csv
"""

import argparse
import csv
import re
from pathlib import Path

# ─── SPECIES NAME NORMALIZATION ─────────────────────────────────────────────

SPECIES_NAME_MAP = {
    "TUMERIC": "Turmeric",
    "Tumeric": "Turmeric",
    "tumeric": "Turmeric",
    "Pigeon pea": "Pigeon Pea",
    "pigeon pea": "Pigeon Pea",
    "Olive tree": "Olive",
    "olive tree": "Olive",
    "Peach tree": "Peach",
    "peach tree": "Peach",
    "Fern Tree": "Tree Fern",
    "fern tree": "Tree Fern",
    "Spinach-Perennial": "Spinach - Perennial",
    "spinach-perennial": "Spinach - Perennial",
    "Tree Lucerne - Tagasaste": "Tagasaste - Tree Lucerne",
    "papaya": "Papaya",
    "Tallowood tree": "Tallowood",
    "tallowood tree": "Tallowood",
    "Sweet potato": "Sweet Potato",
    "sweet potato": "Sweet Potato",
    "figue de Barbarie": "Prickly Pear",  # Opuntia ficus-indica — not in plant_types.csv yet
    "Vacoa": "Vacoa (Pandanus)",
    "Black She-oak -Allocasuarina": "Black She-oak",
    "Lemon Balm": "Lemon Balm",
    "Grape Vine": "Grape Vine",
}

# Mappings that produce (common_name, variety) tuples — overrides both fields
SPECIES_TUPLE_MAP = {
    "Red Capsicum": ("Capsicum", "Red"),
}

# Onion - Spring needs special handling for farmOS name lookup
FARMOS_NAME_OVERRIDES = {
    # (normalized common_name, variety) → farmos_name
    ("Onion - Spring", "White Lisbon"): "Spring Onion (Lisbon)",
    ("Onion - Spring", ""): "Spring Onion",
    ("Spinach - Perennial", "Okinawa"): "Spinach-Perennial (Okinawa Spinach)",
}

# Guava/Pear with embedded quotes: "Guava ""Hawaian""" → Guava (Hawaiian)
QUOTED_VARIETY_MAP = {
    ('Guava', 'Hawaian'): ('Guava', 'Hawaiian'),
    ('Guava', 'Hawaiian'): ('Guava', 'Hawaiian'),
    ('Guava', 'Strawberry'): ('Guava', 'Strawberry'),
    ('Pear', 'William'): ('Pear', 'Williams'),
    ('Pear tree', 'William'): ('Pear', 'Williams'),
    ('Pear', 'Williams'): ('Pear', 'Williams'),
    ('Mulberry', 'White'): ('Mulberry', 'White'),
}


def normalize_species(common_name, variety):
    """Normalize a common_name + variety into clean (common_name, variety) pair."""
    common_name = common_name.strip()
    variety = variety.strip() if variety else ""

    # Handle embedded quoted varieties like: Guava "Hawaian" or Guava ""Hawaian""
    # These come from CSV parsing of fields like: "Guava ""Hawaian"""
    embedded_match = re.match(r'^(.+?)\s*["""](.+?)["""]$', common_name)
    if embedded_match:
        base = embedded_match.group(1).strip()
        embedded_var = embedded_match.group(2).strip()
        key = (base, embedded_var)
        if key in QUOTED_VARIETY_MAP:
            return QUOTED_VARIETY_MAP[key]
        # Also try with "tree" stripped
        base_no_tree = re.sub(r'\s+tree$', '', base, flags=re.IGNORECASE).strip()
        key2 = (base_no_tree, embedded_var)
        if key2 in QUOTED_VARIETY_MAP:
            return QUOTED_VARIETY_MAP[key2]
        return (base_no_tree if base_no_tree != base else base, embedded_var)

    # Handle "Mulberry – White" (en-dash separator for variety)
    en_dash_match = re.match(r'^(.+?)\s*[–—]\s*(.+)$', common_name)
    if en_dash_match and not en_dash_match.group(1).strip().endswith('-'):
        base = en_dash_match.group(1).strip()
        var = en_dash_match.group(2).strip()
        key = (base, var)
        if key in QUOTED_VARIETY_MAP:
            return QUOTED_VARIETY_MAP[key]
        # Check if this is a dash-name like "Basil - Sweet" vs "Mulberry – White"
        # If base+var maps to a known farmos_name with variety, treat as variety
        return (base, var)

    # Tuple mapping (produces both common_name and variety)
    if common_name in SPECIES_TUPLE_MAP:
        return SPECIES_TUPLE_MAP[common_name]

    # Direct name mapping
    if common_name in SPECIES_NAME_MAP:
        common_name = SPECIES_NAME_MAP[common_name]

    # Strip "tree" suffix from names (but not "Tree Fern" which was already mapped)
    if common_name not in ("Tree Fern",):
        common_name = re.sub(r'\s+tree$', '', common_name, flags=re.IGNORECASE).strip()

    # Title-case fix for all-lower or all-upper names
    if common_name == common_name.lower() or common_name == common_name.upper():
        # Preserve known dash-names
        if " - " in common_name:
            parts = common_name.split(" - ")
            common_name = " - ".join(p.strip().title() for p in parts)
        else:
            common_name = common_name.title()

    # Variety normalization
    if variety:
        # OKINAWA → Okinawa
        if variety == variety.upper() and len(variety) > 2:
            variety = variety.title()
        # "thai" → "Thai"
        if variety == variety.lower():
            variety = variety.title()

    return (common_name, variety)


def build_farmos_name(common_name, variety):
    """Build the farmos_name from common_name + variety."""
    # Check for explicit overrides first
    key = (common_name, variety)
    if key in FARMOS_NAME_OVERRIDES:
        return FARMOS_NAME_OVERRIDES[key]
    if variety:
        return f"{common_name} ({variety})"
    return common_name


def extract_location_id(location_str):
    """Extract the farmOS location ID from the Location column.

    Handles separators: " - ", " — " (em dash), " Ñ " (typo for em dash)
    """
    if not location_str:
        return ""

    # Split on known separators
    for sep in [" - ", " — ", " – ", " Ñ "]:
        if sep in location_str:
            return location_str.split(sep, 1)[0].strip()

    # Fallback: return the whole thing trimmed
    return location_str.strip()


def extract_destination_info(notes):
    """Extract destination, how_many, when from Notes column.

    Patterns:
      "→ P2R4; Mar-26"
      "? P2R4; Mar-26"
      "→ P2R2, P2R4; Mar-26"
      "Need split/transpot"
    """
    if not notes:
        return ("", "", "")

    notes = notes.strip()

    # Match "→ DEST; WHEN" or "? DEST; WHEN"
    dest_match = re.match(r'^[→?]\s*(.+?)(?:;\s*(.+))?$', notes)
    if dest_match:
        destination = dest_match.group(1).strip()
        when = dest_match.group(2).strip() if dest_match.group(2) else ""
        return (destination, "", when)

    return ("", "", "")


def calc_success_rate(pots_planted, viable):
    """Calculate success rate percentage. Returns empty string if not calculable."""
    try:
        pots = int(float(pots_planted))
        viab = int(float(viable))
        if pots > 0:
            rate = round(viab / pots * 100)
            return str(rate)
    except (ValueError, TypeError, ZeroDivisionError):
        pass
    return ""


def load_plant_types(csv_path):
    """Load plant types keyed by farmos_name for enrichment lookup."""
    db = {}
    if not csv_path.exists():
        print(f"  Warning: plant_types.csv not found at {csv_path}")
        return db

    with open(csv_path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = row.get("farmos_name", "").strip()
            if name:
                db[name] = {
                    "botanical_name": row.get("botanical_name", "").strip(),
                    "strata": row.get("strata", "").strip(),
                    "succession_stage": row.get("succession_stage", "").strip(),
                    "source": row.get("source", "").strip(),
                }
    return db


def transform(input_path, output_path, plant_types_path):
    """Transform raw nursery CSV into enriched format."""
    print(f"Loading plant types from {plant_types_path}...")
    plant_db = load_plant_types(plant_types_path)
    print(f"  Loaded {len(plant_db)} plant types")

    print(f"Reading raw nursery CSV from {input_path}...")
    rows = []
    unmapped = set()
    locations = set()

    with open(input_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_location = row.get("Location", "").strip()
            raw_common = row.get("Common Name", "").strip()
            raw_variety = row.get("Variety", "").strip()
            raw_process = row.get("Growing Process", "").strip()
            raw_date = row.get("Seeding/Planting Date", "").strip()
            raw_pots = row.get("Pots Planted", "").strip()
            raw_viable = row.get("Viable Plants", "").strip()
            raw_nrtt = row.get("Not RTT", "").strip()
            raw_rtt = row.get("RTT", "").strip()
            raw_notes = row.get("Notes", "").strip()

            if not raw_location or not raw_common:
                continue

            # Extract location ID
            loc_id = extract_location_id(raw_location)
            locations.add(loc_id)

            # Normalize species
            common_name, variety = normalize_species(raw_common, raw_variety)

            # Build farmos_name
            farmos_name = build_farmos_name(common_name, variety)

            # Look up enrichment data
            enrichment = plant_db.get(farmos_name, {})
            if not enrichment:
                # Try without variety
                enrichment = plant_db.get(common_name, {})
                if not enrichment:
                    unmapped.add(farmos_name)

            botanical_name = enrichment.get("botanical_name", "")
            strata = enrichment.get("strata", "")
            succession = enrichment.get("succession_stage", "")
            source = enrichment.get("source", "")

            # Process normalization (lowercase for consistency)
            process = raw_process.strip().lower() if raw_process else ""

            # Extract destination info from notes
            destination, how_many, when = extract_destination_info(raw_notes)

            # Calculate success rate
            success_rate = calc_success_rate(raw_pots, raw_viable)

            rows.append({
                "Location ID": loc_id,
                "Species (farmOS)": farmos_name,
                "Common Name": common_name,
                "Variety": variety,
                "Botanical Name": botanical_name,
                "Strata": strata,
                "Succession": succession,
                "Source": source,
                "Process": process,
                "Seeding/Planting Date": raw_date,
                "Pots Planted": raw_pots,
                "Viable (Mar 20)": raw_viable,
                "Success Rate %": success_rate,
                "Not RTT": raw_nrtt,
                "RTT": raw_rtt,
                "Destination": destination,
                "How Many": how_many,
                "When": when,
            })

    print(f"  Read {len(rows)} rows across {len(locations)} locations")

    # Write enriched CSV
    print(f"Writing enriched CSV to {output_path}...")
    fieldnames = [
        "Location ID", "Species (farmOS)", "Common Name", "Variety",
        "Botanical Name", "Strata", "Succession", "Source",
        "Process", "Seeding/Planting Date", "Pots Planted",
        "Viable (Mar 20)", "Success Rate %", "Not RTT", "RTT",
        "Destination", "How Many", "When",
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"  Wrote {len(rows)} rows")

    # Report unmapped species
    if unmapped:
        print(f"\n  UNMAPPED SPECIES ({len(unmapped)}):")
        for name in sorted(unmapped):
            print(f"    - {name}")

    # Summary
    print(f"\nSummary:")
    print(f"  Total rows:      {len(rows)}")
    print(f"  Locations:       {len(locations)}")
    print(f"  Mapped species:  {len(rows) - sum(1 for r in rows if r['Species (farmOS)'] in unmapped)}")
    print(f"  Unmapped:        {len(unmapped)} unique species")

    # List locations
    print(f"\nLocations found:")
    for loc in sorted(locations):
        count = sum(1 for r in rows if r["Location ID"] == loc)
        print(f"    {loc}: {count} entries")


def main():
    parser = argparse.ArgumentParser(
        description="Transform raw nursery CSV into enriched format for generate_nursery_pages.py"
    )
    parser.add_argument(
        "--input",
        default="",
        help="Path to raw nursery CSV (default: auto-detect from Downloads)",
    )
    parser.add_argument(
        "--output",
        default="knowledge/nursery_inventory_sheet_march2026.csv",
        help="Path to output enriched CSV",
    )
    parser.add_argument(
        "--plants",
        default="knowledge/plant_types.csv",
        help="Path to plant_types.csv for enrichment",
    )
    args = parser.parse_args()

    input_path = Path(args.input) if args.input else Path(
        "/Users/agnes/Downloads/nursery_inventory_20march2026 - nursery_inventory_20march2026.csv"
    )
    output_path = Path(args.output)
    plants_path = Path(args.plants)

    if not input_path.exists():
        print(f"Error: input file not found: {input_path}")
        return

    transform(input_path, output_path, plants_path)


if __name__ == "__main__":
    main()
