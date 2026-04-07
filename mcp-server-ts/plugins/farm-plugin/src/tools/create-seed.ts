import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { getFarmOSClient } from '../clients/index.js';
import { parseDate } from '../helpers/index.js';

export const createSeedTool: Tool = {
  namespace: 'fc',
  name: 'create_seed',
  title: 'Create Seed',
  description: `Create or restock a seed asset in the seed bank.

Creates a farmOS seed asset, sets initial inventory, and records location
in NURS.FRDG (seed bank fridge). If the seed asset already exists, adds
stock via an inventory increment log.

Three acquisition pathways are supported:
- commercial: purchased from a nursery or supplier
- harvest: saved from farm harvest
- exchange: received from another farm (non-commercial)

Args:
    species: Plant species farmos_name (must match plant_type taxonomy).
    quantity_grams: Initial weight in grams (for bulk seeds).
    stock_level: For sachet seeds: "full", "half", or "empty".
    source: Where seeds came from (e.g., "Down Under Ag", "Farm harvest P2R3").
    source_type: One of "commercial", "harvest", "exchange". Default "commercial".
    notes: Free text (composition, invoice refs, harvest context).
    date: Acquisition date in ISO format. Defaults to today.`,
  paramsSchema: z.object({
    species: z.string().describe('Plant species farmos_name'),
    quantity_grams: z.number().optional().describe('Initial weight in grams'),
    stock_level: z.string().optional().describe('For sachet seeds: "full", "half", or "empty"'),
    source: z.string().optional().describe('Supplier or origin'),
    source_type: z.string().optional().describe('"commercial", "harvest", or "exchange"'),
    notes: z.string().default('').describe('Additional notes'),
    date: z.string().optional().describe('Acquisition date in ISO format'),
  }).shape,
  options: { readOnlyHint: false },

  handler: async (params, extra) => {
    const client = getFarmOSClient(extra);

    // Validate species exists in plant_type taxonomy
    const plantTypeUuid = await client.getPlantTypeUuid(params.species);
    if (!plantTypeUuid) {
      return { content: [{ type: 'text' as const, text: JSON.stringify({ error: `Plant type '${params.species}' not found in farmOS taxonomy.` }) }] };
    }

    // Validate quantity params
    if (!params.quantity_grams && !params.stock_level) {
      return { content: [{ type: 'text' as const, text: JSON.stringify({ error: 'Provide either quantity_grams or stock_level.' }) }] };
    }

    const seedName = `${params.species} Seeds`;
    const dateStr = params.date ?? new Date(Date.now() + 10 * 60 * 60 * 1000).toISOString().slice(0, 10);
    const timestamp = parseDate(dateStr);
    const sourceType = params.source_type ?? 'commercial';

    // Build notes with source metadata
    const noteParts: string[] = [];
    if (params.source) noteParts.push(`Source: ${params.source} (${sourceType})`);
    if (params.notes) noteParts.push(params.notes);
    const fullNotes = noteParts.join('. ');

    // Check if seed asset already exists
    const existingId = await client.seedAssetExists(seedName);

    let seedId: string;
    let status: string;

    if (existingId) {
      // Restock existing seed
      seedId = existingId;
      status = 'restocked';
    } else {
      // Create new seed asset
      const newId = await client.createSeedAsset(seedName, plantTypeUuid, fullNotes);
      if (!newId) {
        return { content: [{ type: 'text' as const, text: JSON.stringify({ error: 'Failed to create seed asset in farmOS.' }) }] };
      }
      seedId = newId;
      status = 'created';
    }

    // Create inventory quantity
    let qtyId: string | null = null;
    if (params.quantity_grams) {
      const adjustment = existingId ? 'increment' : 'reset';
      qtyId = await client.createSeedQuantity(seedId, params.quantity_grams, 'grams', adjustment);
    } else if (params.stock_level) {
      const levelMap: Record<string, number> = { full: 1, half: 0.5, empty: 0 };
      const value = levelMap[params.stock_level.toLowerCase()] ?? 1;
      qtyId = await client.createSeedQuantity(seedId, value, 'stock_level', 'reset');
    }

    // Create observation log (movement to NURS.FRDG + inventory)
    const qtyLabel = params.quantity_grams ? `${params.quantity_grams}g` : (params.stock_level ?? '');
    const logName = `Seedbank ${existingId ? 'restock' : 'addition'} — ${seedName}${qtyLabel ? ` — ${qtyLabel}` : ''}`;
    const logId = await client.createSeedObservationLog(seedId, qtyId, timestamp, logName, fullNotes);

    return {
      content: [{ type: 'text' as const, text: JSON.stringify({
        status,
        seed: { id: seedId, name: seedName, species: params.species },
        inventory: params.quantity_grams
          ? { quantity_grams: params.quantity_grams, adjustment: existingId ? 'increment' : 'reset' }
          : { stock_level: params.stock_level },
        source: params.source ?? null,
        source_type: sourceType,
        observation_log: { id: logId, name: logName },
      }, null, 2) }],
    };
  },
};
