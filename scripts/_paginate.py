"""Shared pagination helper for farmOS JSON:API queries.

Use `paginate_offset` in any script that fetches a farmOS collection
(assets, logs, taxonomy terms, files, users). It uses page[offset] +
stable sort — the only reliable pattern per architecture decision #11.

Do NOT use `links.next` anywhere in this repo. farmOS silently stops
returning next links after ~250 items, which causes alphabetically- or
chronologically-late entries to disappear from export / audit / cleanup
runs. See: `claude-docs/pagination-fix-plan.md`.

Usage
-----

    from _paginate import paginate_offset

    # Simple: all active plant_types
    for term, _ in paginate_offset(
        fc.session, fc.hostname,
        "taxonomy_term/plant_type",
        filters={"status": "1"},
        sort="drupal_internal__tid",
    ):
        ...

    # With included resources (e.g. image files):
    for term, included in paginate_offset(
        fc.session, fc.hostname,
        "taxonomy_term/plant_type",
        filters={"status": "1"},
        sort="drupal_internal__tid",
        include="image",
    ):
        file_refs = (term.get("relationships", {}).get("image") or {}).get("data") or []
        for ref in file_refs:
            f = included.get(("file--file", ref["id"]))
            if f:
                ...
"""

from __future__ import annotations

import urllib.parse
from typing import Iterator, Optional


def paginate_offset(
    session,
    hostname: str,
    api_path: str,
    filters: Optional[dict] = None,
    sort: Optional[str] = None,
    include: Optional[str] = None,
    limit: int = 50,
    max_pages: int = 100,
    timeout: int = 30,
) -> Iterator[tuple[dict, dict]]:
    """Paginate through a farmOS JSON:API collection using page[offset].

    Yields (item, included_index) tuples where included_index is a dict
    mapping (type, id) → included resource, scoped to the page the item
    belongs to. Callers that want a global included map across pages can
    accumulate it themselves.

    Args:
        session: an authenticated requests.Session (usually `fc.session`)
        hostname: farmOS instance URL without trailing slash
        api_path: e.g. "asset/plant", "taxonomy_term/plant_type"
        filters: e.g. {"status": "1"} → `?filter[status]=1`
        sort: e.g. "drupal_internal__tid" for stable sort. If omitted,
              defaults to "drupal_internal__id" as a stable fallback.
              MANDATORY for reliability — farmOS default sort is unstable.
        include: e.g. "image" or "image,plant_type"
        limit: page size (farmOS caps at 50)
        max_pages: safety cap to prevent runaway loops
        timeout: per-request timeout seconds

    Yields:
        (item, included_index) per item in the collection
    """
    params_list = [f"page[limit]={limit}"]
    if filters:
        for k, v in filters.items():
            params_list.append(f"filter[{k}]={urllib.parse.quote(str(v))}")
    params_list.append(f"sort={sort or 'drupal_internal__id'}")
    if include:
        params_list.append(f"include={urllib.parse.quote(include)}")
    base_params = "&".join(params_list)

    offset = 0
    guard = 0
    while guard < max_pages:
        guard += 1
        url = f"{hostname.rstrip('/')}/api/{api_path}?{base_params}&page[offset]={offset}"
        resp = session.get(url, timeout=timeout)
        if not resp.ok:
            break
        data = resp.json()
        items = data.get("data") or []
        if not items:
            break

        # Build per-page included index
        included_index: dict[tuple[str, str], dict] = {}
        for inc in data.get("included") or []:
            key = (inc.get("type", ""), inc.get("id", ""))
            if all(key):
                included_index[key] = inc

        for item in items:
            yield item, included_index

        # Always advance offset and continue until an empty page. farmOS
        # may return fewer than `limit` items on a page without being the
        # last page (e.g. permission filtering, internal limits). The only
        # reliable "end of collection" signal is items == [].
        offset += limit


def paginate_all(
    session,
    hostname: str,
    api_path: str,
    **kwargs,
) -> list[dict]:
    """Convenience wrapper — collect all items as a flat list.

    Use when you don't need included resources.
    """
    return [item for item, _ in paginate_offset(session, hostname, api_path, **kwargs)]
