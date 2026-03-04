#!/usr/bin/env python3
"""
Parse Claire's field sheet Excel files into structured JSON.

Input:  fieldsheets/P2R2_Field_Sheets_v2.xlsx, P2R3_Field_Sheets_v2.xlsx, etc.
Output: site/src/data/sections.json — all sections with planting data

Usage:
    python scripts/parse_fieldsheets.py --input fieldsheets/ --output site/src/data/
"""

import argparse
import json
import os
import re
from pathlib import Path

import openpyxl


def parse_section_sheet(ws):
    """Parse a single section sheet from Claire's field sheet format.
    
    Expected format:
    Row 1: "P2 — R3 — Section 0-3"
    Row 2: "2.6m  |  NO TREES  |  First planted: April 2025"
    Row 3: (blank)
    Row 4: Headers (Strata | Species | Notes | Planted | Inventory | TODAY | ...)
    Row 5+: Data rows
    """
    # Parse header info from row 1
    title_cell = str(ws.cell(1, 1).value or "")
    meta_cell = str(ws.cell(2, 1).value or "")
    
    # Extract section ID from title like "P2 — R3 — Section 0-3"
    # Handle various dash types
    title_clean = title_cell.replace("—", "-").replace("–", "-").replace("\u2014", "-").replace("\u2013", "-")
    
    # Try to extract paddock, row, section range
    m = re.search(r'P(\d+)\s*[-–—]\s*R(\d+)\s*[-–—]\s*Section\s+([\d.]+-[\d.]+)', title_clean)
    if not m:
        return None
    
    paddock = int(m.group(1))
    row = int(m.group(2))
    section_range = m.group(3)
    section_id = f"P{paddock}R{row}.{section_range}"
    
    # Parse metadata from row 2
    meta_clean = meta_cell.replace("—", "-").replace("–", "-")
    
    # Extract length
    length_m = re.search(r'([\d.]+)\s*m', meta_clean)
    length = f"{length_m.group(1)}m" if length_m else ""
    
    # Tree or no tree
    has_trees = "WITH TREES" in meta_cell.upper()
    
    # First planted
    first_planted_m = re.search(r'First planted:\s*(\w+\s*\d*)', meta_cell, re.IGNORECASE)
    first_planted = first_planted_m.group(1).strip() if first_planted_m else ""
    
    # Find the inventory date from the header row (row 4)
    inventory_date = ""
    header_row = 4
    for col in range(1, ws.max_column + 1):
        val = str(ws.cell(header_row, col).value or "")
        date_m = re.search(r'(\d{4}-\d{2}-\d{2})', val)
        if date_m:
            inventory_date = date_m.group(1)
            break
    
    # Parse plant data from row 5 onwards
    plants = []
    current_strata = None
    
    for row_idx in range(5, ws.max_row + 1):
        strata_val = str(ws.cell(row_idx, 1).value or "").strip()
        species_val = str(ws.cell(row_idx, 2).value or "").strip()
        notes_val = str(ws.cell(row_idx, 3).value or "").strip()
        
        # Get inventory count (column E = 5, the latest inventory)
        inventory_val = ws.cell(row_idx, 5).value
        
        # Skip empty rows
        if not species_val:
            continue
        
        # Update strata if specified
        if strata_val:
            strata_lower = strata_val.lower()
            if strata_lower in ("emergent", "high", "medium", "low"):
                current_strata = strata_lower
        
        if not current_strata:
            continue
        
        # Parse count
        count = None
        if inventory_val is not None:
            try:
                count = float(inventory_val)
                if count == int(count):
                    count = int(count)
            except (ValueError, TypeError):
                count = None
        
        plants.append({
            "species": species_val,
            "strata": current_strata,
            "count": count,
            "notes": notes_val,
        })
    
    return {
        "id": section_id,
        "paddock": paddock,
        "row": row,
        "range": section_range.replace("-", "–"),
        "length": length,
        "has_trees": has_trees,
        "first_planted": first_planted,
        "inventory_date": inventory_date,
        "plants": plants,
    }


def parse_fieldsheet_file(filepath):
    """Parse all section sheets from a single field sheet Excel file."""
    wb = openpyxl.load_workbook(filepath, data_only=True)
    sections = []
    
    for sheet_name in wb.sheetnames:
        # Skip non-section sheets
        if "log" in sheet_name.lower() or "mapping" in sheet_name.lower():
            continue
        
        ws = wb[sheet_name]
        section = parse_section_sheet(ws)
        if section:
            sections.append(section)
            print(f"  Parsed: {section['id']} — {len(section['plants'])} species")
        else:
            print(f"  Skipped: {sheet_name} (could not parse header)")
    
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
        row["sections"].sort(key=lambda sid: float(sid.split(".")[-1].split("–")[0].split("-")[0]))
        # Calculate total length from last section endpoint
        last_sec = [s for s in sections if s["id"] == row["sections"][-1]][0]
        range_parts = last_sec["range"].replace("–", "-").split("-")
        if len(range_parts) == 2:
            row["total_length"] = f"{range_parts[1]}m"
    
    return rows


def main():
    parser = argparse.ArgumentParser(description="Parse field sheet Excel files into JSON")
    parser.add_argument("--input", default="fieldsheets/", help="Directory containing .xlsx files")
    parser.add_argument("--output", default="site/src/data/", help="Output directory for JSON")
    args = parser.parse_args()
    
    input_dir = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    all_sections = []
    
    # Find and parse all field sheet files
    xlsx_files = sorted(input_dir.glob("*.xlsx"))
    if not xlsx_files:
        print(f"No .xlsx files found in {input_dir}")
        return
    
    for filepath in xlsx_files:
        print(f"\nParsing: {filepath.name}")
        sections = parse_fieldsheet_file(filepath)
        all_sections.extend(sections)
    
    # Build row summaries
    rows = build_row_info(all_sections)
    
    # Write sections.json
    output_file = output_dir / "sections.json"
    output_data = {
        "generated": True,
        "sections": {s["id"]: s for s in all_sections},
        "rows": rows,
    }
    
    with open(output_file, "w") as f:
        json.dump(output_data, f, indent=2)
    
    print(f"\n{'='*50}")
    print(f"Wrote {len(all_sections)} sections across {len(rows)} rows to {output_file}")
    for row_id, row_info in sorted(rows.items()):
        print(f"  {row_id}: {len(row_info['sections'])} sections")


if __name__ == "__main__":
    main()
