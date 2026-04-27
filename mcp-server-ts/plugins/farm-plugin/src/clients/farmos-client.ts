/**
 * farmOS JSON:API HTTP client.
 *
 * Auth-stateless: takes a pre-configured framework HttpClient (from
 * @fireflyagents/mcp-shared-utils) which holds the OAuth2 access token in
 * its default Authorization header and handles 401-driven reactive refresh
 * transparently via the onUnauthorized callback. See ADR 0010 + the
 * post-2026-04-27 follow-up commit dropping the hand-driven _fetchWithRetry.
 *
 * This client owns: pagination with dedup, CONTAINS filters, cached lookups,
 * and all CRUD operations needed by the MCP tools.
 */

import type { HttpClient } from '@fireflyagents/mcp-shared-utils';
import { HttpClientError } from '@fireflyagents/mcp-shared-utils';
import { logger as baseLogger } from '@fireflyagents/mcp-shared-utils';
import {
  type ApiVersion,
  type AssetStatus,
  assetStatusFilter,
  assetStatusFilterParam,
  assetArchivePayload,
  readAssetStatus,
} from './api-version.js';

const logger = baseLogger.child({ context: 'farm-plugin:farmos-client' });

const PLANT_UNIT_UUID = '2371b79e-a87b-4152-b6e4-ea6a9ed37fd0';
const GRAMS_UNIT_UUID = 'e7bad672-9c33-4138-9fc3-1b0548a33aca';
const NURS_FRDG_UUID = '429fcdd3-8be6-436a-b439-49186f56b3c7';

interface FarmOSConfig {
  /** farmOS base URL (e.g. https://margregen.farmos.net). Trailing slashes stripped. */
  farmUrl: string;
  /**
   * Pre-configured framework HttpClient. Constructed by getFarmOSClient with
   * the bearer token in default headers and onUnauthorized wired to the
   * framework's reactive refresh callback. Tests pass a mock implementation.
   */
  httpClient: HttpClient;
  /**
   * farmOS JSON:API version flag. Default `'3'` (legacy). Set `'4'` after
   * Mike upgrades margregen. Drives asset status filter / archive PATCH /
   * display reader behaviour via the helpers in `api-version.ts`. See ADR 0009.
   */
  apiVersion?: ApiVersion;
}

export class FarmOSClient {
  private httpClient: HttpClient;
  /** Public so tools can use it with the standalone helpers when needed. */
  readonly apiVersion: ApiVersion;
  private plantTypeCache = new Map<string, string>(); // farmos_name → UUID
  private sectionCache = new Map<string, string>(); // section_id → UUID
  private plantTypeFullCache: any[] | null = null;
  private plantTypeFullCacheTime = 0;
  private readonly PLANT_TYPE_CACHE_TTL = 300; // 5 minutes

  constructor(config: FarmOSConfig) {
    if (!config.httpClient) {
      throw new Error('FarmOSClient: httpClient is required (constructed by getFarmOSClient).');
    }
    this.httpClient = config.httpClient;
    this.apiVersion = config.apiVersion ?? '3';
  }

  /** Always true for a constructed client; kept as a back-compat shim. */
  get isConnected(): boolean {
    return true;
  }

  /**
   * Convenience: produce the right asset-status filter dict for THIS client's
   * version. Use at tool call sites that pass a filters dict to
   * `fetchAllPaginated` / `fetchFiltered`.
   */
  assetStatusFilter(status: AssetStatus): Record<string, string> {
    return assetStatusFilter(this.apiVersion, status);
  }

  // ── Low-level HTTP ──────────────────────────────────────────
  //
  // These wrap the framework's HttpClient calls in our error-message format
  // so callers see consistent "farmOS API error: HTTP <status> for <path>"
  // messages (existing tests grep for that shape). The framework throws
  // HttpClientError on non-2xx; we re-throw with our message and let other
  // errors propagate unchanged. 401-driven refresh is fully owned by the
  // axios interceptor in the framework HttpClient (see axios-client.js:43-71).

  private async _get(path: string): Promise<any> {
    try {
      const resp = await this.httpClient.get(path);
      return resp.data;
    } catch (e) {
      if (e instanceof HttpClientError) {
        throw new Error(`farmOS API error: HTTP ${e.status} for ${path}`);
      }
      throw e;
    }
  }

  private async _post(path: string, payload: any): Promise<any> {
    try {
      const resp = await this.httpClient.post(path, payload);
      return resp.data;
    } catch (e) {
      if (e instanceof HttpClientError) {
        const body = typeof e.response === 'string' ? e.response : JSON.stringify(e.response ?? {});
        throw new Error(`farmOS POST error: HTTP ${e.status} - ${body}`);
      }
      throw e;
    }
  }

  private async _patch(path: string, payload: any): Promise<any> {
    try {
      const resp = await this.httpClient.patch(path, payload);
      return resp.data;
    } catch (e) {
      if (e instanceof HttpClientError) {
        const body = typeof e.response === 'string' ? e.response : JSON.stringify(e.response ?? {});
        throw new Error(`farmOS PATCH error: HTTP ${e.status} - ${body}`);
      }
      throw e;
    }
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
      const path = `/api/${apiPath}?${params}&page[offset]=${offset}`;
      let data: any;
      try {
        const resp = await this.httpClient.get(path);
        data = resp.data;
      } catch (e) {
        if (e instanceof HttpClientError) {
          throw new Error(`farmOS API error: HTTP ${e.status} fetching ${apiPath}`);
        }
        throw e;
      }

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
    // No `status` field on creation: redundant in v3 (active is the default)
    // and the field doesn't exist in v4. ADR 0009.
    const data: any = {
      attributes: { name },
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
    // No `status` field on creation (see createPlantAsset comment). ADR 0009.
    const data: any = {
      attributes: { name },
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

  private async fetchPlantsContains(nameContains: string, status: AssetStatus = 'active', maxPages = 20): Promise<any[]> {
    const encoded = encodeURIComponent(nameContains);
    const statusParam = assetStatusFilterParam(this.apiVersion, status);
    const basePath = `/api/asset/plant?filter[name][operator]=CONTAINS&filter[name][value]=${encoded}&${statusParam}&sort=name&page[limit]=50`;

    const seen = new Map<string, any>();
    let offset = 0;

    for (let page = 0; page < maxPages; page++) {
      const path = `${basePath}&page[offset]=${offset}`;
      let data: any;
      try {
        const resp = await this.httpClient.get(path);
        data = resp.data;
      } catch (e) {
        if (e instanceof HttpClientError) {
          throw new Error(`farmOS API error: HTTP ${e.status}`);
        }
        throw e;
      }

      const items = data.data ?? [];
      if (items.length === 0) break;

      for (const item of items) {
        if (item.id) seen.set(item.id, item);
      }
      offset += 50;
    }

    return Array.from(seen.values());
  }

  async getSeedAssets(sectionId?: string, species?: string, status: AssetStatus = 'active'): Promise<any[]> {
    if (species) return this.fetchSeedsContains(species, status);
    if (sectionId) return this.fetchSeedsContains(sectionId, status);
    return this.fetchAllPaginated('asset/seed', this.assetStatusFilter(status));
  }

  private async fetchSeedsContains(nameContains: string, status: AssetStatus = 'active', maxPages = 20): Promise<any[]> {
    const encoded = encodeURIComponent(nameContains);
    const statusParam = assetStatusFilterParam(this.apiVersion, status);
    const basePath = `/api/asset/seed?filter[name][operator]=CONTAINS&filter[name][value]=${encoded}&${statusParam}&sort=name&page[limit]=50`;
    const seen = new Map<string, any>();
    let offset = 0;
    for (let page = 0; page < maxPages; page++) {
      const path = `${basePath}&page[offset]=${offset}`;
      let data: any;
      try {
        const resp = await this.httpClient.get(path);
        data = resp.data;
      } catch (e) {
        if (e instanceof HttpClientError) {
          throw new Error(`farmOS API error: HTTP ${e.status}`);
        }
        throw e;
      }
      const items = data.data ?? [];
      if (items.length === 0) break;
      for (const item of items) { if (item.id) seen.set(item.id, item); }
      offset += 50;
    }
    return Array.from(seen.values());
  }

  async getPlantAssets(sectionId?: string, species?: string, status: AssetStatus = 'active'): Promise<any[]> {
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
    return this.fetchAllPaginated('asset/plant', this.assetStatusFilter(status));
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
      const entry = { name, uuid: asset.id, asset_type: 'land', status: readAssetStatus(asset) };
      if (paddockPattern.test(name)) grouped.paddock.push(entry);
      else if (nurseryPattern.test(name)) grouped.nursery.push(entry);
      else if (compostPattern.test(name)) grouped.compost.push(entry);
      else grouped.other.push(entry);
    }

    const structureAssets = await this.fetchAllPaginated('asset/structure');
    for (const asset of structureAssets) {
      const name = asset.attributes?.name ?? '';
      const entry = { name, uuid: asset.id, asset_type: 'structure', status: readAssetStatus(asset) };
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
      const path = `${basePath}&page[offset]=${offset}`;
      let data: any;
      try {
        const resp = await this.httpClient.get(path);
        data = resp.data;
      } catch (e) {
        if (e instanceof HttpClientError) {
          throw new Error(`farmOS API error: HTTP ${e.status}`);
        }
        throw e;
      }

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
        attributes: assetArchivePayload(this.apiVersion),
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
    _mimeType = 'image/jpeg',
  ): Promise<string | null> {
    const path = `/api/${entityType}/${entityId}/${fieldName}`;
    let result: any;
    try {
      const resp = await this.httpClient.post(path, binaryData, {
        headers: {
          'Content-Type': 'application/octet-stream',
          'Content-Disposition': `file; filename="${filename}"`,
        },
      });
      result = resp.data;
    } catch (e) {
      if (e instanceof HttpClientError) {
        throw new Error(`farmOS file upload error: HTTP ${e.status}`);
      }
      throw e;
    }
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
    // Absolute URLs (cross-host file fetches) bypass the framework HttpClient's
    // baseURL; relative paths are prepended by axios.
    try {
      const resp = await this.httpClient.get(path);
      return resp.data;
    } catch (e) {
      if (e instanceof HttpClientError) {
        throw new Error(`farmOS GET ${path}: HTTP ${e.status}`);
      }
      throw e;
    }
  }

  /**
   * PATCH a relationship on an entity — used by the photo pipeline
   * (ADR 0008 I5) to collapse plant_type.image to single-valued after
   * promoting a new reference photo. Idempotent; graceful on 204/2xx.
   */
  async patchRelationship(
    entityType: string,
    entityId: string,
    fieldName: string,
    refs: Array<{ type: string; id: string }>,
  ): Promise<boolean> {
    const path = `/api/${entityType}/${entityId}/relationships/${fieldName}`;
    try {
      await this.httpClient.patch(path, { data: refs });
      return true;
    } catch (e) {
      if (e instanceof HttpClientError) {
        logger.warn('patchRelationship failed', { path, status: e.status });
        return false;
      }
      throw e;
    }
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
