"""
Shared utilities for the farmOS MCP server.

Extracts and centralizes reusable functions from existing scripts:
- Date parsing (from import_fieldsheets.py)
- Plant asset name formatting (from import_fieldsheets.py)
- farmOS response formatting (for clean tool output)
"""

from datetime import datetime, timezone, timedelta


AEST = timezone(timedelta(hours=10))
PLANT_UNIT_UUID = "2371b79e-a87b-4152-b6e4-ea6a9ed37fd0"


# ── Date utilities ──────────────────────────────────────────────

def _guard_future_ts(ts: int, raw: str) -> int:
    # ADR 0008 I12: refuse timestamps more than 24h past now. 24h grace
    # accommodates AEST↔UTC edge cases without admitting year-typos.
    now_ts = int(datetime.now(tz=AEST).timestamp())
    if ts > now_ts + 86400:
        human = datetime.fromtimestamp(ts, tz=AEST).strftime('%Y-%m-%d')
        raise ValueError(
            f"Refusing future-dated timestamp: '{raw}' resolved to {human}, "
            f"more than 24h after now. Possible year-typo (e.g. '2026-12-18' "
            f"when you meant '2025-12-18'). See ADR 0008 I12."
        )
    return ts


def parse_date(date_str: str) -> int:
    """Parse date string to Unix timestamp (farmOS format).

    Handles multiple formats from farm data:
    - ISO: "2025-10-09"
    - Text: "2025-MARCH-20 to 24TH"
    - Fallback: returns now

    Rejects future-dated inputs more than 24h past now (ADR 0008 I12).

    Returns:
        Unix timestamp as integer

    Raises:
        ValueError: input resolves to a timestamp more than 24h in the future.
    """
    if not date_str:
        return int(datetime.now(tz=AEST).timestamp())

    # ISO format: 2025-10-09
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=AEST)
        return _guard_future_ts(int(dt.timestamp()), date_str)
    except ValueError as e:
        if "Refusing future-dated" in str(e):
            raise

    # ISO with time: 2026-03-09T03:15:00.000Z
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return _guard_future_ts(int(dt.timestamp()), date_str)
    except ValueError as e:
        if "Refusing future-dated" in str(e):
            raise

    # "2025-MARCH-20 to 24TH" format
    try:
        parts = date_str.upper().replace(",", "").split("-")
        if len(parts) >= 2:
            year = int(parts[0].strip())
            month_names = {
                "JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "APRIL": 4,
                "MAY": 5, "JUNE": 6, "JULY": 7, "AUGUST": 8,
                "SEPTEMBER": 9, "OCTOBER": 10, "NOVEMBER": 11, "DECEMBER": 12,
            }
            month_str = parts[1].strip()
            if month_str in month_names:
                day = 1
                if len(parts) >= 3:
                    day_str = parts[2].strip().split()[0]
                    try:
                        day = int("".join(c for c in day_str if c.isdigit()))
                    except ValueError:
                        day = 1
                dt = datetime(year, month_names[month_str], max(1, day), tzinfo=AEST)
                return _guard_future_ts(int(dt.timestamp()), date_str)
    except ValueError as e:
        if "Refusing future-dated" in str(e):
            raise
    except IndexError:
        pass

    # Fallback: now (unparseable input is safe, but a future-dated
    # successful parse is not — the guard above handles that case).
    return int(datetime.now(tz=AEST).timestamp())


def format_planted_label(date_str: str) -> str:
    """Format first_planted date for plant asset name.

    Examples:
        "2025-04-25" → "25 APR 2025"
        "April 2025" → "APR 2025"
        "" → "SPRING 2025"
    """
    if not date_str:
        return "SPRING 2025"

    # ISO format: 2025-04-25
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%-d %b %Y").upper()
    except ValueError:
        pass

    # Text format: "April 2025"
    try:
        dt = datetime.strptime(date_str, "%B %Y")
        return dt.strftime("%b %Y").upper()
    except ValueError:
        pass

    return date_str.upper()


def build_asset_name(planted_date: str, farmos_name: str, section_id: str) -> str:
    """Build a plant asset name following farmOS conventions.

    Format: "{planted_date_label} - {farmos_name} - {section_id}"
    Example: "25 APR 2025 - Pigeon Pea - P2R2.0-3"
    """
    label = format_planted_label(planted_date)
    return f"{label} - {farmos_name} - {section_id}"


def format_timestamp(unix_ts) -> str:
    """Format a Unix timestamp or ISO string to human-readable date."""
    if not unix_ts:
        return "unknown"

    # Try as Unix timestamp (integer or numeric string)
    try:
        if isinstance(unix_ts, str):
            ts = int(unix_ts)
        else:
            ts = int(unix_ts)
        dt = datetime.fromtimestamp(ts, tz=AEST)
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError, OSError):
        pass

    # Try as ISO 8601 string (farmOS raw HTTP returns these)
    if isinstance(unix_ts, str):
        try:
            dt = datetime.fromisoformat(unix_ts.replace("Z", "+00:00"))
            dt_local = dt.astimezone(AEST)
            return dt_local.strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            pass

    return str(unix_ts)


# ── farmOS response formatting ─────────────────────────────────

def format_plant_asset(asset: dict) -> dict:
    """Format a raw farmOS plant asset for clean tool output."""
    attrs = asset.get("attributes", {})
    rels = asset.get("relationships", {})

    # Extract plant type name from relationship
    plant_type_data = rels.get("plant_type", {}).get("data", [])
    plant_type_ids = [pt.get("id", "") for pt in plant_type_data] if plant_type_data else []

    # Parse the asset name to extract components
    # Format: "{date} - {species} - {section_id}"
    # Species can contain " - " (e.g., "Basil - Sweet (Classic)")
    # Section is always LAST, date is always FIRST
    name = attrs.get("name", "")
    parts = name.split(" - ")
    if len(parts) >= 3:
        planted_date = parts[0]
        section = parts[-1]
        species = " - ".join(parts[1:-1])
    elif len(parts) == 2:
        planted_date = parts[0]
        species = parts[1]
        section = ""
    else:
        planted_date = ""
        species = name
        section = ""

    # Extract notes
    notes_raw = attrs.get("notes", {})
    notes = ""
    if isinstance(notes_raw, dict):
        notes = notes_raw.get("value", "")
    elif isinstance(notes_raw, str):
        notes = notes_raw

    # Extract computed inventory count from farmOS
    # farmOS returns: [{"measure": "count", "value": "4", "units": {"...": "plant"}}]
    inventory_data = attrs.get("inventory", [])
    inventory_count = None
    if inventory_data:
        for inv in inventory_data:
            if inv.get("measure") == "count":
                try:
                    inventory_count = int(float(inv.get("value", 0)))
                except (ValueError, TypeError):
                    inventory_count = None
                break
        # If no "count" measure found but there is inventory data, take the first
        if inventory_count is None and inventory_data:
            try:
                inventory_count = int(float(inventory_data[0].get("value", 0)))
            except (ValueError, TypeError):
                pass

    result = {
        "id": asset.get("id", ""),
        "name": name,
        "species": species,
        "section": section,
        "planted_date": planted_date,
        "status": attrs.get("status", ""),
        "notes": notes,
        "plant_type_ids": plant_type_ids,
    }
    if inventory_count is not None:
        result["inventory_count"] = inventory_count
    return result


def format_log(log: dict) -> dict:
    """Format a raw farmOS log for clean tool output."""
    attrs = log.get("attributes", {})
    rels = log.get("relationships", {})

    # Extract notes
    notes_raw = attrs.get("notes", {})
    notes = ""
    if isinstance(notes_raw, dict):
        notes = notes_raw.get("value", "")
    elif isinstance(notes_raw, str):
        notes = notes_raw

    # Extract log type from the type field
    log_type = log.get("type", "").replace("log--", "")

    # Extract associated asset names
    asset_data = rels.get("asset", {}).get("data", [])
    asset_ids = [a.get("id", "") for a in asset_data] if asset_data else []

    # Extract location
    location_data = rels.get("location", {}).get("data", [])
    location_ids = [l.get("id", "") for l in location_data] if location_data else []

    # Extract quantity data (populated when logs are fetched with ?include=quantity)
    # Merged into log by farmos_client as "_quantities" list
    quantities = []
    for q in log.get("_quantities", []):
        q_attrs = q.get("attributes", {})
        value_raw = q_attrs.get("value", {})
        # value can be {"decimal": "3"} or just a number
        if isinstance(value_raw, dict):
            val = value_raw.get("decimal", value_raw.get("numerator"))
        else:
            val = value_raw
        try:
            val = int(float(val)) if val is not None else None
        except (ValueError, TypeError):
            val = None
        quantities.append({
            "value": val,
            "measure": q_attrs.get("measure", ""),
            "inventory_adjustment": q_attrs.get("inventory_adjustment", ""),
            "label": q_attrs.get("label", ""),
        })

    result = {
        "id": log.get("id", ""),
        "name": attrs.get("name", ""),
        "type": log_type,
        "timestamp": format_timestamp(attrs.get("timestamp")),
        "status": attrs.get("status", ""),
        "is_movement": attrs.get("is_movement", False),
        "notes": notes,
        "asset_ids": asset_ids,
        "location_ids": location_ids,
    }
    if quantities:
        result["quantity"] = quantities
    return result


def format_plant_type(term: dict) -> dict:
    """Format a raw farmOS plant_type taxonomy term for clean output."""
    attrs = term.get("attributes", {})

    # Parse description for syntropic metadata
    desc_raw = attrs.get("description", {})
    description = ""
    if isinstance(desc_raw, dict):
        description = desc_raw.get("value", "")
    elif isinstance(desc_raw, str):
        description = desc_raw

    # Extract syntropic metadata from description
    # Format in farmOS: "**Key:** Value" (Markdown bold markers)
    metadata = {}
    if "Syntropic Agriculture Data" in description:
        for line in description.split("\n"):
            # Strip Markdown bold markers: "**Key:** Value" → "Key: Value"
            clean = line.strip().replace("**", "")
            if clean.startswith("Botanical Name:"):
                metadata["botanical_name"] = clean.split(":", 1)[1].strip()
            elif clean.startswith("Strata:"):
                metadata["strata"] = clean.split(":", 1)[1].strip()
            elif clean.startswith("Succession Stage:"):
                metadata["succession_stage"] = clean.split(":", 1)[1].strip()
            elif clean.startswith("Functions:"):
                metadata["functions"] = clean.split(":", 1)[1].strip()
            elif clean.startswith("Family:"):
                metadata["family"] = clean.split(":", 1)[1].strip()
            elif clean.startswith("Lifespan:"):
                metadata["lifespan"] = clean.split(":", 1)[1].strip()
            elif clean.startswith("Life Cycle:"):
                metadata["lifecycle"] = clean.split(":", 1)[1].strip()
            elif clean.startswith("Source:"):
                metadata["source"] = clean.split(":", 1)[1].strip()

    return {
        "id": term.get("id", ""),
        "name": attrs.get("name", ""),
        "maturity_days": attrs.get("maturity_days"),
        "transplant_days": attrs.get("transplant_days"),
        **metadata,
    }


def format_section_from_assets(section_asset: dict, plant_assets: list) -> dict:
    """Build a section summary from a land asset and its associated plant assets."""
    attrs = section_asset.get("attributes", {})
    section_id = attrs.get("name", "")

    # Group plants by strata
    plants = []
    for plant in plant_assets:
        formatted = format_plant_asset(plant)
        plants.append({
            "species": formatted["species"],
            "planted_date": formatted["planted_date"],
            "status": formatted["status"],
            "notes": formatted["notes"],
        })

    return {
        "id": section_id,
        "uuid": section_asset.get("id", ""),
        "status": attrs.get("status", ""),
        "plant_count": len(plants),
        "plants": plants,
    }


# ── Plant type description helpers ─────────────────────────────


def build_plant_type_description(fields: dict) -> str:
    """Build farmOS plant type description with syntropic metadata block.

    Replicates the format from scripts/import_plants.py build_description().
    The metadata is embedded in the description as Markdown-formatted key-value
    pairs, since farmOS doesn't have native syntropic fields yet (Phase 4).

    Args:
        fields: Dict with keys: description, botanical_name, lifecycle_years,
                strata, succession_stage, plant_functions, crop_family,
                lifespan_years, source.
    """
    parts = []

    if fields.get("description"):
        parts.append(fields["description"])

    metadata = []
    if fields.get("botanical_name"):
        metadata.append(f"**Botanical Name:** {fields['botanical_name']}")
    if fields.get("lifecycle_years"):
        metadata.append(f"**Life Cycle:** {fields['lifecycle_years']} years")
    if fields.get("strata"):
        metadata.append(f"**Strata:** {fields['strata'].title()}")
    if fields.get("succession_stage"):
        metadata.append(f"**Succession Stage:** {fields['succession_stage'].title()}")
    if fields.get("plant_functions"):
        functions = fields["plant_functions"].replace("_", " ").replace(",", ", ")
        metadata.append(f"**Functions:** {functions.title()}")
    if fields.get("crop_family"):
        metadata.append(f"**Family:** {fields['crop_family']}")
    if fields.get("lifespan_years"):
        metadata.append(f"**Lifespan:** {fields['lifespan_years']} years")
    if fields.get("source"):
        metadata.append(f"**Source:** {fields['source']}")
    if fields.get("photo_source"):
        metadata.append(f"**Photo Source:** {fields['photo_source']}")

    if metadata:
        parts.append("\n\n---\n**Syntropic Agriculture Data:**\n" + "\n".join(metadata))

    return "\n".join(parts)


def parse_plant_type_metadata(description_text: str) -> dict:
    """Extract syntropic metadata from a plant type description.

    Parses the Markdown-formatted metadata block embedded in farmOS
    plant_type descriptions.

    Returns dict with keys: botanical_name, strata, succession_stage,
    plant_functions, crop_family, lifespan_years, lifecycle_years, source.
    """
    metadata = {}
    if not description_text or "Syntropic Agriculture Data" not in description_text:
        return metadata

    for line in description_text.split("\n"):
        clean = line.strip().replace("**", "")
        if clean.startswith("Botanical Name:"):
            metadata["botanical_name"] = clean.split(":", 1)[1].strip()
        elif clean.startswith("Strata:"):
            metadata["strata"] = clean.split(":", 1)[1].strip().lower()
        elif clean.startswith("Succession Stage:"):
            metadata["succession_stage"] = clean.split(":", 1)[1].strip().lower()
        elif clean.startswith("Functions:"):
            # Restore underscore format: "Nitrogen Fixer" → "nitrogen_fixer"
            raw = clean.split(":", 1)[1].strip()
            metadata["plant_functions"] = raw.lower().replace(" ", "_").replace(",_", ",")
        elif clean.startswith("Family:"):
            metadata["crop_family"] = clean.split(":", 1)[1].strip()
        elif clean.startswith("Lifespan:"):
            val = clean.split(":", 1)[1].strip()
            metadata["lifespan_years"] = val.replace(" years", "")
        elif clean.startswith("Life Cycle:"):
            val = clean.split(":", 1)[1].strip()
            metadata["lifecycle_years"] = val.replace(" years", "")
        elif clean.startswith("Photo Source:"):
            metadata["photo_source"] = clean.split(":", 1)[1].strip()
        elif clean.startswith("Source:"):
            metadata["source"] = clean.split(":", 1)[1].strip()

    return metadata


# ── Topic-to-farmOS mapping ───────────────────────────────────────

TOPIC_FARMOS_MAP = {
    "nursery":        {"section_prefix": "NURS.", "asset_types": ["plant", "structure"]},
    "compost":        {"section_prefix": "COMP.", "asset_types": ["compost"]},
    "paddock":        {"section_prefix": "P",     "asset_types": ["plant", "land"]},
    "seeds":          {"section_prefix": "NURS.FR", "asset_types": ["seed"]},
    "irrigation":     {"section_prefix": None,    "asset_types": ["water", "equipment"]},
    "equipment":      {"section_prefix": None,    "asset_types": ["equipment"]},
    "infrastructure": {"section_prefix": None,    "asset_types": ["water", "land"]},
    "camp":           {"section_prefix": None,    "asset_types": ["structure"]},
    "harvest":        {"section_prefix": None,    "asset_types": ["plant"]},
    "cooking":        {"section_prefix": None,    "asset_types": []},
    "syntropic":      {"section_prefix": "P",     "asset_types": ["plant", "land"]},
}
