#!/usr/bin/env python3
"""
audit_row.py — Build a spreadsheet-vs-farmOS reconciliation MD file for a paddock row.

Reads:
  - Claire's field-sheet Excel file (one tab per section)
  - A farmOS snapshot JSON (from a one-time agent fetch or export)

Writes:
  claude-docs/audits/{ROW}-reconciliation.md

Output format mirrors the P2R5 template (structural findings → per-section
tables with ✓/⚠/🔴 markers → summary of findings).

Usage:
    python scripts/audit_row.py P2R3 \\
        --sheet "fieldsheets/2026FEB-P2R3-Inventory-&-Next-Planting-v2.xlsx" \\
        --farmos /tmp/p2r3_farmos.json \\
        --output claude-docs/audits/P2R3-reconciliation.md
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Species name normalization — map Claire's spreadsheet names to farmOS names
# ---------------------------------------------------------------------------
SPECIES_ALIASES: dict[str, str] = {
    "Basil (Thai)": "Basil - Perennial (Thai)",
    "Basil (Sweet)": "Basil - Sweet (Classic)",
    "Basil - Sweet": "Basil - Sweet (Classic)",
    "Basil Sweet": "Basil - Sweet (Classic)",
    "Basil (Greek)": "Basil - Sweet (Classic)",
    "Cherry Guava (Strawberry)": "Guava (Strawberry)",
    "Cootamundra Wattle": "Wattle - Cootamundra (Baileyana)",
    "Wattle (Cootamundra)": "Wattle - Cootamundra (Baileyana)",
    "Wattle - Cootamundra": "Wattle - Cootamundra (Baileyana)",
    "White Mulberry": "Mulberry (White)",
    "Mulberry (White)": "Mulberry (White)",
    "Tallowood": "Tallowood (Gum)",
    "Tallowood (Gum)": "Tallowood (Gum)",
    "Tea Tree": "Tea Tree Oil (Melaleuca) (Alternifolia)",
    "Tea Tree Oil": "Tea Tree Oil (Melaleuca) (Alternifolia)",
    "Tagasaste": "Tagasaste - Tree Lucerne",
    "Thai Basil": "Basil - Perennial (Thai)",
    "Jacaranda": "Jacaranda",
    "Forest Red Gum": "Forest Red Gum",
    # P2R4 sheet uses these short forms
    "Tomato": "Tomato (Marmande)",
    "Tumeric": "Turmeric",  # common typo
    "Pumpkin": "Pumpkin (Generic)",
    "Cabbage Red": "Cabbage (Red)",
    "Red Cabbage": "Cabbage (Red)",
    "red cabbage": "Cabbage (Red)",
    "cowpea": "Cowpea",
    "Jacaranda (Blue)": "Jacaranda",
    "Pepino Plant": "Pepino plant",
    "nasturtium": "Nasturtium",
    "Nasturtium": "Nasturtium",
    # P2R1 renovation sheet (uppercase, abbreviated)
    "Guava": "Guava",
    "Grape Vine": "Grape Vine",
    "Olive Tree": "Olive",
    "Fig Tree": "Fig",
    "Finger Lime": "Finger Lime",
    "Citrus Yuzu": "Citrus (Yuzu)",
    "Lemon Tree": "Lemon",
    "Pigeon Pea": "Pigeon Pea",
    "Lavender": "Lavender",
    "Rosemary": "Rosemary",
    "Sage": "Sage",
    "Ginger": "Ginger",
    "Comfrey": "Comfrey",
    "Thyme": "Thyme",
    "Oregano": "Oregano",
    "Lemon Balm": "Lemon Balm",
    "Chives": "Chives",
    "Bush Mint": "Mint (Australian)",
    "Geranium Cuttings": "Geranium",
    "Geranium": "Geranium",
}

# Strata labels that are NOT actual plant rows — skip them during parsing
NON_PLANT_STRATA: set[str] = {
    "GREENMANURE",
    "GREEN MANURE",
    "COMPANION PLANT",
    "COMPANION",
    "Placenta",
    "TOTALS",
    "TOTAL",
    "GM TOTAL",
}

# Species Claire treats as annuals or seasonal — absence in farmOS isn't a loss,
# it's the natural end-of-cycle. These match her P2R5 audit's "expected" category.
ANNUAL_SPECIES: set[str] = {
    "Tomato (Marmande)",
    "Zucchini (Blackjack)",
    "Cabbage (Golden Acre)",
    "Cabbage (Red)",
    "Pak Choi",
    "Eggplant",
    "Amaranth",
    "Garlic",  # lifts annually
    "Radish",
    "Sunflower",
    "Cowpea",
    "Broad Bean",
    "Butternut Pumpkin",
    "Pumpkin",
    "Pumpkin (Generic)",
    "Okra",
    "Coriander",
    "Parsley (Italian)",
    "Parsley (Moss Curled)",
    "Borage",  # biennial but Claire lists as annual turnover
    "Nasturtium",
    "Millet",
    "Sunn Hemp",
    "Buckwheat",
    "Corn (Sweet)",
    "Bean (Climbing)",
    "Barley",
    "Basil - Sweet (Classic)",  # treated as annual by Claire
}

# Phrases in the sheet's Notes column that mean Claire already knows the plant is dead
DEAD_MARKERS = {"all dead", "dead", "all lost", "just gone"}


def normalize_species(name: str) -> str:
    """Map a spreadsheet species name to its canonical farmOS form."""
    name = name.strip()
    return SPECIES_ALIASES.get(name, name)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class PlantRow:
    strata: str
    species: str  # normalized
    original_species: str  # as written in sheet
    planted: int | None  # col D 'Planted (init)'
    last_inv: int | None  # col E 'Last Inventory'
    new_total: int | None  # col I 'New TOTAL' — Feb 2026 running total
    notes: str

    @property
    def effective_baseline(self) -> int | None:
        """The most recent count the sheet provides for this row."""
        if self.new_total is not None:
            return self.new_total
        if self.last_inv is not None:
            return self.last_inv
        return self.planted


@dataclass
class SheetSection:
    tab: str
    header: str
    length_m: int | None
    plants: list[PlantRow] = field(default_factory=list)


@dataclass
class FarmosPlant:
    species: str
    count: int | None
    planted_date: str


@dataclass
class FarmosSection:
    section_id: str
    length_m: int | None
    plants: list[FarmosPlant] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Spreadsheet parser (handles the v2 format used for P2R2/P2R3/P2R4)
# ---------------------------------------------------------------------------
# Header-row column detection — the two sheet schemas Claire uses
# Schema A (P2R3, P2R4, P2R5 v2):
#     Strata | Species | Previous Notes | Planted (init) | Last Inventory |
#     New inventory before planting | New Plants (nb) | New Seeds (g) | New TOTAL | Comments
# Schema B (P2R2 15 Mar 2026):
#     Strata | Species | Lifecycle (productive) | Succession Stage | Lifespan |
#     Previous Notes | farmOS Count | New inventory before planting | New Plants (nb) |
#     New Seeds (g) | New TOTAL | Comments

HEADER_ALIASES: dict[str, str] = {
    "strata": "strata",
    "species (farmos_name)": "species",
    "species (farmos name)": "species",
    "species": "species",
    "previous notes": "notes",
    "planted\n(init)": "planted",
    "planted (init)": "planted",
    "last inventory": "last_inv",
    "farmos\ncount": "farmos_count",
    "farmos count": "farmos_count",
    "new plants\n(nb)": "new_plants",
    "new plants (nb)": "new_plants",
    "new total": "new_total",
    "lifecycle\n(productive)": "lifecycle",
    "lifecycle (productive)": "lifecycle",
    "succession\nstage": "succession",
    "succession stage": "succession",
    "lifespan": "lifespan",
    "comments (new notes + to do)": "comments",
    "comments": "comments",
}


def _build_col_map(df: pd.DataFrame) -> dict[str, int]:
    """Read row 3 (the header row) and build {logical_name: column_index}."""
    col_map: dict[str, int] = {}
    for col_idx in range(df.shape[1]):
        cell = df.iloc[3, col_idx]
        if pd.isna(cell):
            continue
        key = str(cell).strip().lower()
        # Normalize whitespace so multi-line headers collapse
        key_clean = " ".join(key.split())
        for alias, logical in HEADER_ALIASES.items():
            alias_clean = " ".join(alias.lower().split())
            if alias_clean == key_clean:
                col_map[logical] = col_idx
                break
    return col_map


def _detect_schema_c(df: pd.DataFrame) -> bool:
    """Schema C = P2R1 spring renovation sheet: lifecycle bracket columns, species in col C.

    Distinctive marker: row 3 starts with 'Lifecycle' and cols 3-8 contain year ranges + 'no tree'.
    """
    if df.shape[1] < 12 or df.shape[0] < 5:
        return False
    try:
        row3 = [str(df.iloc[3, c]).lower() if pd.notna(df.iloc[3, c]) else "" for c in range(min(12, df.shape[1]))]
    except Exception:
        return False
    has_lifecycle = "lifecycle" in row3[0]
    has_year_cols = sum(1 for c in row3[3:8] if "year" in c) >= 2
    has_no_tree = "no tree" in row3[8]
    return has_lifecycle and has_year_cols and has_no_tree


def _parse_schema_c(df: pd.DataFrame, tab_name: str) -> tuple[SheetSection, str] | None:
    """Parse a P2R1-style renovation sheet tab.

    Layout (0-indexed columns):
      0: strata
      1: % surface
      2: species (UPPERCASE)
      3-7: lifecycle brackets (<1yr, 1-3yr, etc.)
      8: pl/sd (initial planted count)
      9: inventory (last inventory)
      10: to do (planned)
      11: seeds g
      12: total (effective baseline)

    Section ID comes from row 2 col 2 (e.g. 'P2R1.0-3').
    """
    # Extract section ID from row 2 col 2
    section_id = None
    try:
        for c in range(df.shape[1]):
            v = df.iloc[2, c]
            if pd.notna(v) and isinstance(v, str) and v.startswith("P2R") and "." in v:
                section_id = v.strip()
                break
    except Exception:
        return None
    if not section_id:
        return None

    length = None
    try:
        for c in range(df.shape[1]):
            v = df.iloc[1, c]
            if pd.notna(v) and isinstance(v, (int, float)):
                length = int(v)
                break
    except Exception:
        pass

    sec = SheetSection(tab=section_id, header=str(df.iloc[0, 0]) if pd.notna(df.iloc[0, 0]) else "", length_m=length)
    last_strata = ""
    for i in range(5, len(df)):
        strata_raw = df.iloc[i, 0]
        species = df.iloc[i, 2]
        planted = df.iloc[i, 8] if df.shape[1] > 8 else None
        last_inv = df.iloc[i, 9] if df.shape[1] > 9 else None
        total = df.iloc[i, 12] if df.shape[1] > 12 else None

        if pd.notna(strata_raw) and str(strata_raw).strip():
            last_strata = str(strata_raw).strip()

        if last_strata.lower() in ("placenta", "pionneer.", "pionneer", "pioneer"):
            # The P2R1 sheet uses these as reference markers — skip after them
            if "green manure" in (str(species) if pd.notna(species) else "").lower():
                break
            # Still keep track of strata but don't use "placenta" as real strata
            strata_eff = ""
        else:
            strata_eff = last_strata

        if pd.isna(species) or not str(species).strip():
            continue

        orig = str(species).strip()
        # Strip FFC markers + "cuttings" / "seedl" hints on the RAW uppercase form first
        upper = orig.upper()
        for suffix in (" FFC CUT", " FFC SEEDL", " FFC", " CUTTINGS", " SEEDL", " CUTTING"):
            if upper.endswith(suffix):
                upper = upper[: -len(suffix)].strip()
                break
        # P2R1 uses UPPERCASE names — title-case them
        cleaned = " ".join(w.capitalize() for w in upper.split())

        sec.plants.append(
            PlantRow(
                strata=strata_eff,
                species=normalize_species(cleaned),
                original_species=orig,
                planted=_to_int(planted),
                last_inv=_to_int(last_inv),
                new_total=_to_int(total),
                notes="",
            )
        )
    return sec, section_id


def parse_sheet(path: Path) -> dict[str, SheetSection]:
    xl = pd.ExcelFile(path)
    sections: dict[str, SheetSection] = {}

    for tab in xl.sheet_names:
        df = pd.read_excel(path, sheet_name=tab, header=None)
        if len(df) < 4:
            continue

        # Try schema C first (P2R1 spring renovation)
        if _detect_schema_c(df):
            result = _parse_schema_c(df, tab)
            if result is not None:
                sec, sid = result
                sections[sid] = sec
            continue

        # Schema A/B: require the tab name to look like a section
        if not (tab.startswith("P2R") or tab.startswith("P1R")):
            continue

        header = str(df.iloc[0, 0]) if pd.notna(df.iloc[0, 0]) else ""

        length = None
        try:
            v = df.iloc[2, 1]
            if pd.notna(v):
                length = int(v)
        except Exception:
            pass

        col_map = _build_col_map(df)
        # Minimum required: strata + species
        if "strata" not in col_map or "species" not in col_map:
            # Fall back to fixed positions (schema A)
            col_map.setdefault("strata", 0)
            col_map.setdefault("species", 1)
            col_map.setdefault("notes", 2)
            col_map.setdefault("planted", 3)
            col_map.setdefault("last_inv", 4)
            col_map.setdefault("new_total", 8)

        sec = SheetSection(tab=tab, header=header, length_m=length)
        last_strata = ""
        for i in range(4, len(df)):
            row_text = " ".join(
                str(v) for v in df.iloc[i].dropna().tolist()
            )
            if "Firefly Corner" in row_text or "Last seeded" in row_text or "GM TOTAL" in row_text:
                break

            def get(key: str):
                idx = col_map.get(key)
                if idx is None or idx >= df.shape[1]:
                    return None
                return df.iloc[i, idx]

            strata_raw = get("strata")
            species = get("species")
            notes = get("notes")
            planted = get("planted")
            last_inv = get("last_inv")
            farmos_count_col = get("farmos_count")
            new_total = get("new_total")

            # Schema B uses 'farmos_count' as the current baseline in place of last_inv
            if last_inv is None and farmos_count_col is not None:
                last_inv = farmos_count_col

            if pd.notna(strata_raw) and str(strata_raw).strip():
                last_strata = str(strata_raw).strip()

            if last_strata in NON_PLANT_STRATA:
                continue
            if pd.isna(species) or not str(species).strip():
                continue
            orig = str(species).strip()
            if orig.upper() in {"TOTALS", "TOTAL", "GM TOTAL", "GREEN MANURE"}:
                continue

            sec.plants.append(
                PlantRow(
                    strata=last_strata,
                    species=normalize_species(orig),
                    original_species=orig,
                    planted=_to_int(planted),
                    last_inv=_to_int(last_inv),
                    new_total=_to_int(new_total),
                    notes="" if pd.isna(notes) else str(notes).strip(),
                )
            )
        sections[tab] = sec
    return sections


def _to_int(v) -> int | None:
    if pd.isna(v):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    try:
        return int(str(v).strip())
    except Exception:
        return None


# ---------------------------------------------------------------------------
# farmOS JSON loader
# ---------------------------------------------------------------------------
def load_farmos(path: Path) -> dict[str, FarmosSection]:
    raw = json.loads(path.read_text())
    out: dict[str, FarmosSection] = {}
    for sid, data in raw["sections"].items():
        sec = FarmosSection(
            section_id=sid,
            length_m=data.get("length_m"),
            plants=[
                FarmosPlant(
                    species=p["species"],
                    count=p.get("count"),
                    planted_date=p.get("planted_date", ""),
                )
                for p in data.get("plants", [])
            ],
        )
        out[sid] = sec
    return out


# ---------------------------------------------------------------------------
# Reconciliation — produces a list of per-section diff rows
# ---------------------------------------------------------------------------
@dataclass
class DiffRow:
    strata: str
    species: str
    sheet_last_inv: int | None
    sheet_planted: int | None
    sheet_new_total: int | None
    farmos_count: int | None
    delta_marker: str  # ✓ ⚠️ 🔴 annual new ℹ️
    note: str


def _has_dead_marker(note: str) -> bool:
    n = note.lower()
    return any(m in n for m in DEAD_MARKERS)


def diff_section(
    sheet: SheetSection | None, farmos: FarmosSection | None
) -> list[DiffRow]:
    rows: list[DiffRow] = []

    def _sum_opt(a, b):
        if a is None and b is None:
            return None
        return (a or 0) + (b or 0)

    sheet_plants: dict[str, PlantRow] = {}
    if sheet:
        for p in sheet.plants:
            # Aggregate duplicate rows in the sheet (e.g. "Lemon" listed twice as
            # "FFC cuttings dead" + "FFC seedlings planted Nov")
            key = p.species
            if key in sheet_plants:
                existing = sheet_plants[key]
                existing.last_inv = _sum_opt(existing.last_inv, p.last_inv)
                existing.planted = _sum_opt(existing.planted, p.planted)
                existing.new_total = _sum_opt(existing.new_total, p.new_total)
                existing.notes = (existing.notes + "; " + p.notes).strip("; ")
            else:
                sheet_plants[key] = PlantRow(
                    strata=p.strata,
                    species=p.species,
                    original_species=p.original_species,
                    planted=p.planted,
                    last_inv=p.last_inv,
                    new_total=p.new_total,
                    notes=p.notes,
                )

    farmos_plants: dict[str, FarmosPlant] = {}
    if farmos:
        for p in farmos.plants:
            if p.species in farmos_plants:
                existing = farmos_plants[p.species]
                existing.count = (existing.count or 0) + (p.count or 0)
            else:
                farmos_plants[p.species] = FarmosPlant(
                    species=p.species,
                    count=p.count,
                    planted_date=p.planted_date,
                )

    all_species = sorted(set(sheet_plants.keys()) | set(farmos_plants.keys()))

    for sp in all_species:
        s = sheet_plants.get(sp)
        f = farmos_plants.get(sp)

        sheet_baseline = s.effective_baseline if s else None
        farmos_ct = f.count if f else None
        strata = s.strata if s else ""
        is_annual = sp in ANNUAL_SPECIES
        dead_per_sheet = s and _has_dead_marker(s.notes)

        # Rows in sheet with NO numbers at all = Claire's "intended / placeholder" rows
        unregistered_in_sheet = (
            s and sheet_baseline is None and not dead_per_sheet
        )
        # A sheet row with baseline=0 is explicitly "zero / not planted" — treat as no claim
        zero_claim = s and sheet_baseline == 0

        note = ""
        if s and not f:
            if dead_per_sheet:
                marker = "✓"
                note = "dead (sheet agrees)"
            elif unregistered_in_sheet:
                marker = "ℹ️"
                note = "listed in sheet without a count — never registered in farmOS"
            elif zero_claim:
                marker = "ℹ️"
                note = "listed as 0 — Claire's 'to add' slot, not yet in farmOS"
            elif is_annual:
                marker = "annual"
                note = f"was {sheet_baseline} — annual, end of cycle"
            else:
                marker = "🔴"
                note = f"in sheet ({sheet_baseline}), missing from farmOS"
        elif f and not s:
            marker = "new"
            note = f"not in sheet — added since (farmOS: {farmos_ct})"
        else:
            if sheet_baseline is None and (farmos_ct is None or farmos_ct == 0):
                marker = "ℹ️"
                note = "listed but no counts either side"
            elif zero_claim and (farmos_ct is None or farmos_ct == 0):
                marker = "✓"
                note = "both zero"
            elif sheet_baseline == farmos_ct:
                marker = "✓"
            elif farmos_ct == 0 and sheet_baseline and sheet_baseline > 0:
                if is_annual:
                    marker = "annual"
                    note = f"was {sheet_baseline} — end of cycle"
                elif dead_per_sheet:
                    marker = "✓"
                    note = "dead (sheet agrees)"
                else:
                    marker = "🔴"
                    note = f"all lost (was {sheet_baseline})"
            elif sheet_baseline and farmos_ct and abs(farmos_ct - sheet_baseline) <= 1:
                marker = "⚠️"
                delta = farmos_ct - sheet_baseline
                note = f"{'+' if delta >= 0 else ''}{delta}"
            elif sheet_baseline and farmos_ct and farmos_ct > sheet_baseline:
                marker = "⚠️"
                note = f"+{farmos_ct - sheet_baseline} since sheet"
            elif sheet_baseline and farmos_ct:
                marker = "⚠️"
                note = f"-{sheet_baseline - farmos_ct} since sheet"
            else:
                marker = "⚠️"
                note = "check counts"

        rows.append(
            DiffRow(
                strata=strata,
                species=sp,
                sheet_last_inv=s.last_inv if s else None,
                sheet_planted=s.planted if s else None,
                sheet_new_total=s.new_total if s else None,
                farmos_count=farmos_ct,
                delta_marker=marker,
                note=note + (f" — {s.notes}" if s and s.notes else ""),
            )
        )
    return rows


def _section_start(section_id: str) -> tuple[int, int]:
    """Sort key — extract the start offset from 'P2R3.15-21' → (3, 15)."""
    try:
        row_part, span = section_id.split(".", 1)
        row_num = int(row_part[-1])
        start = int(span.split("-")[0])
        return (row_num, start)
    except (ValueError, IndexError):
        return (99, 0)


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------
STRATA_ORDER = {"Emergent": 0, "High": 1, "Medium": 2, "Low": 3, "": 4}


def _fmt(v: int | None) -> str:
    if v is None:
        return "—"
    return str(v)


def _find_duplicate_tabs(sheet: dict[str, SheetSection]) -> dict[str, list[str]]:
    """Return {section_id: [other tabs it duplicates]}."""
    out: dict[str, list[str]] = {}
    ids = list(sheet.keys())
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            pa = [(p.species, p.last_inv, p.planted) for p in sheet[a].plants]
            pb = [(p.species, p.last_inv, p.planted) for p in sheet[b].plants]
            if pa and pa == pb:
                out.setdefault(a, []).append(b)
                out.setdefault(b, []).append(a)
    return out


def render_md(
    row: str,
    sheet: dict[str, SheetSection],
    farmos: dict[str, FarmosSection],
    notes: dict[str, str],
) -> str:
    out: list[str] = []
    today = datetime.now().strftime("%Y-%m-%d")
    dup_tabs = _find_duplicate_tabs(sheet)
    out.append(f"# Spreadsheet vs farmOS — {row} Full Comparison\n")
    out.append(f"_Generated: {today}_\n")
    out.append(
        "> Source: Claire's field spreadsheet compared against farmOS current state.  "
        "\n> Sheet columns: `Planted` = initial planting count, `Last inv` = last inventory before new round, `New total` = running total after Feb 2026 planting. The audit uses `New total` when present, else `Last inv`, else `Planted` as the effective sheet baseline.  "
        "\n> Markers: **✓** match · **⚠️** small drift · **🔴** significant loss or data discrepancy · "
        "**annual** expected end-of-cycle (annuals) · **ℹ️** listed in sheet without a count · **new** added since the sheet.\n"
    )

    # --- Structural findings
    out.append("## Key structural findings\n")
    sheet_sections = sorted(sheet.keys())
    farmos_sections = sorted(farmos.keys())
    sheet_only = [s for s in sheet_sections if s not in farmos]
    farmos_only = [s for s in farmos_sections if s not in sheet]
    out.append(
        f"- Spreadsheet tabs: **{len(sheet_sections)}** · farmOS sections: **{len(farmos_sections)}**"
    )
    if farmos_only:
        out.append(
            "- Sections in farmOS but **not in the spreadsheet**: "
            + ", ".join(f"`{s}`" for s in farmos_only)
        )
    if sheet_only:
        out.append(
            "- Sections in spreadsheet but **not in farmOS**: "
            + ", ".join(f"`{s}`" for s in sheet_only)
        )

    # --- Duplicate-tab detection
    seen_pairs: set[tuple[str, str]] = set()
    for a, dups in dup_tabs.items():
        for b in dups:
            pair = tuple(sorted([a, b]))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            out.append(
                f"- 🔴 **CRITICAL DATA INTEGRITY ISSUE:** Spreadsheet tabs `{pair[0]}` and `{pair[1]}` "
                f"contain identical plant rows. These were 'split from' a previous merged section "
                f"but the split was never actually done in the data — any sum over the spreadsheet double-counts this range, "
                f"and any per-section comparison against farmOS will show false losses because the real plants are distributed between the two sections."
            )

    for note_key, note_text in notes.items():
        out.append(f"- {note_text}")
    out.append("")

    # --- Surface section boundary shifts captured in sheet headers
    shifts = []
    for sid in sorted(sheet.keys(), key=_section_start):
        h = sheet[sid].header
        if "(was" in h:
            shifts.append(f"`{sid}` {h[h.find('(was'):].rstrip(')').lstrip('(')}")
    if shifts:
        out.append(
            "- Spreadsheet headers record section-boundary shifts from an earlier layout: "
            + ", ".join(shifts)
        )
    out.append("")

    # --- Section-by-section
    out.append("## Section-by-section comparison\n")

    all_sections = sorted(set(sheet_sections) | set(farmos_sections), key=_section_start)
    for sid in all_sections:
        s = sheet.get(sid)
        f = farmos.get(sid)
        out.append(f"### {sid}\n")
        if s is None:
            out.append(
                f"> **No spreadsheet tab.** This section exists in farmOS with "
                f"**{len(f.plants) if f else 0}** plant records.\n"
            )
        if f is None:
            out.append(
                "> **No farmOS section.** The spreadsheet tab has no corresponding section in farmOS.\n"
            )
        if s and s.header:
            out.append(f"> {s.header}  ")
            out.append(f"> _Sheet length: {s.length_m or '?'}m_\n")
        if sid in dup_tabs:
            twins = ", ".join(f"`{t}`" for t in dup_tabs[sid])
            out.append(
                f"> 🔴 **Duplicated tab** — the spreadsheet data here is identical to {twins}. "
                f"Treat any 🔴 row below as SUSPECT: the plant may actually exist in the twin section. "
                f"Use this table as a reference for *what should exist across the combined range*, "
                f"not as an authoritative per-section inventory.\n"
            )

        rows = diff_section(s, f)
        if not rows:
            out.append("_(empty section)_\n")
            continue

        rows.sort(key=lambda r: (STRATA_ORDER.get(r.strata, 5), r.species))
        out.append("| Strata | Species | Planted | Last inv | New total | farmOS today | Δ | Notes |")
        out.append("|---|---|---|---|---|---|---|---|")
        for r in rows:
            out.append(
                f"| {r.strata or '—'} | {r.species} | {_fmt(r.sheet_planted)} | {_fmt(r.sheet_last_inv)} | {_fmt(r.sheet_new_total)} | {_fmt(r.farmos_count)} | {r.delta_marker} | {r.note} |"
            )
        out.append("")

    # --- Summary of findings
    out.append("## Summary of findings\n")
    counters = {"✓": 0, "⚠️": 0, "🔴": 0, "annual": 0, "ℹ️": 0, "new": 0}
    red_rows: list[tuple[str, DiffRow]] = []
    new_rows: list[tuple[str, DiffRow]] = []
    for sid in all_sections:
        s = sheet.get(sid)
        f = farmos.get(sid)
        for r in diff_section(s, f):
            counters[r.delta_marker] = counters.get(r.delta_marker, 0) + 1
            if r.delta_marker == "🔴":
                red_rows.append((sid, r))
            elif r.delta_marker == "new":
                new_rows.append((sid, r))
    total = sum(counters.values())

    out.append(f"- ✓ **{counters['✓']}** species match sheet ↔ farmOS")
    out.append(f"- ⚠️ **{counters['⚠️']}** species with small drift (±1 or ±2)")
    out.append(f"- 🔴 **{counters['🔴']}** species with significant loss or data discrepancy (needs field verification)")
    out.append(f"- annual **{counters['annual']}** species at natural end of cycle")
    out.append(f"- ℹ️ **{counters['ℹ️']}** species listed in the sheet but never registered with a count")
    out.append(f"- new **{counters['new']}** species in farmOS added since the sheet was written")
    out.append(f"- **{total}** total species rows compared across **{len(all_sections)}** sections\n")

    if red_rows:
        out.append("### 🔴 Rows that need a field check\n")
        out.append("These are the discrepancies that matter. Agnes or James walks the section, confirms on the ground, and either (a) archives the ghost plants, (b) corrects the farmOS count, or (c) records a new planting/seeding log.\n")
        for sid, r in red_rows:
            out.append(f"- **{sid} — {r.species}** ({r.strata}): {r.note}")
        out.append("")

    if new_rows:
        out.append("### new Rows added since the sheet\n")
        out.append("These species exist in farmOS but weren't in Claire's spreadsheet — either she added them after the sheet was written, or they appeared via WWOOFer observation / transcript import. Review to confirm they're real.\n")
        for sid, r in new_rows:
            out.append(f"- **{sid} — {r.species}** ({r.strata}): {_fmt(r.farmos_count)} in farmOS")
        out.append("")
    out.append("")
    out.append("_This file is generated by `scripts/audit_row.py`. Edit that script to change the format for all rows at once._")

    return "\n".join(out)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("row", help="Row ID, e.g. P2R3")
    p.add_argument("--sheet", required=True, help="Path to Claire's Excel fieldsheet")
    p.add_argument("--farmos", required=True, help="Path to farmOS JSON snapshot")
    p.add_argument("--output", required=True, help="Path to write the .md file")
    p.add_argument("--note", action="append", default=[], help="Extra structural note to include")
    args = p.parse_args()

    sheet = parse_sheet(Path(args.sheet))
    farmos = load_farmos(Path(args.farmos))

    notes = {f"n{i}": n for i, n in enumerate(args.note)}
    md = render_md(args.row, sheet, farmos, notes)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md)
    print(f"Wrote {out_path} ({len(md.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
