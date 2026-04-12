/**
 * PlantNet species verification for the photo pipeline.
 *
 * Calls the PlantNet Identify API to check whether a photo actually
 * depicts the claimed species before attaching it to a farmOS log or
 * setting it as a species reference photo.
 *
 * Mirrors mcp-server/plantnet_verify.py.
 */

import { logger as baseLogger } from '@fireflyagents/mcp-shared-utils';
import * as fs from 'node:fs';
import * as path from 'node:path';

const logger = baseLogger.child({ context: 'plantnet-verify' });

const PLANTNET_URL = 'https://my-api.plantnet.org/v2/identify/all';
const CONFIDENCE_THRESHOLD = 0.30;

let _plantnetCalls = 0;

export interface VerifyResult {
  verified: boolean;
  plantnetTop: string;
  confidence: number;
  reason: string;
}

export interface BotanicalLookup {
  /** botanical_name.toLowerCase() → farmos_name */
  forward: Map<string, string>;
  /** farmos_name → botanical_name.toLowerCase() */
  reverse: Map<string, string>;
}

/**
 * Build botanical lookup from formatted plant type objects.
 *
 * Accepts the output of formatPlantType() which has a botanical_name field
 * extracted from the description via parsePlantTypeMetadata.
 */
export function buildBotanicalLookup(
  plantTypes: Array<{ name: string; botanical_name?: string }>
): BotanicalLookup {
  const forward = new Map<string, string>();
  const reverse = new Map<string, string>();

  for (const pt of plantTypes) {
    const name = pt.name?.trim();
    const botanical = pt.botanical_name?.trim();
    if (name && botanical) {
      forward.set(botanical.toLowerCase(), name);
      reverse.set(name, botanical.toLowerCase());
    }
  }

  return { forward, reverse };
}

/**
 * Build botanical lookup from plant_types.csv content (string).
 * Useful when the CSV is loaded as a file rather than via farmOS API.
 */
export function buildBotanicalLookupFromCsv(csvContent: string): BotanicalLookup {
  const lines = csvContent.split('\n');
  if (lines.length < 2) return { forward: new Map(), reverse: new Map() };

  const header = lines[0].split(',');
  const nameIdx = header.indexOf('farmos_name');
  const botIdx = header.indexOf('botanical_name');
  if (nameIdx < 0 || botIdx < 0) return { forward: new Map(), reverse: new Map() };

  const forward = new Map<string, string>();
  const reverse = new Map<string, string>();

  for (let i = 1; i < lines.length; i++) {
    const cols = lines[i].split(',');
    const name = cols[nameIdx]?.trim();
    const botanical = cols[botIdx]?.trim();
    if (name && botanical) {
      forward.set(botanical.toLowerCase(), name);
      reverse.set(name, botanical.toLowerCase());
    }
  }

  return { forward, reverse };
}

/**
 * Synonym bridge: PlantNet botanical name → farmOS botanical name.
 * Loaded from knowledge/plantnet_bridge.csv on first use.
 */
let _synonymBridge: Map<string, string> | null = null;

function getSynonymBridge(): Map<string, string> {
  if (_synonymBridge) return _synonymBridge;
  _synonymBridge = new Map();
  try {
    const csvPath = path.resolve(__dirname, '../../../../knowledge/plantnet_bridge.csv');
    const content = fs.readFileSync(csvPath, 'utf-8');
    const lines = content.split('\n');
    if (lines.length < 2) return _synonymBridge;
    const header = lines[0].split(',');
    const pnIdx = header.indexOf('plantnet_botanical');
    const fbIdx = header.indexOf('farmos_botanical');
    const typeIdx = header.indexOf('match_type');
    if (pnIdx < 0 || fbIdx < 0) return _synonymBridge;
    for (let i = 1; i < lines.length; i++) {
      const cols = lines[i].split(',');
      const pn = cols[pnIdx]?.trim().toLowerCase();
      const fb = cols[fbIdx]?.trim().toLowerCase();
      const matchType = cols[typeIdx]?.trim();
      if (pn && fb && ['synonym', 'genus', 'related_species'].includes(matchType)) {
        _synonymBridge.set(pn, fb);
      }
    }
  } catch {
    // Bridge CSV not found — no synonyms available
  }
  return _synonymBridge;
}

function botanicalMatch(plantnetName: string, expected: string): boolean {
  const a = plantnetName.toLowerCase().trim();
  const b = expected.toLowerCase().trim();

  // Direct match (exact or prefix)
  if (a === b || a.startsWith(b) || b.startsWith(a)) return true;

  // Synonym bridge
  const bridge = getSynonymBridge();
  const resolved = bridge.get(a);
  if (resolved && (resolved === b || resolved.startsWith(b) || b.startsWith(resolved))) return true;

  // Genus-level: if expected ends with "spp." match on genus prefix
  if (b.endsWith('spp.')) {
    const genus = b.replace('spp.', '').trim();
    if (a.startsWith(genus)) return true;
  }

  return false;
}

/**
 * Verify a photo matches the claimed species via PlantNet.
 *
 * Returns a VerifyResult indicating whether the photo should be attached.
 * On API errors, returns verified=false (safe default: skip photo).
 */
export async function verifySpeciesPhoto(
  imageBytes: ArrayBuffer | Buffer,
  claimedSpecies: string,
  lookup: BotanicalLookup,
  apiKey?: string,
): Promise<VerifyResult> {
  const key = apiKey ?? process.env.PLANTNET_API_KEY ?? '';

  if (!key) {
    return { verified: false, plantnetTop: '', confidence: 0, reason: 'no_api_key' };
  }

  if (!claimedSpecies) {
    return { verified: true, plantnetTop: '', confidence: 0, reason: 'no_species_claim' };
  }

  const expectedBotanical = lookup.reverse.get(claimedSpecies);
  if (!expectedBotanical) {
    return { verified: true, plantnetTop: '', confidence: 0, reason: 'no_botanical_name' };
  }

  // Build multipart form
  const blob = new Blob([imageBytes], { type: 'image/jpeg' });
  const formData = new FormData();
  formData.append('images', blob, 'photo.jpg');
  formData.append('organs', 'auto');

  try {
    _plantnetCalls++;
    const url = `${PLANTNET_URL}?api-key=${encodeURIComponent(key)}&lang=en&nb-results=3`;
    const resp = await fetch(url, {
      method: 'POST',
      body: formData,
      signal: AbortSignal.timeout(15000),
    });

    if (!resp.ok) {
      const text = await resp.text().catch(() => '');
      logger.warn(`PlantNet HTTP ${resp.status}: ${text.substring(0, 200)}`);
      return { verified: false, plantnetTop: '', confidence: 0, reason: `api_http_${resp.status}` };
    }

    const payload = await resp.json() as any;
    const results: any[] = payload?.results ?? [];

    if (results.length === 0) {
      return { verified: false, plantnetTop: '', confidence: 0, reason: 'no_plantnet_results' };
    }

    const topSpecies = results[0]?.species?.scientificNameWithoutAuthor ?? '';
    const topScore = results[0]?.score ?? 0;

    for (const match of results.slice(0, 3)) {
      const botanical: string = match?.species?.scientificNameWithoutAuthor ?? '';
      const score: number = match?.score ?? 0;

      if (botanicalMatch(botanical, expectedBotanical) && score >= CONFIDENCE_THRESHOLD) {
        return {
          verified: true,
          plantnetTop: botanical,
          confidence: score,
          reason: `match (${Math.round(score * 100)}%)`,
        };
      }
    }

    return {
      verified: false,
      plantnetTop: topSpecies,
      confidence: topScore,
      reason: `mismatch — PlantNet says ${topSpecies} (${Math.round(topScore * 100)}%), expected ${expectedBotanical}`,
    };
  } catch (err: any) {
    logger.warn(`PlantNet API error: ${err?.message ?? err}`);
    return { verified: false, plantnetTop: '', confidence: 0, reason: `api_error: ${err?.message}` };
  }
}

export function getPlantnetCallCount(): number {
  return _plantnetCalls;
}
