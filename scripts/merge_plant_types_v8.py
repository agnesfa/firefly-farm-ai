#!/usr/bin/env python3
"""Merge plant types from Google Sheet (Claire's enrichments) + CSV (uncorrupted numerics).

The Google Sheet has:
  - ~45 new plant types Claire added
  - Enriched source fields with provenance detail
  - 2 strata corrections
  - New botanical/description/function data for some entries
  - BUT: 80+ entries with date-corrupted lifespan_years and lifecycle_years

The CSV (v7, 222 entries) has:
  - Correct lifespan_years and lifecycle_years (never corrupted)
  - Original data for all existing entries

Strategy:
  1. For entries in BOTH: take Sheet enrichments, keep CSV lifespan/lifecycle
  2. For entries ONLY in Sheet (new): take all Sheet data, flag corrupted numerics
  3. For entries ONLY in CSV (renamed by Claire): map old→new name via Sheet
  4. Handle duplicates (Beetroot x3, Carrot x3, Spinach x3)
  5. Output: clean v8 CSV + report

Usage:
  python scripts/merge_plant_types_v8.py --dry-run     # Preview changes
  python scripts/merge_plant_types_v8.py                # Write v8 CSV
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime

# Columns in output CSV
COLUMNS = [
    "common_name", "variety", "farmos_name", "botanical_name", "crop_family",
    "origin", "description", "lifespan_years", "lifecycle_years", "maturity_days",
    "strata", "succession_stage", "plant_functions", "harvest_days",
    "germination_time", "transplant_days", "source",
]

# Fields where Sheet data takes priority (Claire's enrichments)
SHEET_PRIORITY_FIELDS = [
    "common_name", "variety", "farmos_name", "botanical_name", "crop_family",
    "origin", "description", "strata", "succession_stage", "plant_functions",
    "source", "maturity_days", "harvest_days", "germination_time", "transplant_days",
]

# Fields where CSV takes priority (uncorrupted numeric ranges)
CSV_PRIORITY_FIELDS = ["lifespan_years", "lifecycle_years"]

# Known renames: old CSV name → new Sheet name
# Built from the diff analysis: 22 CSV names not in Sheet, 45 Sheet names not in CSV
# These are 1:1 renames where Claire changed the naming convention
RENAMES = {
    "Ball Honey Myrtle": "Melaleuca (Ball Honey Myrtle)",
    "Banana (Cavendish)": "Banana",  # dropped variety — just "Banana" now
    "Broad Bean": "Broad Bean (Long Pod)",
    "Broccoli": "Broccoli (Summer Green)",
    "Cabbage (Savoy)": "Cabbage (Savoy Vertu)",
    "Clover (Red)": "Clover (Red Persian)",
    "Clover (White)": "Clover (White Haifa)",
    "Cowpea": "Cowpea (Red)",
    "Galangal": "Ginger - Galangal",
    "Kale (Tuscan)": "Kale (Nero di Toscana)",
    "Marigold (French)": "Marigold (French - Dwarf)",
    "Parsnip": "Parsnip (Hollow Grown)",
    "Plum (Generic)": "Plum",
    "Pluot (Black Adder)": "Plum - Pluot (Black Adder)",
    "Pumpkin (Generic)": "Pumpkin",
    "Radish (Generic)": "Radish",
    "Snow in Summer (Melaleuca) (Linariifolia)": "Melaleuca (Snow in Summer)",
    "Spinach (Generic)": "Spinach",
    "Tarragon": "Tarragon (Mexican)",  # Claire split into Mexican + Russian
    "Tomato (Marmande)": "Tomato (Rouge de Marmande)",
    "Watermelon": "Watermelon (Sugar baby)",
    "Wattle (Generic)": "Wattle",
}

# Correct lifespan/lifecycle for new entries (where Sheet has date corruption)
# Research-based values for species not in our CSV
NEW_ENTRY_NUMERICS = {
    "Avocado (Hass)": {"lifespan_years": "50-200", "lifecycle_years": "10-20"},
    "Bean - Climbing (Blue Lake)": {"lifespan_years": "1", "lifecycle_years": "0.5"},
    "Bean - Climbing (Purple King)": {"lifespan_years": "1", "lifecycle_years": "0.5"},
    "Bean - Dwarf (Borlotti)": {"lifespan_years": "1", "lifecycle_years": "0.5"},
    "Borage (Blue Flower)": {"lifespan_years": "1", "lifecycle_years": "0.5"},
    "Borage (White Flower)": {"lifespan_years": "1", "lifecycle_years": "0.5"},
    "Broad Bean (Long Pod)": {"lifespan_years": "1", "lifecycle_years": "0.5"},
    "Broccoletti (Raab Rapini)": {"lifespan_years": "1", "lifecycle_years": "0.5"},
    "Broccoli (Summer Green)": {"lifespan_years": "1", "lifecycle_years": "0.5"},
    "Bunnya Pine": {"lifespan_years": "500-1000", "lifecycle_years": "10-20"},
    "Cabbage (Savoy Vertu)": {"lifespan_years": "1", "lifecycle_years": "0.5"},
    "Chilli (Big Jim)": {"lifespan_years": "1-3", "lifecycle_years": "0.5"},
    "Chives - Garlic": {"lifespan_years": "3-5", "lifecycle_years": "3-10"},
    "Clover (Crimson)": {"lifespan_years": "3-5", "lifecycle_years": "1-3"},
    "Clover (Red Persian)": {"lifespan_years": "2-3", "lifecycle_years": "1-3"},
    "Clover (White Haifa)": {"lifespan_years": "3-5", "lifecycle_years": "1-3"},
    "Coffee (Arabica)": {"lifespan_years": "50-100", "lifecycle_years": "20+"},
    "Cowpea (Red)": {"lifespan_years": "1", "lifecycle_years": "0.5"},
    "Cucumber (Space Master)": {"lifespan_years": "1", "lifecycle_years": "0.5"},
    "Eggplant (Long Purple)": {"lifespan_years": "1-3", "lifecycle_years": "0.5"},
    "Ginger - Galangal": {"lifespan_years": "3-5", "lifecycle_years": "3-10"},
    "Kale (Nero di Toscana)": {"lifespan_years": "2", "lifecycle_years": "1-3"},
    "Marigold (African)": {"lifespan_years": "1", "lifecycle_years": "0.5"},
    "Marigold (French - Dwarf)": {"lifespan_years": "1", "lifecycle_years": "0.5"},
    "Melaleuca (Ball Honey Myrtle)": {"lifespan_years": "20-50", "lifecycle_years": "3-10"},
    "Melaleuca (Snow in Summer)": {"lifespan_years": "20-50", "lifecycle_years": "3-10"},
    "Parsnip (Hollow Grown)": {"lifespan_years": "2", "lifecycle_years": "1-3"},
    "Peanut": {"lifespan_years": "1", "lifecycle_years": "0.5"},
    "Plum": {"lifespan_years": "20-30", "lifecycle_years": "3-10"},
    "Plum - Pluot (Black Adder)": {"lifespan_years": "20-30", "lifecycle_years": "3-10"},
    "Pumpkin": {"lifespan_years": "1", "lifecycle_years": "0.5"},
    "Pumpkin (Golden Nugget)": {"lifespan_years": "1", "lifecycle_years": "0.5"},
    "Radish": {"lifespan_years": "1", "lifecycle_years": "0.5"},
    "Radish (red - Sparkler)": {"lifespan_years": "1", "lifecycle_years": "0.5"},
    "Radish (red - scarlett globe)": {"lifespan_years": "1", "lifecycle_years": "0.5"},
    "Shallot": {"lifespan_years": "3-5", "lifecycle_years": "3-10"},
    "Spinach": {"lifespan_years": "2", "lifecycle_years": "1-3"},
    "Sunflower (Sun King)": {"lifespan_years": "1", "lifecycle_years": "0.5"},
    "Tarragon (Mexican)": {"lifespan_years": "3-5", "lifecycle_years": "3-10"},
    "Tarragon (Russian)": {"lifespan_years": "3-5", "lifecycle_years": "3-10"},
    "Tomato (Rouge de Marmande)": {"lifespan_years": "1-3", "lifecycle_years": "0.5"},
    "Turnip (Purple top)": {"lifespan_years": "2", "lifecycle_years": "0.5"},
    "Watermelon (Sugar baby)": {"lifespan_years": "1", "lifecycle_years": "0.5"},
    "Wattle": {"lifespan_years": "10-20", "lifecycle_years": "3-10"},
    "Yarrow": {"lifespan_years": "5-10", "lifecycle_years": "3-10"},
}


def is_date_corrupted(value):
    """Check if a value looks like a corrupted date instead of a numeric range."""
    s = str(value or "").strip()
    if not s:
        return False
    return "2026" in s or "GMT" in s or "00:00:00" in s


def decode_date_as_range(value):
    """Recover the original 'd-m' range from a date-corrupted value.

    Google Sheets auto-interpreted values like '3-10' as dates (3rd October).
    The API returns these as full date strings. We can recover the original
    by extracting day and month: '2026-10-03' → day=3, month=10 → '3-10'.

    Returns the recovered string, or None if not a recognizable date pattern.
    """
    s = str(value or "").strip()
    if not s:
        return None

    # Try parsing various date formats from the API
    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
        try:
            dt = datetime.strptime(s[:19], fmt)
            day = dt.day
            month = dt.month
            return f"{day}-{month}"
        except (ValueError, IndexError):
            continue

    # Try the JavaScript date format: "Mon Mar 01 2026 19:00:00 GMT+1100 ..."
    # These come from the Apps Script API
    try:
        # Extract just the date part
        parts = s.split()
        if len(parts) >= 4 and parts[3].startswith("202"):
            month_names = {
                "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
                "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
            }
            month = month_names.get(parts[1])
            day = int(parts[2])
            if month:
                return f"{day}-{month}"
    except (ValueError, IndexError):
        pass

    return None


def load_csv(path):
    """Load CSV into dict keyed by farmos_name."""
    entries = {}
    with open(path) as f:
        for row in csv.DictReader(f):
            entries[row["farmos_name"]] = dict(row)
    return entries


def load_sheet(path):
    """Load Sheet JSON into dict keyed by farmos_name. Handle duplicates."""
    with open(path) as f:
        data = json.load(f)

    entries = {}
    duplicates = []
    for pt in data["plant_types"]:
        name = pt.get("farmos_name", "").strip()
        if not name:
            continue
        if name in entries:
            duplicates.append(name)
        else:
            entries[name] = pt
    return entries, duplicates


def merge(csv_entries, sheet_entries, dry_run=False):
    """Merge Sheet enrichments with CSV uncorrupted numerics."""
    merged = []
    report = {
        "matched": [],
        "renamed": [],
        "new_from_sheet": [],
        "csv_only_dropped": [],
        "enrichments": [],
        "strata_changes": [],
        "date_fixes": [],
        "warnings": [],
    }

    # Build reverse rename map: new_name → old_name
    reverse_renames = {v: k for k, v in RENAMES.items()}

    # Track which CSV entries have been consumed
    csv_consumed = set()

    # Process all Sheet entries (they represent Claire's current view)
    for sheet_name, sheet_row in sorted(sheet_entries.items()):
        row = {}

        # Find matching CSV entry (direct match or via rename)
        csv_row = None
        csv_name = None
        if sheet_name in csv_entries:
            csv_row = csv_entries[sheet_name]
            csv_name = sheet_name
        elif sheet_name in reverse_renames:
            old_name = reverse_renames[sheet_name]
            if old_name in csv_entries:
                csv_row = csv_entries[old_name]
                csv_name = old_name
                report["renamed"].append(f"{old_name} → {sheet_name}")

        if csv_row:
            csv_consumed.add(csv_name)
            report["matched"].append(sheet_name)

            # Merge: Sheet enrichments + date recovery
            for field in COLUMNS:
                sheet_val = str(sheet_row.get(field, "") or "").strip()
                csv_val = str(csv_row.get(field, "") or "").strip()

                if is_date_corrupted(sheet_val):
                    # Recover the original value by decoding the date
                    recovered = decode_date_as_range(sheet_val)
                    if recovered:
                        row[field] = recovered
                        if csv_val and recovered != csv_val:
                            report["date_fixes"].append(
                                f"{sheet_name}.{field}: decoded '{sheet_val[:30]}' → '{recovered}' (CSV had '{csv_val}')"
                            )
                        else:
                            report["date_fixes"].append(
                                f"{sheet_name}.{field}: decoded '{sheet_val[:30]}' → '{recovered}'"
                            )
                    else:
                        # Can't decode — fall back to CSV
                        row[field] = csv_val
                        report["warnings"].append(
                            f"{sheet_name}.{field}: date-corrupted, could not decode, using CSV fallback"
                        )
                elif sheet_val:
                    # Sheet has data — use it (this captures all enrichments)
                    row[field] = sheet_val
                    if csv_val and sheet_val != csv_val:
                        if field == "strata":
                            report["strata_changes"].append(
                                f"{sheet_name}: {csv_val} → {sheet_val}"
                            )
                        elif field == "source":
                            pass  # Source enrichments are expected, don't log each one
                        else:
                            report["enrichments"].append(
                                f"{sheet_name}.{field}: '{csv_val[:40]}' → '{sheet_val[:40]}'"
                            )
                else:
                    # Sheet empty, keep CSV value
                    row[field] = csv_val
        else:
            # New entry from Sheet only
            report["new_from_sheet"].append(sheet_name)
            for field in COLUMNS:
                val = str(sheet_row.get(field, "") or "").strip()

                if is_date_corrupted(val):
                    # Try to decode the date back to the original range
                    recovered = decode_date_as_range(val)
                    if recovered:
                        row[field] = recovered
                        report["date_fixes"].append(
                            f"{sheet_name}.{field}: decoded '{val[:30]}' → '{recovered}'"
                        )
                    elif sheet_name in NEW_ENTRY_NUMERICS and field in NEW_ENTRY_NUMERICS[sheet_name]:
                        # Fall back to hardcoded research values
                        row[field] = NEW_ENTRY_NUMERICS[sheet_name][field]
                        report["date_fixes"].append(
                            f"{sheet_name}.{field}: '{val[:30]}' → '{row[field]}' (research fallback)"
                        )
                    else:
                        row[field] = ""
                        report["warnings"].append(
                            f"MISSING NUMERIC: {sheet_name}.{field} is date-corrupted "
                            f"and could not be decoded"
                        )
                else:
                    row[field] = val

        merged.append(row)

    # Check for CSV entries not consumed (shouldn't happen if RENAMES is complete)
    for csv_name in sorted(csv_entries.keys()):
        if csv_name not in csv_consumed:
            # Check if it was a rename source
            if csv_name in RENAMES:
                # Already handled via reverse_renames
                pass
            else:
                report["csv_only_dropped"].append(csv_name)
                report["warnings"].append(
                    f"CSV entry '{csv_name}' not found in Sheet and not in RENAMES — DROPPED"
                )

    return merged, report


def main():
    parser = argparse.ArgumentParser(description="Merge plant types v8")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    parser.add_argument(
        "--csv", default="knowledge/plant_types.csv", help="Input CSV (v7)"
    )
    parser.add_argument(
        "--sheet", default="/tmp/sheet_plant_types.json", help="Sheet JSON dump"
    )
    parser.add_argument(
        "--output", default="knowledge/plant_types.csv", help="Output CSV path"
    )
    args = parser.parse_args()

    print(f"Loading CSV: {args.csv}")
    csv_entries = load_csv(args.csv)
    print(f"  {len(csv_entries)} entries")

    print(f"Loading Sheet: {args.sheet}")
    sheet_entries, duplicates = load_sheet(args.sheet)
    print(f"  {len(sheet_entries)} unique entries")
    if duplicates:
        print(f"  ⚠️  Duplicates found (using first occurrence): {duplicates}")

    print("\nMerging...")
    merged, report = merge(csv_entries, sheet_entries, args.dry_run)

    # Print report
    print(f"\n{'='*60}")
    print(f"MERGE REPORT")
    print(f"{'='*60}")
    print(f"Total output entries: {len(merged)}")
    print(f"Matched (CSV↔Sheet): {len(report['matched'])}")
    print(f"Renamed: {len(report['renamed'])}")
    print(f"New from Sheet: {len(report['new_from_sheet'])}")
    print(f"Strata changes: {len(report['strata_changes'])}")
    print(f"Date fixes applied: {len(report['date_fixes'])}")
    print(f"Warnings: {len(report['warnings'])}")

    if report["renamed"]:
        print(f"\n--- RENAMES ({len(report['renamed'])}) ---")
        for r in report["renamed"]:
            print(f"  {r}")

    if report["new_from_sheet"]:
        print(f"\n--- NEW FROM SHEET ({len(report['new_from_sheet'])}) ---")
        for n in report["new_from_sheet"]:
            print(f"  + {n}")

    if report["strata_changes"]:
        print(f"\n--- STRATA CHANGES ({len(report['strata_changes'])}) ---")
        for s in report["strata_changes"]:
            print(f"  {s}")

    if report["enrichments"]:
        print(f"\n--- FIELD ENRICHMENTS ({len(report['enrichments'])}) ---")
        for e in report["enrichments"]:
            print(f"  {e}")

    if report["date_fixes"]:
        print(f"\n--- DATE FIXES ({len(report['date_fixes'])}) ---")
        for d in report["date_fixes"]:
            print(f"  {d}")

    if report["warnings"]:
        print(f"\n--- ⚠️  WARNINGS ({len(report['warnings'])}) ---")
        for w in report["warnings"]:
            print(f"  {w}")

    if report["csv_only_dropped"]:
        print(f"\n--- CSV-ONLY DROPPED ({len(report['csv_only_dropped'])}) ---")
        for c in report["csv_only_dropped"]:
            print(f"  - {c}")

    # Validate: check for remaining date corruption in output
    corrupt_remaining = 0
    for row in merged:
        for field in CSV_PRIORITY_FIELDS:
            if is_date_corrupted(row.get(field, "")):
                corrupt_remaining += 1
                print(f"  ❌ STILL CORRUPT: {row['farmos_name']}.{field} = {row[field]}")
    if corrupt_remaining:
        print(f"\n❌ {corrupt_remaining} date-corrupted fields remain in output!")
    else:
        print(f"\n✅ Zero date corruption in output")

    if args.dry_run:
        print(f"\n[DRY RUN] Would write {len(merged)} entries to {args.output}")
    else:
        # Back up existing CSV
        if os.path.exists(args.output):
            backup = args.output.replace(".csv", "_v7_backup.csv")
            if not os.path.exists(backup):
                import shutil
                shutil.copy2(args.output, backup)
                print(f"\nBackup saved: {backup}")

        with open(args.output, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(merged)
        print(f"\n✅ Written {len(merged)} entries to {args.output}")


if __name__ == "__main__":
    main()
