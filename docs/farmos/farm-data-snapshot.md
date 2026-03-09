# Firefly Corner Farm — Data Snapshot

**Last Export**: 2026-03-09

## Statistics Overview

| Category | Count |
|----------|-------|
| Total Assets | ~550 |
| Total Logs | ~890 |
| Total Taxonomy Terms | ~230 |

## Assets by Type

| Type | Count | Description |
|------|-------|-------------|
| Plant | 404 | Active crops across 33 sections (5 rows) |
| Land | 93 | Paddocks, rows, sections (37 sections incl. 4 gap) |
| Structure | 17 | Buildings, sheds, nursery |
| Material | 14 | Supplies, inputs |
| Water | 11 | Dams, irrigation, keyline trenches |
| Group | 11 | Asset groupings |
| Compost | 5 | Compost systems |
| Equipment | 3 | Farm machinery |

## Logs by Type

| Type | Count | Description |
|------|-------|-------------|
| Observation | ~580 | 442 inventory + ~137 historical inventory |
| Transplanting | ~238 | 7 original + ~230 historical (planted + renovation) |
| Activity | 63 | General farm activities |
| Seeding | 8 | Planting events |
| Lab Test | 6 | Soil/water tests |
| Purchase | 2 | Purchase records |

## Taxonomy Terms

| Vocabulary | Count | Notes |
|------------|-------|-------|
| Plant Types | 219 | 218 in CSV + 1 extra; all with syntropic metadata in descriptions |
| Material Types | 10 | Compost, tools, raw materials |
| Log Categories | 7 | Irrigation, compost, weekly planning, etc. |
| Units | 5 | Measurement units (incl. plant unit: 2371b79e) |
| Season | 1 | Growing season |
| Crop Family | 1 | Botanical families |

## Plant Assets by Row

| Row | Sections | Plants | Species | Notes |
|-----|----------|--------|---------|-------|
| P2R1 | 4 | ~35 | ~20 | Spring 2025 renovation |
| P2R2 | 7 | ~100 | ~40 | Largest row variety |
| P2R3 | 7 | ~110 | ~45 | Most established row |
| P2R4 | 8 (+2 gap) | ~109 | ~31 | 3 empty gap sections |
| P2R5 | 7 (+2 gap) | ~50 | ~19 | Newest, P2R5.38-44 uninventoried |

## Land Hierarchy

- **Firefly Corner farm** (Farm)
  - P1 (Paddock 1) → P1R1-P1R5
  - P2 (Paddock 2) → P2R1-P2R5 (37 sections, 33 planted + 4 gap)
  - Front House Paddock
  - Other paddocks

## Import History

| Date | Action | Result |
|------|--------|--------|
| 2026-03-06 | Plant types v7 migration | 213 types: 16 renamed, 15 archived, 157 created |
| 2026-03-07 | P2R1-R3 import | 245 plants, 77 species, 18 sections |
| 2026-03-07 | P2R4-R5 import | 159 plants, 50 species, 14 sections |
| 2026-03-09 | Historical logs (H1) | 422 backdated logs (R1-R5) |
| 2026-03-09 | Gap sections added | 4 gap sections with green manure data |
| 2026-03-09 | Field observations imported | 131 approved, 4 rejected, 64 inventory updates |
| 2026-03-09 | 5 new plant types | Davidson Plum, Pear (Flordahome/Nashi), Pluot, Chilli (Devil's Brew) |

---

*This snapshot is updated by running `scripts/export_farmos.py`. Regenerate with: `python scripts/export_farmos.py --output exports/`*
