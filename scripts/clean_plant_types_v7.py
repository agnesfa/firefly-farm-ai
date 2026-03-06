#!/usr/bin/env python3
"""
Clean plant_types CSV v7 for Firefly Corner Farm.

Reads Claire's consolidated plant type list (exported from the NURSERY ACTIVITY
spreadsheet), applies data quality fixes, and produces the cleaned v7 reference CSV.

Fixes applied:
- Drop v6 reference column (column 0) and 11 empty trailing columns
- Rename column headers (lifespan → lifespan_years, lifecycle → lifecycle_years)
- Strip "YEAR"/"YEARS" from lifecycle data values
- Convert "<1" lifecycle to "0.5"
- Convert ">X" lifecycle to "X+"
- Fix Passionfruit lifespan Excel date bug (46149 → 5-7)
- Fix double spaces in names
- Fix trailing whitespace
- Fix botanical typo Psydium → Psidium
- Fix variety typo Hawaian → Hawaiian
- Merge Pigeon Pea duplicate (one plant type, note both sources)
- Standardize source values
- Add derived farmos_name column

Also generates a name mapping CSV for farmOS migration.
"""

import csv
import re
import os
import json
from collections import Counter

INPUT_FILE = "/Users/agnes/Downloads/NURSERY ACTIVITY 05 MAR 2026.xlsx - firefly_plant_types.csv"
OUTPUT_FILE = "/Users/agnes/Repos/FireflyCorner/knowledge/plant_types_v7.csv"
MAPPING_FILE = "/Users/agnes/Repos/FireflyCorner/knowledge/plant_type_name_mapping.csv"
OLD_CSV = "/Users/agnes/Repos/FireflyCorner/knowledge/plant_types.csv"
FARMOS_EXPORT = "/Users/agnes/Repos/FireflyCorner/exports/farmos_export_20260304/taxonomy/plant_type_terms.json"

# Source standardization map
SOURCE_MAP = {
    'Greenpatch Seeds': 'Greenpatch Organic Seeds',
    'Various nurseries': 'Various',
    'Various seed suppliers': 'Various',
    'Various suppliers': 'Various',
    'Greengrocer (saved seed)': 'Saved seed (greengrocer)',
    'Supermarket (saved seed)': 'Saved seed (supermarket)',
}

def clean_lifecycle(val):
    """Strip YEAR/YEARS text, convert <1 to 0.5, >X to X+."""
    if not val:
        return val
    # Remove YEAR/YEARS (case-insensitive)
    val = re.sub(r'\s*YEARS?\s*$', '', val, flags=re.IGNORECASE).strip()
    # Convert <1 to 0.5
    if val == '<1':
        val = '0.5'
    # Convert >X to X+ (e.g., >20 → 20+, >10 → 10+)
    m = re.match(r'^>(\d+)$', val)
    if m:
        val = f"{m.group(1)}+"
    return val

def clean_name(name):
    """Fix double spaces, trim whitespace."""
    name = name.strip()
    name = re.sub(r'\s{2,}', ' ', name)
    return name

def build_farmos_name(common_name, variety):
    """Build the farmOS plant_type taxonomy term name."""
    cn = clean_name(common_name)
    v = clean_name(variety) if variety else ''

    # Drop "(Generic)" varieties - these are catch-all entries
    # The farmOS name is just the common_name
    if v.lower() in ('(generic)', 'generic', ''):
        return cn

    # Strip parentheses from variety if already wrapped
    v_clean = v.strip('()')

    return f"{cn} ({v_clean})"

def main():
    # Read input
    with open(INPUT_FILE, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        raw_headers = next(reader)
        raw_rows = list(reader)

    print(f"Input: {len(raw_rows)} rows, {len(raw_headers)} columns")

    # Read old CSV for v6 name reference
    v6_names = {}
    with open(OLD_CSV, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            v6_names[row['common_name']] = row
    print(f"Old CSV: {len(v6_names)} records")

    # Read farmOS taxonomy
    farmos_names = {}
    with open(FARMOS_EXPORT) as f:
        farmos_data = json.load(f)
    farmos_terms = farmos_data if isinstance(farmos_data, list) else farmos_data.get('data', [])
    for t in farmos_terms:
        name = t.get('attributes', {}).get('name', '') or t.get('name', '')
        farmos_names[name] = t.get('id', '')
    print(f"farmOS: {len(farmos_names)} plant types")

    # Process rows
    cleaned = []
    pigeon_pea_sources = []
    pigeon_pea_row = None
    skipped = 0

    for i, row in enumerate(raw_rows):
        if len(row) < 17:
            print(f"  WARNING: Row {i+2} has only {len(row)} columns, skipping")
            skipped += 1
            continue

        v6_name = row[0].strip()
        common_name = clean_name(row[1])
        variety = clean_name(row[2])
        botanical = row[3].strip()
        crop_family = row[4].strip()
        origin = row[5].strip()
        description = row[6].strip()
        lifespan = row[7].strip()
        lifecycle = row[8].strip()
        maturity_days = row[9].strip()
        strata = row[10].strip().lower()
        succession = row[11].strip().lower()
        functions = row[12].strip()
        harvest_days = row[13].strip()
        germination = row[14].strip()
        transplant_days = row[15].strip()
        source = row[16].strip()

        # --- FIXES ---

        # 1. Botanical typo
        botanical = botanical.replace('Psydium', 'Psidium')

        # 2. Variety typo
        if variety == 'Hawaian':
            variety = 'Hawaiian'

        # 3. Passionfruit lifespan Excel date bug
        if common_name.startswith('Passionfruit') and lifespan == '46149':
            lifespan = '5-7'
            print(f"  Fixed Passionfruit lifespan: 46149 -> 5-7")

        # 4. Lifecycle cleanup
        lifecycle = clean_lifecycle(lifecycle)

        # 5. Source standardization
        if source in SOURCE_MAP:
            source = SOURCE_MAP[source]

        # 6. Pigeon Pea merge
        if common_name == 'Pigeon Pea' and not variety:
            pigeon_pea_sources.append(source)
            if pigeon_pea_row is None:
                pigeon_pea_row = len(cleaned)
                # Will add later, use first occurrence's data
                entry = {
                    'v6_name': v6_name,
                    'common_name': common_name,
                    'variety': variety,
                    'botanical_name': botanical,
                    'crop_family': crop_family,
                    'origin': origin,
                    'description': description,
                    'lifespan_years': lifespan,
                    'lifecycle_years': lifecycle,
                    'maturity_days': maturity_days,
                    'strata': strata,
                    'succession_stage': succession,
                    'plant_functions': functions,
                    'harvest_days': harvest_days,
                    'germination_time': germination,
                    'transplant_days': transplant_days,
                    'source': source,  # Will be updated after merge
                }
                cleaned.append(entry)
            else:
                print(f"  Merged Pigeon Pea duplicate (source: {source})")
                skipped += 1
            continue

        entry = {
            'v6_name': v6_name,
            'common_name': common_name,
            'variety': variety,
            'botanical_name': botanical,
            'crop_family': crop_family,
            'origin': origin,
            'description': description,
            'lifespan_years': lifespan,
            'lifecycle_years': lifecycle,
            'maturity_days': maturity_days,
            'strata': strata,
            'succession_stage': succession,
            'plant_functions': functions,
            'harvest_days': harvest_days,
            'germination_time': germination,
            'transplant_days': transplant_days,
            'source': source,
        }
        cleaned.append(entry)

    # Finalize Pigeon Pea source (combine sources)
    if pigeon_pea_row is not None and pigeon_pea_sources:
        cleaned[pigeon_pea_row]['source'] = ', '.join(sorted(set(pigeon_pea_sources)))
        print(f"  Pigeon Pea sources combined: {cleaned[pigeon_pea_row]['source']}")

    print(f"\nCleaned: {len(cleaned)} records ({skipped} skipped/merged)")

    # Build farmos_name for each entry
    for entry in cleaned:
        entry['farmos_name'] = build_farmos_name(entry['common_name'], entry['variety'])

    # Validate uniqueness
    farmos_name_counts = Counter(e['farmos_name'] for e in cleaned)
    dupes = {k: v for k, v in farmos_name_counts.items() if v > 1}
    if dupes:
        print(f"\nDUPLICATE farmos_names: {dupes}")
    else:
        print(f"\nAll {len(cleaned)} farmos_names are unique.")

    # Write cleaned CSV
    output_headers = [
        'common_name', 'variety', 'farmos_name',
        'botanical_name', 'crop_family', 'origin', 'description',
        'lifespan_years', 'lifecycle_years', 'maturity_days',
        'strata', 'succession_stage', 'plant_functions',
        'harvest_days', 'germination_time', 'transplant_days', 'source'
    ]

    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=output_headers, extrasaction='ignore')
        writer.writeheader()
        for entry in sorted(cleaned, key=lambda e: (e['common_name'].lower(), e.get('variety', '').lower())):
            writer.writerow(entry)

    print(f"\nWrote {OUTPUT_FILE}")

    # Build name mapping
    # For each cleaned entry, find what it was called in:
    # 1. The v6 CSV (old common_name)
    # 2. farmOS (existing taxonomy term name)
    # 3. What it should be called in farmOS going forward (farmos_name)

    mapping_rows = []
    for entry in sorted(cleaned, key=lambda e: e['farmos_name'].lower()):
        v6 = entry['v6_name']
        farmos_name = entry['farmos_name']

        # Check if this farmos_name already exists in farmOS
        in_farmos = 'YES' if farmos_name in farmos_names else 'NO'

        # Check if the v6 name exists in farmOS (might need renaming)
        v6_in_farmos = 'YES' if v6 and v6 in farmos_names else 'NO'

        # Determine action needed
        if farmos_name in farmos_names:
            action = 'EXISTS -- no change'
        elif v6 and v6 in farmos_names and v6 != farmos_name:
            action = f'RENAME in farmOS: "{v6}" -> "{farmos_name}"'
        elif v6 and v6 in farmos_names and v6 == farmos_name:
            action = 'EXISTS -- no change'
        else:
            action = 'CREATE new taxonomy term'

        mapping_rows.append({
            'farmos_name': farmos_name,
            'common_name': entry['common_name'],
            'variety': entry['variety'],
            'v6_name': v6,
            'in_farmos_now': in_farmos,
            'v6_in_farmos': v6_in_farmos,
            'action': action,
        })

    mapping_headers = ['farmos_name', 'common_name', 'variety', 'v6_name', 'in_farmos_now', 'v6_in_farmos', 'action']
    with open(MAPPING_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=mapping_headers)
        writer.writeheader()
        for row in mapping_rows:
            writer.writerow(row)

    print(f"Wrote {MAPPING_FILE}")

    # Summary
    actions = Counter(r['action'] for r in mapping_rows)
    print(f"\n=== MIGRATION SUMMARY ===")
    for action, count in actions.most_common():
        print(f"  {action}: {count}")

    # Show all RENAME actions
    renames = [r for r in mapping_rows if r['action'].startswith('RENAME')]
    if renames:
        print(f"\n=== RENAME ACTIONS ({len(renames)}) ===")
        for r in renames:
            print(f"  {r['action']}")

    # Show entries that exist in farmOS but have NO match in the new CSV
    existing_farmos_used = set()
    for r in mapping_rows:
        if r['in_farmos_now'] == 'YES':
            existing_farmos_used.add(r['farmos_name'])
        if r['v6_in_farmos'] == 'YES':
            existing_farmos_used.add(r['v6_name'])

    orphaned_farmos = set(farmos_names.keys()) - existing_farmos_used
    if orphaned_farmos:
        print(f"\n=== ORPHANED farmOS ENTRIES (in farmOS, not in new CSV) ({len(orphaned_farmos)}) ===")
        for name in sorted(orphaned_farmos):
            print(f"  {name}")

    # Strata distribution
    print(f"\n=== STRATA DISTRIBUTION ===")
    strata_counts = Counter(e['strata'] for e in cleaned)
    for s, c in sorted(strata_counts.items()):
        print(f"  {s}: {c}")

    # Source distribution (after standardization)
    print(f"\n=== SOURCE DISTRIBUTION (after standardization) ===")
    source_counts = Counter(e['source'] for e in cleaned)
    for s, c in source_counts.most_common():
        print(f"  {s}: {c}")

if __name__ == '__main__':
    main()
