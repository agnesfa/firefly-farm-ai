import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { getFarmOSClient } from '../clients/index.js';
import { parseDate, buildAssetName, buildMcpStamp, appendStamp } from '../helpers/index.js';

export const createPlantTool: Tool = {
  namespace: 'fc',
  name: 'create_plant',
  title: 'Create Plant',
  description: 'Create a new plant asset in a section.\n\nCreates the plant asset, sets its location via an observation log,\nand records the initial inventory count.\n\nArgs:\n    species: Plant species farmos_name (e.g., "Pigeon Pea", "Tomato (Marmande)").\n            Must match an existing plant_type taxonomy term.\n    section_id: Section to place the plant (e.g., "P2R3.15-21").\n    count: Initial number of plants.\n    planted_date: Planting date in ISO format (e.g., "2026-03-09"). Defaults to today.\n    notes: Additional notes about the planting. Optional.\n\nReturns:\n    Created plant and log details.',
  paramsSchema: z.object({
    species: z.string().describe('Plant species farmos_name'),
    section_id: z.string().describe('Section to place the plant'),
    count: z.number().describe('Initial number of plants'),
    planted_date: z.string().optional().describe('Planting date in ISO format'),
    notes: z.string().default('').describe('Additional notes'),
  }).shape,
  options: { readOnlyHint: false },
  handler: async (params, extra) => {
    const client = getFarmOSClient(extra);
    const plantTypeUuid = await client.getPlantTypeUuid(params.species);
    if (!plantTypeUuid) {
      return { content: [{ type: 'text' as const, text: JSON.stringify({ error: `Plant type '${params.species}' not found in farmOS taxonomy.` }) }] };
    }
    const sectionUuid = await client.getSectionUuid(params.section_id);
    if (!sectionUuid) {
      return { content: [{ type: 'text' as const, text: JSON.stringify({ error: `Section '${params.section_id}' not found in farmOS` }) }] };
    }

    const dateStr = params.planted_date ?? new Date(Date.now() + 10 * 60 * 60 * 1000).toISOString().slice(0, 10);
    const assetName = buildAssetName(dateStr, params.species, params.section_id);

    const existing = await client.plantAssetExists(assetName);
    if (existing) {
      return { content: [{ type: 'text' as const, text: JSON.stringify({ status: 'skipped', message: `Plant asset '${assetName}' already exists`, existing_id: existing }) }] };
    }

    const stamp = buildMcpStamp('created', 'plant', { relatedEntities: [params.species, params.section_id] });
    const stampedNotes = appendStamp(params.notes ?? '', stamp);

    const plantId = await client.createPlantAsset(assetName, plantTypeUuid, stampedNotes);
    if (!plantId) {
      return { content: [{ type: 'text' as const, text: JSON.stringify({ error: 'Failed to create plant asset' }) }] };
    }

    const qtyId = await client.createQuantity(plantId, params.count, 'reset');
    const timestamp = parseDate(dateStr);
    const logName = `Inventory ${params.section_id} — ${params.species}`;
    const logId = await client.createObservationLog(plantId, sectionUuid, qtyId, timestamp, logName, stampedNotes);

    return {
      content: [{ type: 'text' as const, text: JSON.stringify({
        status: 'created',
        plant: { id: plantId, name: assetName, species: params.species, section: params.section_id, count: params.count },
        observation_log: { id: logId, name: logName },
        notes: params.notes,
      }, null, 2) }],
    };
  },
};
