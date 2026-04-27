/**
 * farmOS v3 ↔ v4 compatibility helpers.
 *
 * v4 (#986) removes the asset `status` base field and replaces it with an
 * `archived` boolean. To minimise the diff between dual-path support and
 * post-cutover cleanup, ALL version-conditional logic lives in this file.
 * Everything else (FarmOSClient, tools, formatters) calls these helpers.
 *
 * The version is selected at runtime via `FARMOS_API_VERSION` env var
 * (default `"3"`). FarmOSClient reads it once at construction and exposes
 * it as `client.apiVersion`. See ADR 0009.
 *
 * Three helpers, three concerns:
 *
 *   - assetStatusFilter / assetStatusFilterParam — outgoing READ filters
 *     (we have to know the version because v3 and v4 use different filter
 *     keys: `filter[status]=` vs `filter[archived]=`).
 *
 *   - assetArchivePayload — outgoing ARCHIVE PATCH payload
 *     (v3: `{ status: 'archived' }`, v4: `{ archived: true }`).
 *
 *   - readAssetStatus — incoming response READ. Shape-detected, no version
 *     parameter needed: if the response has `archived` → v4; otherwise v3.
 *     This means formatters and display-readers are version-agnostic by
 *     construction.
 *
 * Asset CREATE payloads drop the redundant `status: 'active'` line entirely
 * (it's the default in v3 and the field doesn't exist in v4) — single-version
 * code, no helper needed.
 */

export type ApiVersion = '3' | '4';

export const ACTIVE = 'active' as const;
export const ARCHIVED = 'archived' as const;
export type AssetStatus = typeof ACTIVE | typeof ARCHIVED;

const VALID_VERSIONS: readonly ApiVersion[] = ['3', '4'];

/**
 * Read FARMOS_API_VERSION from env with `'3'` as the safe default.
 * Throws on an unknown value (typo, future version) so the misconfiguration
 * surfaces at startup rather than as a confusing 400 mid-call.
 */
export function parseApiVersion(raw: string | undefined): ApiVersion {
  const v = (raw ?? '3') as ApiVersion;
  if (!VALID_VERSIONS.includes(v)) {
    throw new Error(
      `FARMOS_API_VERSION must be one of ${VALID_VERSIONS.join('/')}, got ${JSON.stringify(raw)}.`,
    );
  }
  return v;
}

/**
 * Filter dict for `fetchAllPaginated` / `fetchFiltered`. The existing URL
 * builders iterate the dict and emit `&filter[<key>]=<value>` per entry, so
 * we just have to return the right key/value for the active version.
 */
export function assetStatusFilter(
  version: ApiVersion,
  status: AssetStatus,
): Record<string, string> {
  if (version === '4') {
    return { archived: status === ARCHIVED ? '1' : '0' };
  }
  return { status };
}

/**
 * URL-fragment variant for sites that build the URL by hand
 * (e.g. fetchPlantsContains, fetchSeedsContains).
 */
export function assetStatusFilterParam(version: ApiVersion, status: AssetStatus): string {
  const filter = assetStatusFilter(version, status);
  const entries = Object.entries(filter);
  // Helper always returns exactly one key/value.
  const [key, value] = entries[0]!;
  return `filter[${key}]=${value}`;
}

/**
 * Attribute payload for the archive PATCH on `asset/plant/{id}`.
 * v3 sets the legacy status field; v4 toggles the boolean.
 */
export function assetArchivePayload(version: ApiVersion): Record<string, unknown> {
  if (version === '4') {
    return { archived: true };
  }
  return { status: 'archived' };
}

/**
 * Normalise an asset response shape into `'active' | 'archived'` regardless
 * of which farmOS version produced it. Shape-detected — no version parameter
 * needed. Use this in formatters and any code that displays asset status.
 *
 * v4 always emits `archived` (boolean). v3 emits `status` (string).
 * Mixed responses can't actually happen in our setup (we talk to one farmOS
 * instance per tenant) but the precedence rule keeps the function safe even
 * if the data crosses streams.
 */
export function readAssetStatus(asset: { attributes?: any } | null | undefined): AssetStatus {
  const attrs = asset?.attributes;
  if (attrs && 'archived' in attrs) {
    return attrs.archived ? ARCHIVED : ACTIVE;
  }
  return attrs?.status === ARCHIVED ? ARCHIVED : ACTIVE;
}
