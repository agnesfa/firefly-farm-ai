/**
 * farmOS response formatters — clean output for tool responses.
 */

import { formatTimestamp } from './dates.js';
import { parseAssetName } from './names.js';

/** Extract notes from farmOS notes field (can be string or {value: string}). */
function extractNotes(notesRaw: unknown): string {
  if (!notesRaw) return '';
  if (typeof notesRaw === 'string') return notesRaw;
  if (typeof notesRaw === 'object' && notesRaw !== null) {
    return (notesRaw as Record<string, string>).value ?? '';
  }
  return '';
}

/** Extract IDs from a farmOS relationship data array. */
function extractRelIds(rels: Record<string, any>, key: string): string[] {
  const data = rels?.[key]?.data;
  if (!Array.isArray(data)) return [];
  return data.map((item: any) => item?.id ?? '').filter(Boolean);
}

/**
 * Format a raw farmOS plant asset for clean tool output.
 */
export function formatPlantAsset(asset: Record<string, any>): Record<string, any> {
  const attrs = asset.attributes ?? {};
  const rels = asset.relationships ?? {};

  const plantTypeIds = extractRelIds(rels, 'plant_type');
  const parsed = parseAssetName(attrs.name ?? '');

  const notes = extractNotes(attrs.notes);

  // Extract computed inventory count
  const inventoryData: any[] = attrs.inventory ?? [];
  let inventoryCount: number | null = null;
  if (inventoryData.length > 0) {
    for (const inv of inventoryData) {
      if (inv.measure === 'count') {
        const val = parseFloat(inv.value);
        if (!isNaN(val)) inventoryCount = Math.floor(val);
        break;
      }
    }
    if (inventoryCount === null) {
      const val = parseFloat(inventoryData[0]?.value);
      if (!isNaN(val)) inventoryCount = Math.floor(val);
    }
  }

  const result: Record<string, any> = {
    id: asset.id ?? '',
    name: attrs.name ?? '',
    species: parsed.species,
    section: parsed.section,
    planted_date: parsed.plantedDate,
    status: attrs.status ?? '',
    notes,
    plant_type_ids: plantTypeIds,
  };
  if (inventoryCount !== null) {
    result.inventory_count = inventoryCount;
  }
  return result;
}

/**
 * Format a raw farmOS log for clean tool output.
 */
export function formatLog(log: Record<string, any>): Record<string, any> {
  const attrs = log.attributes ?? {};
  const rels = log.relationships ?? {};

  const notes = extractNotes(attrs.notes);
  const logType = (log.type ?? '').replace('log--', '');
  const assetIds = extractRelIds(rels, 'asset');
  const locationIds = extractRelIds(rels, 'location');

  // Extract quantities (merged by client as _quantities)
  const quantities: any[] = [];
  for (const q of (log._quantities ?? [])) {
    const qAttrs = q.attributes ?? {};
    const valueRaw = qAttrs.value;
    let val: number | null = null;
    if (typeof valueRaw === 'object' && valueRaw !== null) {
      const dec = valueRaw.decimal ?? valueRaw.numerator;
      if (dec != null) val = Math.floor(parseFloat(dec));
    } else if (valueRaw != null) {
      const parsed = parseFloat(valueRaw);
      if (!isNaN(parsed)) val = Math.floor(parsed);
    }
    quantities.push({
      value: val,
      measure: qAttrs.measure ?? '',
      inventory_adjustment: qAttrs.inventory_adjustment ?? '',
      label: qAttrs.label ?? '',
    });
  }

  const result: Record<string, any> = {
    id: log.id ?? '',
    name: attrs.name ?? '',
    type: logType,
    timestamp: formatTimestamp(attrs.timestamp),
    status: attrs.status ?? '',
    is_movement: attrs.is_movement ?? false,
    notes,
    asset_ids: assetIds,
    location_ids: locationIds,
  };
  if (quantities.length > 0) {
    result.quantity = quantities;
  }
  return result;
}

/**
 * Format a raw farmOS plant_type taxonomy term with syntropic metadata.
 */
export function formatPlantType(term: Record<string, any>): Record<string, any> {
  const attrs = term.attributes ?? {};

  const descRaw = attrs.description;
  let description = '';
  if (typeof descRaw === 'string') {
    description = descRaw;
  } else if (typeof descRaw === 'object' && descRaw !== null) {
    description = descRaw.value ?? '';
  }

  // Extract syntropic metadata from description
  const metadata: Record<string, string> = {};
  if (description.includes('Syntropic Agriculture Data')) {
    for (const line of description.split('\n')) {
      const clean = line.trim().replace(/\*\*/g, '');
      if (clean.startsWith('Botanical Name:')) metadata.botanical_name = clean.split(':', 2)[1].trim();
      else if (clean.startsWith('Strata:')) metadata.strata = clean.split(':', 2)[1].trim();
      else if (clean.startsWith('Succession Stage:')) metadata.succession_stage = clean.split(':', 2)[1].trim();
      else if (clean.startsWith('Functions:')) metadata.functions = clean.split(':', 2)[1].trim();
      else if (clean.startsWith('Family:')) metadata.family = clean.split(':', 2)[1].trim();
      else if (clean.startsWith('Lifespan:')) metadata.lifespan = clean.split(':', 2)[1].trim();
      else if (clean.startsWith('Life Cycle:')) metadata.lifecycle = clean.split(':', 2)[1].trim();
      else if (clean.startsWith('Source:')) metadata.source = clean.split(':', 2)[1].trim();
    }
  }

  return {
    id: term.id ?? '',
    name: attrs.name ?? '',
    maturity_days: attrs.maturity_days ?? null,
    transplant_days: attrs.transplant_days ?? null,
    ...metadata,
  };
}

/**
 * Trim KB entries to summary: entry_id, title, category, topics, tags, author, content preview.
 */
export function summarizeKbEntries(entries: Record<string, any>[]): Record<string, any>[] {
  const summaryKeys = ['entry_id', 'title', 'category', 'topics', 'tags', 'author'];
  return entries.map((entry) => {
    const item: Record<string, any> = {};
    for (const key of summaryKeys) {
      item[key] = entry[key] ?? '';
    }
    const content = entry.content ?? '';
    item.content_preview = content.length > 100 ? content.slice(0, 100) + '...' : content;
    return item;
  });
}

/**
 * Build a section summary from a land asset and its associated plant assets.
 */
export function formatSectionFromAssets(
  sectionAsset: Record<string, any>,
  plantAssets: Record<string, any>[],
): Record<string, any> {
  const attrs = sectionAsset.attributes ?? {};
  const plants = plantAssets.map((plant) => {
    const formatted = formatPlantAsset(plant);
    return {
      species: formatted.species,
      planted_date: formatted.planted_date,
      status: formatted.status,
      notes: formatted.notes,
    };
  });

  return {
    id: attrs.name ?? '',
    uuid: sectionAsset.id ?? '',
    status: attrs.status ?? '',
    plant_count: plants.length,
    plants,
  };
}
