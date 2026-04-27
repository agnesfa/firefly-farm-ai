"""
farmOS v3 ↔ v4 compatibility helpers (Python mirror of TS api-version.ts).

v4 (#986) removes the asset `status` base field and replaces it with an
`archived` boolean. To minimise the diff between dual-path support and
post-cutover cleanup, ALL version-conditional logic lives in this module.

The version is selected at runtime via `FARMOS_API_VERSION` env var
(default `"3"`). FarmOSClient reads it once at construction and exposes
it as `client.api_version`. See ADR 0009.

Three helpers, three concerns:

  - asset_status_filter / asset_status_filter_param — outgoing READ filters
    (we have to know the version because v3 and v4 use different filter
    keys: `filter[status]=` vs `filter[archived]=`).

  - asset_archive_payload — outgoing ARCHIVE PATCH payload
    (v3: `{"status": "archived"}`, v4: `{"archived": True}`).

  - read_asset_status — incoming response READ. Shape-detected, no version
    parameter needed: if the response has `archived` → v4; otherwise v3.
    This means formatters and display-readers are version-agnostic by
    construction.

Asset CREATE payloads drop the redundant `"status": "active"` line entirely
(it's the default in v3 and the field doesn't exist in v4) — single-version
code, no helper needed.
"""

from typing import Literal, Optional

ApiVersion = Literal["3", "4"]
AssetStatus = Literal["active", "archived"]

ACTIVE: AssetStatus = "active"
ARCHIVED: AssetStatus = "archived"

_VALID_VERSIONS: tuple[str, ...] = ("3", "4")


def parse_api_version(raw: Optional[str]) -> ApiVersion:
    """
    Read FARMOS_API_VERSION from env with `'3'` as the safe default.
    Raises on an unknown value (typo, future version) so the misconfiguration
    surfaces at startup rather than as a confusing 400 mid-call.
    """
    v = raw if raw is not None else "3"
    if v not in _VALID_VERSIONS:
        raise ValueError(
            f"FARMOS_API_VERSION must be one of {'/'.join(_VALID_VERSIONS)}, "
            f"got {raw!r}."
        )
    return v  # type: ignore[return-value]


def asset_status_filter(version: ApiVersion, status: AssetStatus) -> dict[str, str]:
    """
    Filter dict for `fetch_all_paginated` / `fetch_filtered`. The existing URL
    builders iterate the dict and emit `&filter[<key>]=<value>` per entry, so
    we just have to return the right key/value for the active version.
    """
    if version == "4":
        return {"archived": "1" if status == ARCHIVED else "0"}
    return {"status": status}


def asset_status_filter_param(version: ApiVersion, status: AssetStatus) -> str:
    """
    URL-fragment variant for sites that build the URL by hand
    (e.g. _fetch_plants_contains, _fetch_seeds_contains).
    """
    f = asset_status_filter(version, status)
    key, value = next(iter(f.items()))
    return f"filter[{key}]={value}"


def asset_archive_payload(version: ApiVersion) -> dict[str, object]:
    """
    Attribute payload for the archive PATCH on `asset/plant/{id}`.
    v3 sets the legacy status field; v4 toggles the boolean.
    """
    if version == "4":
        return {"archived": True}
    return {"status": "archived"}


def read_asset_status(asset: Optional[dict]) -> AssetStatus:
    """
    Normalise an asset response shape into 'active' | 'archived' regardless
    of which farmOS version produced it. Shape-detected — no version parameter
    needed. Use this in formatters and any code that displays asset status.

    v4 always emits `archived` (boolean). v3 emits `status` (string).
    Mixed responses can't actually happen in our setup (we talk to one farmOS
    instance per tenant) but the precedence rule keeps the function safe even
    if the data crosses streams.
    """
    if not asset:
        return ACTIVE
    attrs = asset.get("attributes") or {}
    if "archived" in attrs:
        return ARCHIVED if attrs.get("archived") else ACTIVE
    return ARCHIVED if attrs.get("status") == ARCHIVED else ACTIVE
