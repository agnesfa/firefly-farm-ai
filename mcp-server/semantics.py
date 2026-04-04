"""
Farm Semantic Layer (Layer 3) — Computable metric functions.

Loads definitions from knowledge/farm_semantics.yaml and computes
governed, canonical metrics on farmOS data. Pure functions — no I/O,
no client calls. Takes formatted data, returns scored interpretations.

Every function reads thresholds from the loaded semantics dict so that
changing the YAML automatically changes the computation.
"""

import os
from datetime import datetime, timezone, timedelta
from typing import Optional

import yaml

AEST = timezone(timedelta(hours=10))

# ── YAML loading ──────────────────────────────────────────────────

_SEMANTICS_CACHE: dict = {}
_ONTOLOGY_CACHE: dict = {}


def _find_yaml(filename: str) -> str:
    """Locate a YAML file in the knowledge/ directory relative to this module."""
    here = os.path.dirname(os.path.abspath(__file__))
    # Try parent/knowledge/ (when running from mcp-server/)
    candidate = os.path.join(here, "..", "knowledge", filename)
    if os.path.exists(candidate):
        return candidate
    # Try knowledge/ directly (when running from repo root)
    candidate = os.path.join(here, "knowledge", filename)
    if os.path.exists(candidate):
        return candidate
    raise FileNotFoundError(f"Cannot find {filename} in knowledge/ directory")


def load_semantics(path: Optional[str] = None) -> dict:
    """Load and cache farm_semantics.yaml."""
    global _SEMANTICS_CACHE
    if _SEMANTICS_CACHE:
        return _SEMANTICS_CACHE
    if path is None:
        path = _find_yaml("farm_semantics.yaml")
    with open(path, "r") as f:
        _SEMANTICS_CACHE = yaml.safe_load(f)
    return _SEMANTICS_CACHE


def load_ontology(path: Optional[str] = None) -> dict:
    """Load and cache farm_ontology.yaml."""
    global _ONTOLOGY_CACHE
    if _ONTOLOGY_CACHE:
        return _ONTOLOGY_CACHE
    if path is None:
        path = _find_yaml("farm_ontology.yaml")
    with open(path, "r") as f:
        _ONTOLOGY_CACHE = yaml.safe_load(f)
    return _ONTOLOGY_CACHE


def clear_caches():
    """Clear loaded YAML caches (for testing)."""
    global _SEMANTICS_CACHE, _ONTOLOGY_CACHE
    _SEMANTICS_CACHE = {}
    _ONTOLOGY_CACHE = {}


# ── Helpers ───────────────────────────────────────────────────────

def _get_threshold(semantics: dict, metric_path: str, level: str) -> float:
    """Navigate nested dict to get a threshold value.
    metric_path like 'section_health.strata_coverage'"""
    parts = metric_path.split(".")
    node = semantics
    for p in parts:
        node = node.get(p, {})
    return node.get("thresholds", {}).get(level, 0.0)


def _classify(value: float, thresholds: dict) -> str:
    """Classify a value against ordered thresholds (highest first).
    thresholds = {"good": 0.75, "fair": 0.50, "poor": 0.25}
    Returns the highest threshold that value meets or exceeds."""
    for label in ["good", "healthy", "active"]:
        if label in thresholds and value >= thresholds[label]:
            return label
    for label in ["fair", "concerning", "needs_attention"]:
        if label in thresholds and value >= thresholds[label]:
            return label
    # Return the worst status
    for label in ["poor", "at_risk", "neglected", "stalled"]:
        if label in thresholds:
            return label
    return "unknown"


def _classify_recency(days: int, thresholds: dict) -> str:
    """Classify recency — lower is better (inverse of normal thresholds)."""
    if days <= thresholds.get("active", 14):
        return "active"
    if days <= thresholds.get("needs_attention", 30):
        return "needs_attention"
    return "neglected"


# ── Core metric functions ─────────────────────────────────────────


def assess_strata_coverage(
    plants: list[dict],
    plant_types_db: dict,
    has_trees: bool,
    semantics: Optional[dict] = None,
) -> dict:
    """
    Assess strata coverage for a section.

    Args:
        plants: list of formatted plant dicts with 'species' and 'count' keys
        plant_types_db: dict mapping farmos_name → {"strata": "...", ...}
        has_trees: whether this is a tree section (expects 4 strata) or open (expects 2)
        semantics: loaded farm_semantics.yaml (loads default if None)

    Returns:
        {"emergent": n, "high": n, "medium": n, "low": n,
         "filled_strata": n, "expected_strata": n,
         "score": 0.0-1.0, "status": "good"|"fair"|"poor"}
    """
    if semantics is None:
        semantics = load_semantics()

    config = semantics.get("section_health", {}).get("strata_coverage", {})
    expected_config = config.get("expected_strata", {})
    expected = expected_config.get("tree_section", 4) if has_trees else expected_config.get("open_section", 2)
    thresholds = config.get("thresholds", {"good": 0.75, "fair": 0.50, "poor": 0.25})

    strata_counts = {"emergent": 0, "high": 0, "medium": 0, "low": 0}

    for plant in plants:
        count = plant.get("count") or 0
        if count <= 0:
            continue
        species = plant.get("species", "")
        pt = plant_types_db.get(species, {})
        strata = pt.get("strata", plant.get("strata", "")).lower() if pt else plant.get("strata", "").lower()
        if strata in strata_counts:
            strata_counts[strata] += count

    filled = sum(1 for v in strata_counts.values() if v > 0)
    score = filled / expected if expected > 0 else 0.0

    return {
        **strata_counts,
        "filled_strata": filled,
        "expected_strata": expected,
        "score": round(score, 2),
        "status": _classify(score, thresholds),
    }


def assess_activity_recency(
    logs: list[dict],
    semantics: Optional[dict] = None,
    now: Optional[datetime] = None,
) -> dict:
    """
    Assess how recently a section was visited/logged.

    Args:
        logs: list of formatted log dicts with 'timestamp' key (ISO or Unix)
        semantics: loaded farm_semantics.yaml
        now: current datetime (for testing)

    Returns:
        {"days_since_last": int, "last_log_date": str, "status": "active"|...}
    """
    if semantics is None:
        semantics = load_semantics()
    if now is None:
        now = datetime.now(tz=AEST)

    config = semantics.get("section_health", {}).get("activity_recency", {})
    thresholds = config.get("thresholds", {"active": 14, "needs_attention": 30, "neglected": 60})

    if not logs:
        return {
            "days_since_last": 9999,
            "last_log_date": None,
            "status": "neglected",
        }

    # Find most recent log timestamp
    latest = None
    for log in logs:
        ts = log.get("timestamp", "")
        if not ts:
            continue
        try:
            if isinstance(ts, (int, float)) or (isinstance(ts, str) and ts.isdigit()):
                dt = datetime.fromtimestamp(int(ts), tz=AEST)
            else:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if latest is None or dt > latest:
                latest = dt
        except (ValueError, OSError):
            continue

    if latest is None:
        return {"days_since_last": 9999, "last_log_date": None, "status": "neglected"}

    # Ensure both are timezone-aware for subtraction
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=AEST)
    if now.tzinfo is None:
        now = now.replace(tzinfo=AEST)

    days = (now - latest).days

    return {
        "days_since_last": days,
        "last_log_date": latest.strftime("%Y-%m-%d"),
        "status": _classify_recency(days, thresholds),
    }


def assess_succession_balance(
    plants: list[dict],
    plant_types_db: dict,
    semantics: Optional[dict] = None,
) -> dict:
    """
    Assess the pioneer/secondary/climax balance in a section.

    Args:
        plants: list of formatted plant dicts
        plant_types_db: dict mapping farmos_name → {"succession_stage": "...", ...}

    Returns:
        {"pioneer": n, "secondary": n, "climax": n, "unknown": n,
         "total": n, "percentages": {...}, "note": str}
    """
    counts = {"pioneer": 0, "secondary": 0, "climax": 0, "unknown": 0}

    for plant in plants:
        count = plant.get("count") or 0
        if count <= 0:
            continue
        species = plant.get("species", "")
        pt = plant_types_db.get(species, {})
        stage = pt.get("succession_stage", "").lower() if pt else ""
        if stage in ("pioneer", "secondary", "climax"):
            counts[stage] += count
        else:
            counts["unknown"] += count

    total = sum(counts.values())
    pcts = {}
    if total > 0:
        for k, v in counts.items():
            if k != "unknown":
                pcts[k] = round(100 * v / total)

    # Generate note
    note = ""
    if total == 0:
        note = "No plants with known succession stage"
    elif pcts.get("pioneer", 0) > 60:
        note = "Pioneer-heavy — expected for young sections"
    elif pcts.get("climax", 0) > 40:
        note = "Climax-dominant — mature succession"
    elif pcts.get("secondary", 0) > 40:
        note = "Secondary-dominant — transitioning well"
    else:
        note = "Balanced mix across succession stages"

    return {
        **counts,
        "total": total,
        "percentages": pcts,
        "note": note,
    }


def assess_section_health(
    plants: list[dict],
    logs: list[dict],
    plant_types_db: dict,
    has_trees: bool,
    semantics: Optional[dict] = None,
    now: Optional[datetime] = None,
) -> dict:
    """
    Comprehensive section health assessment using all semantic metrics.

    Returns a combined dict with strata, recency, succession, and overall status.
    """
    if semantics is None:
        semantics = load_semantics()

    strata = assess_strata_coverage(plants, plant_types_db, has_trees, semantics)
    recency = assess_activity_recency(logs, semantics, now)
    succession = assess_succession_balance(plants, plant_types_db, semantics)

    # Overall status: worst of strata and recency
    status_order = ["good", "healthy", "active", "fair", "concerning",
                    "needs_attention", "poor", "at_risk", "neglected"]

    def _status_rank(s):
        return status_order.index(s) if s in status_order else len(status_order)

    worst = max([strata["status"], recency["status"]], key=_status_rank)

    return {
        "strata_coverage": strata,
        "activity_recency": recency,
        "succession_balance": succession,
        "overall_status": worst,
    }


def find_transplant_ready(
    nursery_plants: list[dict],
    plant_types_db: dict,
    semantics: Optional[dict] = None,
    now: Optional[datetime] = None,
) -> list[dict]:
    """
    Find nursery plants ready for transplanting to the field.

    Args:
        nursery_plants: list of dicts with 'species', 'planted_date', 'name', 'count'
        plant_types_db: species metadata with transplant_days

    Returns:
        List of plants that are ready, with days_since_planted and transplant_days.
    """
    if now is None:
        now = datetime.now(tz=AEST)

    ready = []
    for plant in nursery_plants:
        species = plant.get("species", "")
        pt = plant_types_db.get(species, {})
        transplant_days = pt.get("transplant_days")
        if transplant_days is None:
            continue  # can't assess without transplant_days

        planted_str = plant.get("planted_date", "")
        if not planted_str:
            continue

        try:
            if isinstance(planted_str, str):
                planted_dt = datetime.fromisoformat(planted_str.replace("Z", "+00:00"))
            else:
                continue
        except ValueError:
            continue

        days_since = (now - planted_dt).days
        if days_since >= int(transplant_days):
            ready.append({
                "name": plant.get("name", ""),
                "species": species,
                "section": plant.get("section", ""),
                "count": plant.get("count", 0),
                "days_since_planted": days_since,
                "transplant_days": int(transplant_days),
                "days_overdue": days_since - int(transplant_days),
            })

    # Sort by most overdue first
    ready.sort(key=lambda x: x["days_overdue"], reverse=True)
    return ready


def detect_knowledge_gaps(
    species_in_field: list[str],
    kb_entries: list[dict],
) -> dict:
    """
    Detect species and topics that lack Knowledge Base coverage.

    Args:
        species_in_field: list of farmos_names with plants in the field
        kb_entries: list of KB entry dicts with 'related_plants', 'topics' fields

    Returns:
        {"uncovered_species": [...], "covered_species": [...],
         "coverage_ratio": float}
    """
    # Build set of species covered by KB
    covered = set()
    for entry in kb_entries:
        related = entry.get("related_plants", "") or ""
        for sp in related.split(","):
            sp = sp.strip()
            if sp:
                covered.add(sp)

    field_set = set(species_in_field)
    uncovered = sorted(field_set - covered)
    covered_field = sorted(field_set & covered)
    total = len(field_set)
    ratio = len(covered_field) / total if total > 0 else 0.0

    return {
        "uncovered_species": uncovered,
        "covered_species": covered_field,
        "coverage_ratio": round(ratio, 2),
        "total_field_species": total,
        "total_covered": len(covered_field),
    }


def detect_decision_gaps(
    pending_tasks: list[dict],
    recent_observations: list[dict],
) -> list[str]:
    """
    Detect gaps in the decision pipeline.

    Returns list of gap descriptions.
    """
    gaps = []

    # Pending tasks with no actor
    for task in pending_tasks:
        name = task.get("name", "")
        # Tasks in farmOS don't have an explicit assignee field yet
        # but we can flag tasks that have been pending too long
        status = task.get("status", "")
        if status == "pending":
            ts = task.get("timestamp", "")
            if ts:
                try:
                    if isinstance(ts, (int, float)) or (isinstance(ts, str) and ts.isdigit()):
                        created = datetime.fromtimestamp(int(ts), tz=AEST)
                    else:
                        created = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    days = (datetime.now(tz=AEST) - created).days
                    if days > 7:
                        gaps.append(f"Task '{name}' pending for {days} days — needs attention")
                except (ValueError, OSError):
                    pass

    # Observations with no follow-up (simplified — checks if any pending tasks exist)
    if recent_observations and not pending_tasks:
        gaps.append("Recent observations exist but no pending tasks — observations may not be acted on")

    return gaps


def detect_logging_gaps(
    team_memory_sessions: list[dict],
    farmos_logs: list[dict],
    section_filter: Optional[str] = None,
    species_filter: Optional[str] = None,
) -> list[dict]:
    """
    Cross-reference team memory farmos_changes against actual farmOS logs.
    Detects silent API failures where a session claimed to make changes
    but the changes don't exist in farmOS.

    Layer 4→5 validation: the context graph (what we said we did)
    checked against the knowledge graph (what actually exists).

    Args:
        team_memory_sessions: list of session dicts with 'farmos_changes',
            'user', 'timestamp', 'summary_id' fields
        farmos_logs: list of formatted farmOS log dicts with 'name', 'id', 'type' fields
        section_filter: optional section ID to limit analysis
        species_filter: optional species name to limit analysis

    Returns:
        List of gap dicts: {type, session_id, user, timestamp, claimed, evidence}
    """
    import json as _json

    gaps = []

    # Index farmOS logs by partial ID prefix (first 8 chars of UUID) for matching
    log_ids = set()
    log_names_lower = set()
    for log in farmos_logs:
        lid = log.get("id", "")
        if lid:
            log_ids.add(lid)
            log_ids.add(lid[:8])  # short prefix used in team memory
        name = log.get("name", "")
        if name:
            log_names_lower.add(name.lower())

    for session in team_memory_sessions:
        changes_raw = session.get("farmos_changes", "")
        if not changes_raw or changes_raw.strip() == "":
            continue

        # Parse farmos_changes — can be JSON array string or plain text
        claimed_changes = []
        try:
            parsed = _json.loads(changes_raw)
            if isinstance(parsed, list):
                claimed_changes = parsed
            elif isinstance(parsed, dict):
                claimed_changes = [parsed]
        except (_json.JSONDecodeError, TypeError):
            # Plain text description — can't cross-reference structurally
            continue

        user = session.get("user", "unknown")
        session_ts = session.get("timestamp", "")
        session_id = session.get("summary_id", "")

        for change in claimed_changes:
            if not isinstance(change, dict):
                continue

            change_type = change.get("type", "")
            change_id = change.get("id", "")
            details = change.get("details", change.get("description", ""))

            # Build details from structured fields if not explicitly present
            if not details:
                parts = []
                if change.get("species"):
                    parts.append(change["species"])
                if change.get("count"):
                    parts.append(f"x{change['count']}")
                if change.get("section"):
                    parts.append(f"— {change['section']}")
                if change.get("notes"):
                    parts.append(f"— {change['notes'][:80]}")
                if parts:
                    details = " ".join(parts)

            # Apply filters
            if section_filter and section_filter not in str(details):
                continue
            if species_filter and species_filter.lower() not in str(details).lower():
                continue

            # Check if the claimed change ID exists in farmOS
            found = False
            if change_id:
                if change_id in log_ids:
                    found = True

            # If no ID, try matching by details text against log names
            if not found and details:
                details_lower = details.lower()
                for log_name in log_names_lower:
                    # Check if key words from the claimed change appear in a log name
                    # e.g., "Lavender" and "P2R4.6-14" in a log name
                    if all(word.lower() in log_name for word in details_lower.split()[:3] if len(word) > 2):
                        found = True
                        break

            if not found:
                gaps.append({
                    "type": "claimed_not_found",
                    "session_id": session_id,
                    "user": user,
                    "session_timestamp": session_ts,
                    "claimed_change": {
                        "type": change_type,
                        "id": change_id or None,
                        "details": details,
                    },
                    "evidence": "No matching farmOS log found — possible silent API failure",
                })

    return gaps
