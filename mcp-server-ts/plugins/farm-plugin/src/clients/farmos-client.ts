/**
 * farmOS JSON:API HTTP client with OAuth2 password grant authentication.
 *
 * Ported from Python farmos_client.py. Uses native fetch (no axios).
 * Implements pagination with dedup, CONTAINS filters, cached lookups,
 * and all CRUD operations needed by the 27 MCP tools.
 */

import { logger as baseLogger } from '@fireflyagents/mcp-shared-utils';

const logger = baseLogger.child({ context: 'farm-plugin:farmos-client' });

const PLANT_UNIT_UUID = '2371b79e-a87b-4152-b6e4-ea6a9ed37fd0';
const GRAMS_UNIT_UUID = 'e7bad672-9c33-4138-9fc3-1b0548a33aca';
const NURS_FRDG_UUID = '429fcdd3-8be6-436a-b439-49186f56b3c7';

interface FarmOSConfig {
  farmUrl: string;
  username: string;
  password: string;
}

export class FarmOSClient {
  private baseUrl: string;
  private token: string | null = null;
  private config: FarmOSConfig;
  private plantTypeCache = new Map<string, string>(); // farmos_name → UUID
  private sectionCache = new Map<string, string>(); // section_id → UUID
  private plantTypeFullCache: any[] | null = null;
  private plantTypeFullCacheTime = 0;
  private readonly PLANT_TYPE_CACHE_TTL = 300; // 5 minutes
  private connected = false;

  // ── Connection stats for observability ─────────────────────
  private stats = {
    connectCount: 0,
    retryCount: 0,
    retrySuccessCount: 0,
    retryFailCount: 0,
    lastConnectAt: null as string | null,
    lastRetryAt: null as string | null,
  };

  // Singleton per farmUrl
  private static instances = new Map<string, FarmOSClient>();

  private constructor(config: FarmOSConfig) {
    this.config = config;
    this.baseUrl = config.farmUrl.replace(/\/+$/, '');
  }

  static getInstance(config: FarmOSConfig): FarmOSClient {
    const key = config.farmUrl;
    let instance = FarmOSClient.instances.get(key);
    if (!instance) {
      instance = new FarmOSClient(config);
      FarmOSClient.instances.set(key, instance);
    }
    return instance;
  }

  get isConnected(): boolean {
    return this.connected;
  }

  async connect(): Promise<boolean> {
    const tokenUrl = `${this.baseUrl}/oauth/token`;
    const body = new URLSearchParams({
      grant_type: 'password',
      username: this.config.username,
      password: this.config.password,
      client_id: 'farm',
      scope: 'farm_manager',
    });

    const resp = await fetch(tokenUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: body.toString(),
    });

    if (!resp.ok) {
      logger.error('farmOS connect failed', { status: resp.status, url: this.baseUrl });
      throw new Error(`farmOS OAuth2 authentication failed: HTTP ${resp.status}`);
    }

    const data: any = await resp.json();
    this.token = data.access_token;
    this.connected = true;
    this.stats.connectCount++;
    this.stats.lastConnectAt = new Date().toISOString();
    logger.info('Connected to farmOS', { url: this.baseUrl, connectCount: this.stats.connectCount });
    return true;
  }

  getStats() {
    return { ...this.stats };
  }

  private get headers(): Record<string, string> {
    return {
      Authorization: `Bearer ${this.token}`,
      'Content-Type': 'application/vnd.api+json',
      Accept: 'application/vnd.api+json',
    };
  }

  // ── Low-level HTTP ──────────────────────────────────────────

  async ensureConnected(): Promise<void> {
    if (!this.connected) {
      await this.connect();
    }
  }

  /**
   * Unified fetch wrapper: retry once on 401/403 with a fresh token.
   * All HTTP methods route through here for consistent auth handling.
   */
  private async _fetchWithRetry(url: string, init?: RequestInit): Promise<Response> {
    await this.ensureConnected();
    const mergedInit = { ...init, headers: { ...this.headers, ...init?.headers } };
    const resp = await fetch(url, mergedInit);

    if (resp.status === 401 || resp.status === 403) {
      this.connected = false;
      this.stats.retryCount++;
      this.stats.lastRetryAt = new Date().toISOString();
      const shortUrl = url.replace(this.baseUrl, '');
      logger.warn('Auth expired, reconnecting', { url: shortUrl, status: resp.status });

      await this.connect();
      const retry = await fetch(url, { ...init, headers: { ...this.headers, ...init?.headers } });

      if (retry.status === 401 || retry.status === 403) {
        this.stats.retryFailCount++;
        logger.error('Auth retry failed', { url: shortUrl, status: retry.status });
        throw new Error(`farmOS authentication failed after retry (HTTP ${retry.status})`);
      }

      this.stats.retrySuccessCount++;
      logger.info('Auth retry succeeded', { url: shortUrl });
      return retry;
    }

    return resp;
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
    while (true) {
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
  ): Promise<string | null> {
    const logData: any = {
      attributes: {
        name,
        timestamp: String(timestamp),
        status: 'done',
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
    return result.data?.id ?? null;
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
