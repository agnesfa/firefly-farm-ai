/**
 * farmOS JSON:API HTTP client.
 *
 * Stateless w.r.t. auth: receives an OAuth2 access token from the framework
 * (via FarmOSPlatformAuthHandler at session creation) and an optional refresh
 * callback (via createAuthRefreshCallback) for in-flight 401 recovery.
 *
 * Token lifecycle is owned by @fireflyagents/mcp-server-core; this client
 * never issues OAuth grants directly. See ADR 0010.
 *
 * Implements pagination with dedup, CONTAINS filters, cached lookups,
 * and all CRUD operations needed by the MCP tools.
 */

import { logger as baseLogger } from '@fireflyagents/mcp-shared-utils';

const logger = baseLogger.child({ context: 'farm-plugin:farmos-client' });

const PLANT_UNIT_UUID = '2371b79e-a87b-4152-b6e4-ea6a9ed37fd0';
const GRAMS_UNIT_UUID = 'e7bad672-9c33-4138-9fc3-1b0548a33aca';
const NURS_FRDG_UUID = '429fcdd3-8be6-436a-b439-49186f56b3c7';

const FETCH_TIMEOUT_MS = 15_000;

/** Shape returned by the framework's createAuthRefreshCallback on success. */
interface RefreshAuthResult {
  headers?: Record<string, string>;
}

interface FarmOSConfig {
  farmUrl: string;
  /** OAuth2 access token from extra.authInfo.token (set by FarmOSPlatformAuthHandler). */
  accessToken: string;
  /**
   * Framework refresh callback. On 401/403 the client invokes this once; if
   * it returns headers, the request is retried with them.
   * Production: pass `createAuthRefreshCallback(extra)` from
   * `@fireflyagents/mcp-server-core`.
   * Tests: pass a mock or omit (omitting disables retry; 401 throws immediately).
   */
  refreshAuth?: () => Promise<RefreshAuthResult | null | undefined>;
}

export class FarmOSClient {
  private baseUrl: string;
  private config: FarmOSConfig;
  private plantTypeCache = new Map<string, string>(); // farmos_name → UUID
  private sectionCache = new Map<string, string>(); // section_id → UUID
  private plantTypeFullCache: any[] | null = null;
  private plantTypeFullCacheTime = 0;
  private readonly PLANT_TYPE_CACHE_TTL = 300; // 5 minutes

  // Refresh stats for observability (in-flight reactive refresh via framework callback).
  private stats = {
    refreshCount: 0,
    refreshSuccessCount: 0,
    refreshFailCount: 0,
    lastRefreshAt: null as string | null,
  };

  constructor(config: FarmOSConfig) {
    if (!config.accessToken) {
      throw new Error(
        'FarmOSClient: accessToken is required (provided by framework PlatformAuthHandler via extra.authInfo.token).',
      );
    }
    this.config = config;
    this.baseUrl = config.farmUrl.replace(/\/+$/, '');
  }

  /**
   * Whether this client has an access token. Always true for a constructed
   * client (the constructor throws otherwise). Kept for back-compat with
   * existing callers; consider removing once those migrate.
   */
  get isConnected(): boolean {
    return !!this.config.accessToken;
  }

  getStats() {
    return { ...this.stats };
  }

  private get headers(): Record<string, string> {
    return {
      Authorization: `Bearer ${this.config.accessToken}`,
      'Content-Type': 'application/vnd.api+json',
      Accept: 'application/vnd.api+json',
    };
  }

  // ── Low-level HTTP ──────────────────────────────────────────

  /**
   * HTTP wrapper with one-shot reactive refresh on 401/403.
   *
   * On expired-auth response: invokes the framework's refresh callback (set
   * by getFarmOSClient → createAuthRefreshCallback). If the callback returns
   * new headers, retries once. If the callback returns null/throws or the
   * retry also fails, throws a clear "session expired" error.
   *
   * If `config.refreshAuth` is not provided (e.g. unit tests without a
   * framework session), a 401/403 propagates immediately as a thrown error.
   */
  private async _fetchWithRetry(url: string, init?: RequestInit): Promise<Response> {
    const mergedInit = {
      ...init,
      headers: { ...this.headers, ...init?.headers },
      signal: init?.signal ?? AbortSignal.timeout(FETCH_TIMEOUT_MS),
    };
    const resp = await fetch(url, mergedInit);

    if (resp.status !== 401 && resp.status !== 403) {
      return resp;
    }

    const shortUrl = url.replace(this.baseUrl, '');

    if (!this.config.refreshAuth) {
      logger.warn('Auth expired and no refresh callback configured', { url: shortUrl, status: resp.status });
      throw new Error(
        `farmOS authentication expired (HTTP ${resp.status}) — restart your Claude session to re-authenticate.`,
      );
    }

    this.stats.refreshCount++;
    this.stats.lastRefreshAt = new Date().toISOString();
    logger.warn('Auth expired, requesting framework refresh', { url: shortUrl, status: resp.status });

    let refreshResult: RefreshAuthResult | null | undefined;
    try {
      refreshResult = await this.config.refreshAuth();
    } catch (e) {
      this.stats.refreshFailCount++;
      const msg = e instanceof Error ? e.message : String(e);
      logger.error('Auth refresh callback threw', { url: shortUrl, error: msg });
      throw new Error(`farmOS auth refresh failed: ${msg}`);
    }

    if (!refreshResult?.headers) {
      this.stats.refreshFailCount++;
      logger.error('Auth refresh callback returned no headers', { url: shortUrl });
      throw new Error('farmOS authentication expired — restart your Claude session to re-authenticate.');
    }

    // Pull the new token out of the refresh result so subsequent requests on
    // this client also use it. The framework callback already updated
    // extra.authInfo.token, but our own config.accessToken needs syncing too.
    const auth = refreshResult.headers.Authorization;
    if (typeof auth === 'string' && auth.startsWith('Bearer ')) {
      this.config.accessToken = auth.slice('Bearer '.length);
    }

    const retry = await fetch(url, {
      ...init,
      headers: { ...this.headers, ...init?.headers },
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
    });

    if (retry.status === 401 || retry.status === 403) {
      this.stats.refreshFailCount++;
      logger.error('Auth retry failed after refresh', { url: shortUrl, status: retry.status });
      throw new Error(`farmOS authentication failed after refresh (HTTP ${retry.status}).`);
    }

    this.stats.refreshSuccessCount++;
    logger.info('Auth refresh + retry succeeded', { url: shortUrl });
    return retry;
  }

  private async _get(path: string): Promise<any> {
    const url = `${this.baseUrl}${path}`;
    const resp = await this._fetchWithRetry(url);
    if (!resp.ok) throw new Error(`farmOS API error: HTTP ${resp.status} for ${path}`);
    return resp.json();
  }

  private async _post(path: string, payload: any): Promise<any> {
    const url = `${this.baseUrl}${path}`;
    const resp = await this._fetchWithRetry(url, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`farmOS POST error: HTTP ${resp.status} - ${text}`);
    }
    return resp.json();
  }

  private async _patch(path: string, payload: any): Promise<any> {
    const url = `${this.baseUrl}${path}`;
    const resp = await this._fetchWithRetry(url, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`farmOS PATCH error: HTTP ${resp.status} - ${text}`);
    }
    return resp.json();
  }

  // ── Reliable query methods ──────────────────────────────────

  async fetchByName(apiPath: string, name: string): Promise<any[]> {
    const encoded = encodeURIComponent(name);
    const path = `/api/${apiPath}?filter[name]=${encoded}&page[limit]=50`;
    const data = await this._get(path);
    return data.data ?? [];
  }

  async fetchAllPaginated(
    apiPath: string,
    filters?: Record<string, string>,
    sort?: string,
    limit = 50,
    maxPages = 20,
  ): Promise<any[]> {
    const seen = new Map<string, any>();
    const effectiveSort = sort ?? 'name';

    let params = `page[limit]=${limit}`;
    if (filters) {
      for (const [key, value] of Object.entries(filters)) {
        params += `&filter[${key}]=${encodeURIComponent(value)}`;
      }
    }
    params += `&sort=${effectiveSort}`;

    let offset = 0;
    for (let page = 0; page < maxPages; page++) {
      const url = `${this.baseUrl}/api/${apiPath}?${params}&page[offset]=${offset}`;
      const resp = await this._fetchWithRetry(url);
      if (!resp.ok) throw new Error(`farmOS API error: HTTP ${resp.status} fetching ${apiPath}`);

      const data: any = await resp.json();
      const items: any[] = data.data ?? [];
      if (items.length === 0) break;

      for (const item of items) {
        const id = item.id;
        if (id) seen.set(id, item);
      }
      offset += limit;
    }

    return Array.from(seen.values());
  }

  async fetchFiltered(
    apiPath: string,
    filters?: Record<string, string>,
    sort?: string,
    maxResults = 50,
    include?: string,
  ): Promise<any[]> {
    let path = `/api/${apiPath}?page[limit]=${Math.min(maxResults, 50)}`;
    if (filters) {
      for (const [key, value] of Object.entries(filters)) {
        path += `&filter[${key}]=${encodeURIComponent(value)}`;
      }
    }
    if (sort) path += `&sort=${sort}`;
    if (include) path += `&include=${include}`;

    const data = await this._get(path);
    const items: any[] = data.data ?? [];

    if (include && data.included) {
      FarmOSClient.mergeIncludedQuantities(data, items);
    }

    return items;
  }

  // ── Cached lookups ──────────────────────────────────────────

  async getPlantTypeUuid(farmosName: string): Promise<string | null> {
    if (this.plantTypeCache.has(farmosName)) {
      return this.plantTypeCache.get(farmosName)!;
    }
    const terms = await this.fetchByName('taxonomy_term/plant_type', farmosName);
    if (terms.length > 0) {
      const uuid = terms[0].id;
      this.plantTypeCache.set(farmosName, uuid);
      return uuid;
    }
    return null;
  }

  async getSectionUuid(sectionId: string): Promise<string | null> {
    if (this.sectionCache.has(sectionId)) {
      return this.sectionCache.get(sectionId)!;
    }
    // Try land assets first (paddock sections: P1R1.0-5, P2R3.15-21, etc.)
    const landAssets = await this.fetchByName('asset/land', sectionId);
    if (landAssets.length > 0) {
      const uuid = landAssets[0].id;
      this.sectionCache.set(sectionId, uuid);
      return uuid;
    }
    // Fallback: try structure assets (nursery zones: NURS.SH1-1, etc.)
    const structAssets = await this.fetchByName('asset/structure', sectionId);
    if (structAssets.length > 0) {
      const uuid = structAssets[0].id;
      this.sectionCache.set(sectionId, uuid);
      return uuid;
    }
    return null;
  }

  async getSectionType(sectionId: string): Promise<string> {
    const landAssets = await this.fetchByName('asset/land', sectionId);
    if (landAssets.length > 0) return 'asset--land';
    const structAssets = await this.fetchByName('asset/structure', sectionId);
    if (structAssets.length > 0) return 'asset--structure';
    return 'asset--land'; // default
  }

  async plantAssetExists(assetName: string): Promise<string | null> {
    const assets = await this.fetchByName('asset/plant', assetName);
    return assets.length > 0 ? assets[0].id : null;
  }

  async logExists(logName: string, logType = 'observation'): Promise<string | null> {
    const logs = await this.fetchByName(`log/${logType}`, logName);
    return logs.length > 0 ? logs[0].id : null;
  }

  // ── Entity creation ─────────────────────────────────────────

  async createQuantity(plantId: string, count: number, adjustment = 'reset'): Promise<string | null> {
    const payload = {
      data: {
        type: 'quantity--standard',
        attributes: {
          value: { decimal: String(count) },
          measure: 'count',
          label: 'plants',
          inventory_adjustment: adjustment,
        },
        relationships: {
          units: { data: { type: 'taxonomy_term--unit', id: PLANT_UNIT_UUID } },
          inventory_asset: { data: { type: 'asset--plant', id: plantId } },
        },
      },
    };
    const result = await this._post('/api/quantity/standard', payload);
    return result.data?.id ?? null;
  }

  async createObservationLog(
    plantId: string,
    sectionUuid: string,
    quantityId: string | null,
    timestamp: number,
    name: string,
    notes = '',
    logStatus: 'done' | 'pending' = 'done',
  ): Promise<string | null> {
    const logData: any = {
      attributes: {
        name,
        timestamp: String(timestamp),
        status: logStatus,
        is_movement: true,
      },
      relationships: {
        asset: { data: [{ type: 'asset--plant', id: plantId }] },
        location: { data: [{ type: 'asset--land', id: sectionUuid }] },
      },
    };
    if (notes) logData.attributes.notes = { value: notes, format: 'default' };
    if (quantityId) {
      logData.relationships.quantity = { data: [{ type: 'quantity--standard', id: quantityId }] };
    }

    const payload = { data: { type: 'log--observation', ...logData } };
    const result = await this._post('/api/log/observation', payload);
    return result.data?.id ?? null;
  }

  async createActivityLog(
    sectionUuid: string,
    timestamp: number,
    name: string,
    notes = '',
    assetIds?: string[],
    locationType = 'asset--land',
    logStatus = 'done',
  ): Promise<string | null> {
    const logData: any = {
      attributes: {
        name,
        timestamp: String(timestamp),
        status: logStatus,
      },
      relationships: {
        location: { data: [{ type: locationType, id: sectionUuid }] },
      },
    };
    if (notes) logData.attributes.notes = { value: notes, format: 'default' };
    if (assetIds && assetIds.length > 0) {
      logData.relationships.asset = {
        data: assetIds.map((id) => ({ type: 'asset--plant', id })),
      };
    }

    const payload = { data: { type: 'log--activity', ...logData } };
    const result = await this._post('/api/log/activity', payload);
    return result.data?.id ?? null;
  }

  async createPlantAsset(
    name: string,
    plantTypeUuid: string,
    notes = '',
  ): Promise<string | null> {
    const data: any = {
      attributes: { name, status: 'active' },
      relationships: {
        plant_type: { data: [{ type: 'taxonomy_term--plant_type', id: plantTypeUuid }] },
      },
    };
    if (notes) data.attributes.notes = { value: notes, format: 'default' };

    const payload = { data: { type: 'asset--plant', ...data } };
    const result = await this._post('/api/asset/plant', payload);
    return result.data?.id ?? null;
  }

  // ── Seed asset creation ──────────────────────────────────────

  async seedAssetExists(name: string): Promise<string | null> {
    const assets = await this.fetchByName('asset/seed', name);
    return assets.length > 0 ? assets[0].id : null;
  }

  async createSeedAsset(name: string, plantTypeUuid: string, notes = ''): Promise<string | null> {
    const data: any = {
      attributes: { name, status: 'active' },
      relationships: {
        plant_type: { data: [{ type: 'taxonomy_term--plant_type', id: plantTypeUuid }] },
      },
    };
    if (notes) data.attributes.notes = { value: notes, format: 'default' };

    const payload = { data: { type: 'asset--seed', ...data } };
    const result = await this._post('/api/asset/seed', payload);
    return result.data?.id ?? null;
  }

  async createSeedQuantity(
    seedId: string,
    value: number,
    unitType: 'grams' | 'stock_level' = 'grams',
    adjustment: 'reset' | 'increment' | 'decrement' = 'reset',
  ): Promise<string | null> {
    const isGrams = unitType === 'grams';
    const payload = {
      data: {
        type: 'quantity--standard',
        attributes: {
          value: { decimal: String(value) },
          measure: isGrams ? 'weight' : 'rating',
          label: isGrams ? 'grams' : 'stock_level',
          inventory_adjustment: adjustment,
        },
        relationships: {
          units: { data: { type: 'taxonomy_term--unit', id: GRAMS_UNIT_UUID } },
          inventory_asset: { data: { type: 'asset--seed', id: seedId } },
        },
      },
    };
    const result = await this._post('/api/quantity/standard', payload);
    return result.data?.id ?? null;
  }

  async createSeedObservationLog(
    seedId: string,
    quantityId: string | null,
    timestamp: number,
    name: string,
    notes = '',
    isMovement = true,
  ): Promise<string | null> {
    const logData: any = {
      attributes: {
        name,
        timestamp: String(timestamp),
        status: 'done',
        is_movement: isMovement,
      },
      relationships: {
        asset: { data: [{ type: 'asset--seed', id: seedId }] },
        location: { data: [{ type: 'asset--structure', id: NURS_FRDG_UUID }] },
      },
    };
    if (notes) logData.attributes.notes = { value: notes, format: 'default' };
    if (quantityId) {
      logData.relationships.quantity = { data: [{ type: 'quantity--standard', id: quantityId }] };
    }
    const payload = { data: { type: 'log--observation', ...logData } };
    const result = await this._post('/api/log/observation', payload);
    return result.data?.id ?? null;
  }

  // ── Query helpers for tools ─────────────────────────────────

  private async fetchPlantsContains(nameContains: string, status = 'active', maxPages = 20): Promise<any[]> {
    const encoded = encodeURIComponent(nameContains);
    const basePath = `/api/asset/plant?filter[name][operator]=CONTAINS&filter[name][value]=${encoded}&filter[status]=${status}&sort=name&page[limit]=50`;

    const seen = new Map<string, any>();
    let offset = 0;

    for (let page = 0; page < maxPages; page++) {
      const url = `${this.baseUrl}${basePath}&page[offset]=${offset}`;
      const resp = await this._fetchWithRetry(url);
      if (!resp.ok) throw new Error(`farmOS API error: HTTP ${resp.status}`);

      const data: any = await resp.json();
      const items = data.data ?? [];
      if (items.length === 0) break;

      for (const item of items) {
        if (item.id) seen.set(item.id, item);
      }
      offset += 50;
    }

    return Array.from(seen.values());
  }

  async getSeedAssets(sectionId?: string, species?: string, status = 'active'): Promise<any[]> {
    if (species) return this.fetchSeedsContains(species, status);
    if (sectionId) return this.fetchSeedsContains(sectionId, status);
    return this.fetchAllPaginated('asset/seed', { status });
  }

  private async fetchSeedsContains(nameContains: string, status = 'active', maxPages = 20): Promise<any[]> {
    const encoded = encodeURIComponent(nameContains);
    const basePath = `/api/asset/seed?filter[name][operator]=CONTAINS&filter[name][value]=${encoded}&filter[status]=${status}&sort=name&page[limit]=50`;
    const seen = new Map<string, any>();
    let offset = 0;
    for (let page = 0; page < maxPages; page++) {
      const url = `${this.baseUrl}${basePath}&page[offset]=${offset}`;
      const resp = await this._fetchWithRetry(url);
      if (!resp.ok) throw new Error(`farmOS API error: HTTP ${resp.status}`);
      const data: any = await resp.json();
      const items = data.data ?? [];
      if (items.length === 0) break;
      for (const item of items) { if (item.id) seen.set(item.id, item); }
      offset += 50;
    }
    return Array.from(seen.values());
  }

  async getPlantAssets(sectionId?: string, species?: string, status = 'active'): Promise<any[]> {
    if (species && sectionId) {
      const plants = await this.fetchPlantsContains(sectionId, status);
      // Exact species match using parsed asset name to avoid partial matches
      // e.g., "Strawberry" must NOT match "Guava (Strawberry)"
      return plants.filter((p) => {
        const name = p.attributes?.name ?? '';
        const parts = name.split(' - ');
        const extractedSpecies = parts.length >= 3 ? parts.slice(1, -1).join(' - ') : name;
        return extractedSpecies.toLowerCase() === species.toLowerCase();
      });
    }
    if (species) return this.fetchPlantsContains(species, status);
    if (sectionId) return this.fetchPlantsContains(sectionId, status);
    return this.fetchAllPaginated('asset/plant', { status });
  }

  async getSectionAssets(rowFilter?: string): Promise<any[]> {
    const allSections = await this.fetchAllPaginated('asset/land');
    const sectionPattern = /^P\dR\d\.\d+-\d+$/;

    if (rowFilter) {
      return allSections.filter((s) =>
        (s.attributes?.name ?? '').startsWith(rowFilter + '.'),
      );
    }
    return allSections.filter((s) =>
      sectionPattern.test(s.attributes?.name ?? ''),
    );
  }

  async getAllLocations(typeFilter?: string): Promise<Record<string, any[]>> {
    const grouped: Record<string, any[]> = { paddock: [], nursery: [], compost: [], other: [] };
    const paddockPattern = /^P\dR\d\.\d+-\d+$/;
    const nurseryPattern = /^NURS\./;
    const compostPattern = /^COMP\./;

    const landAssets = await this.fetchAllPaginated('asset/land');
    for (const asset of landAssets) {
      const name = asset.attributes?.name ?? '';
      const entry = { name, uuid: asset.id, asset_type: 'land', status: asset.attributes?.status ?? 'active' };
      if (paddockPattern.test(name)) grouped.paddock.push(entry);
      else if (nurseryPattern.test(name)) grouped.nursery.push(entry);
      else if (compostPattern.test(name)) grouped.compost.push(entry);
      else grouped.other.push(entry);
    }

    const structureAssets = await this.fetchAllPaginated('asset/structure');
    for (const asset of structureAssets) {
      const name = asset.attributes?.name ?? '';
      const entry = { name, uuid: asset.id, asset_type: 'structure', status: asset.attributes?.status ?? 'active' };
      if (nurseryPattern.test(name)) grouped.nursery.push(entry);
      else if (compostPattern.test(name)) grouped.compost.push(entry);
      else grouped.other.push(entry);
    }

    for (const key of Object.keys(grouped)) {
      grouped[key].sort((a, b) => a.name.localeCompare(b.name));
    }

    if (typeFilter && typeFilter in grouped) {
      return { [typeFilter]: grouped[typeFilter] };
    }
    return grouped;
  }

  static mergeIncludedQuantities(data: any, items: any[]): void {
    const included: any[] = data.included ?? [];
    if (!included.length) return;

    const qtyLookup = new Map<string, any>();
    for (const inc of included) {
      if ((inc.type ?? '').startsWith('quantity--')) {
        qtyLookup.set(inc.id, inc);
      }
    }

    for (const item of items) {
      const qtyRels = item.relationships?.quantity?.data ?? [];
      if (qtyRels.length > 0) {
        item._quantities = qtyRels
          .map((qr: any) => qtyLookup.get(qr.id))
          .filter(Boolean);
      }
    }
  }

  private async fetchLogsContains(
    logType: string,
    nameContains: string,
    includeQuantity = true,
    maxPages = 20,
  ): Promise<any[]> {
    const encoded = encodeURIComponent(nameContains);
    let basePath = `/api/log/${logType}?filter[name][operator]=CONTAINS&filter[name][value]=${encoded}&page[limit]=50&sort=-timestamp,name`;
    if (includeQuantity) basePath += '&include=quantity';

    const seen = new Map<string, any>();
    let offset = 0;

    for (let page = 0; page < maxPages; page++) {
      const url = `${this.baseUrl}${basePath}&page[offset]=${offset}`;
      const resp = await this._fetchWithRetry(url);
      if (!resp.ok) throw new Error(`farmOS API error: HTTP ${resp.status}`);

      const data: any = await resp.json();
      const pageItems = data.data ?? [];
      if (pageItems.length === 0) break;

      if (includeQuantity) {
        FarmOSClient.mergeIncludedQuantities(data, pageItems);
      }

      for (const item of pageItems) {
        if (item.id) seen.set(item.id, item);
      }
      offset += 50;
    }

    return Array.from(seen.values());
  }

  async getLogs(
    logType?: string,
    sectionId?: string,
    species?: string,
    maxResults = 50,
    status?: string,
  ): Promise<any[]> {
    const logTypes = logType
      ? [logType]
      : ['observation', 'activity', 'transplanting', 'harvest', 'seeding'];

    const nameFilter = sectionId ?? species;
    const allLogs: any[] = [];

    for (const lt of logTypes) {
      try {
        if (nameFilter) {
          const logs = await this.fetchLogsContains(lt, nameFilter, true);
          allLogs.push(...logs);
        } else {
          const logs = await this.fetchFiltered(`log/${lt}`, undefined, '-timestamp', maxResults, 'quantity');
          allLogs.push(...logs);
        }
      } catch {
        continue;
      }
    }

    let filtered = allLogs;
    if (sectionId && species) {
      filtered = filtered.filter((l) =>
        (l.attributes?.name ?? '').toLowerCase().includes(species.toLowerCase()),
      );
    }

    // Filter by status if specified (pending, done)
    if (status) {
      filtered = filtered.filter((l) => l.attributes?.status === status);
    }

    filtered.sort((a, b) => {
      const tsA = a.attributes?.timestamp ?? '';
      const tsB = b.attributes?.timestamp ?? '';
      return tsB.localeCompare(tsA);
    });

    return filtered.slice(0, maxResults);
  }

  async updateLogStatus(logId: string, logType: string, newStatus: string): Promise<boolean> {
    const payload = {
      data: {
        type: `log--${logType}`,
        id: logId,
        attributes: { status: newStatus },
      },
    };
    const resp = await this._patch(`/api/log/${logType}/${logId}`, payload);
    return !!resp?.data?.id;
  }

  async updateLogNotes(logId: string, logType: string, notes: string): Promise<boolean> {
    const payload = {
      data: {
        type: `log--${logType}`,
        id: logId,
        attributes: { notes: { value: notes, format: 'default' } },
      },
    };
    const resp = await this._patch(`/api/log/${logType}/${logId}`, payload);
    return !!resp?.data?.id;
  }

  async getPlantTypeDetails(name?: string): Promise<any[]> {
    if (name) return this.fetchByName('taxonomy_term/plant_type', name);
    return this.getAllPlantTypesCached();
  }

  async getAllPlantTypesCached(): Promise<any[]> {
    const now = Date.now() / 1000;
    if (this.plantTypeFullCache && (now - this.plantTypeFullCacheTime) < this.PLANT_TYPE_CACHE_TTL) {
      return this.plantTypeFullCache;
    }
    const result = await this.fetchAllPaginated('taxonomy_term/plant_type');
    this.plantTypeFullCache = result;
    this.plantTypeFullCacheTime = now;
    return result;
  }

  private invalidatePlantTypeCache(): void {
    this.plantTypeFullCache = null;
    this.plantTypeFullCacheTime = 0;
  }

  async getRecentLogs(count = 20): Promise<any[]> {
    return this.getLogs(undefined, undefined, undefined, count);
  }

  // ── Plant type taxonomy management ─────────────────────────

  async createPlantType(
    name: string,
    description: string,
    maturityDays?: number,
    transplantDays?: number,
  ): Promise<string | null> {
    const attrs: any = {
      name,
      description: { value: description, format: 'default' },
    };
    if (maturityDays && maturityDays > 0) attrs.maturity_days = maturityDays;
    if (transplantDays && transplantDays > 0) attrs.transplant_days = transplantDays;

    const payload = { data: { type: 'taxonomy_term--plant_type', attributes: attrs } };
    const result = await this._post('/api/taxonomy_term/plant_type', payload);
    this.invalidatePlantTypeCache();
    return result.data?.id ?? null;
  }

  async updatePlantType(uuid: string, attributes: Record<string, any>): Promise<any> {
    const payload = {
      data: {
        type: 'taxonomy_term--plant_type',
        id: uuid,
        attributes,
      },
    };
    const result = await this._patch(`/api/taxonomy_term/plant_type/${uuid}`, payload);
    this.invalidatePlantTypeCache();
    return result;
  }

  // ── Plant asset management ─────────────────────────────────

  async archivePlant(nameOrUuid: string): Promise<any> {
    const isUuid = nameOrUuid.length === 36 && (nameOrUuid.match(/-/g) ?? []).length === 4;
    let plantUuid: string;

    if (isUuid) {
      plantUuid = nameOrUuid;
    } else {
      const assets = await this.fetchByName('asset/plant', nameOrUuid);
      if (assets.length === 0) {
        throw new Error(`Plant asset '${nameOrUuid}' not found in farmOS`);
      }
      plantUuid = assets[0].id;
    }

    const payload = {
      data: {
        type: 'asset--plant',
        id: plantUuid,
        attributes: { status: 'archived' },
      },
    };
    const result = await this._patch(`/api/asset/plant/${plantUuid}`, payload);
    return result.data ?? {};
  }

  // ── File upload ────────────────────────────────────────────

  async uploadFile(
    entityType: string,
    entityId: string,
    fieldName: string,
    filename: string,
    binaryData: ArrayBuffer,
    mimeType = 'image/jpeg',
  ): Promise<string | null> {
    const url = `${this.baseUrl}/api/${entityType}/${entityId}/${fieldName}`;
    const resp = await this._fetchWithRetry(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/octet-stream',
        'Content-Disposition': `file; filename="${filename}"`,
      },
      body: binaryData,
    });
    if (!resp.ok) throw new Error(`farmOS file upload error: HTTP ${resp.status}`);
    const result: any = await resp.json();
    // farmOS file uploads may return {data: {...}} (dict) or {data: [{...}]} (list)
    // depending on version / field cardinality. Python farmos_client handles
    // both; TS must match or we silently return null on successful uploads
    // (discovered 2026-04-21: every photo upload in tonight's session hit
    // upload_returned_null because farmOS returned list form for log.image
    // and our code only checked data.id on a dict).
    //
    // 2026-04-22: multi-valued list response takes the LAST entry, not the
    // first. Background: when POSTing a file to a multi-valued relationship
    // like taxonomy_term/plant_type/{id}/image, farmOS appends the new file
    // to the existing list and returns [prior, ..., new]. Returning data[0]
    // gave us the PRIOR file's id — then the downstream patchRelationship
    // step overwrote the relationship with that prior id, silently orphaning
    // the newly uploaded file and leaving the stale one as the reference
    // photo. Audit on 2026-04-22 found 8 of 8 species-reference photos
    // still pointing at pre-ADR-0005 stock/old-format photos despite
    // species_reference_photos_updated=1 being reported as success for
    // each one in the import pipeline.
    const data = result?.data;
    if (Array.isArray(data)) {
      // Empty list → no upload occurred. Otherwise, newest is last.
      return data.length > 0 ? (data[data.length - 1]?.id ?? null) : null;
    }
    return data?.id ?? null;
  }

  /**
   * Raw JSON:API GET — used by the photo pipeline (ADR 0008 I4 dedup,
   * I5 tier-aware promotion) to inspect existing file relationships
   * before uploading. Returns the parsed JSON response or throws.
   */
  async getRaw(path: string): Promise<any> {
    const url = path.startsWith('http') ? path : `${this.baseUrl}${path}`;
    const resp = await this._fetchWithRetry(url, { method: 'GET' });
    if (!resp.ok) throw new Error(`farmOS GET ${path}: HTTP ${resp.status}`);
    return resp.json();
  }

  /**
   * PATCH a relationship on an entity — used by the photo pipeline
   * (ADR 0008 I5) to collapse plant_type.image to single-valued after
   * promoting a new reference photo. Idempotent; graceful on 204.
   */
  async patchRelationship(
    entityType: string,
    entityId: string,
    fieldName: string,
    refs: Array<{ type: string; id: string }>,
  ): Promise<boolean> {
    const url = `${this.baseUrl}/api/${entityType}/${entityId}/relationships/${fieldName}`;
    const resp = await this._fetchWithRetry(url, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/vnd.api+json' },
      body: JSON.stringify({ data: refs }),
    });
    return resp.ok;
  }

  // ── Utilities ──────────────────────────────────────────────

  private getNextLink(data: any): string | null {
    const nextLink = data.links?.next;
    if (!nextLink) return null;
    if (typeof nextLink === 'string') return nextLink || null;
    if (typeof nextLink === 'object') return nextLink.href || null;
    return null;
  }
}
