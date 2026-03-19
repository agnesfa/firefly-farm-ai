import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { getFarmOSClient } from '../clients/index.js';
import { parseDate, formatTimestamp, formatPlantAsset } from '../helpers/index.js';

export const createObservationTool: Tool = {
  namespace: 'fc',
  name: 'create_observation',
  title: 'Create Observation',
  description: 'Create an observation log with inventory count for a plant asset.\n\nThis updates the plant\'s inventory count in farmOS and records the observation.\n\nArgs:\n    plant_name: Exact plant asset name (e.g., "25 APR 2025 - Pigeon Pea - P2R2.0-3").\n    count: New inventory count (number of living plants).\n    notes: Observation notes (e.g., "2 lost to frost, 3 healthy"). Optional.\n    date: Observation date in ISO format (e.g., "2026-03-09"). Defaults to today.\n\nReturns:\n    Created log details or error message.',
  paramsSchema: z.object({
    plant_name: z.string().describe('Exact plant asset name'),
    count: z.number().describe('New inventory count'),
    notes: z.string().default('').describe('Observation notes'),
    date: z.string().optional().describe('Observation date in ISO format'),
  }).shape,
  options: { readOnlyHint: false },
  handler: async (params, extra) => {
    const client = getFarmOSClient(extra);
    const assets = await client.fetchByName('asset/plant', params.plant_name);
    if (assets.length === 0) {
      return { content: [{ type: 'text' as const, text: JSON.stringify({ error: `Plant asset '${params.plant_name}' not found in farmOS` }) }] };
    }

    const plant = assets[0];
    const plantId = plant.id;
    const formatted = formatPlantAsset(plant);
    const sectionId = formatted.section;
    const sectionUuid = await client.getSectionUuid(sectionId);
    if (!sectionUuid) {
      return { content: [{ type: 'text' as const, text: JSON.stringify({ error: `Section '${sectionId}' not found in farmOS` }) }] };
    }

    const timestamp = parseDate(params.date);
    const obsDate = new Date((timestamp * 1000) + 10 * 60 * 60 * 1000);
    const dateStr = obsDate.toISOString().slice(0, 10);
    const logName = `Observation ${sectionId} — ${formatted.species} — ${dateStr}`;

    const existing = await client.logExists(logName, 'observation');
    if (existing) {
      return { content: [{ type: 'text' as const, text: JSON.stringify({ status: 'skipped', message: `Observation log '${logName}' already exists`, existing_log_id: existing }) }] };
    }

    const qtyId = await client.createQuantity(plantId, params.count, 'reset');
    const logId = await client.createObservationLog(plantId, sectionUuid, qtyId, timestamp, logName, params.notes);

    return {
      content: [{ type: 'text' as const, text: JSON.stringify({
        status: 'created', log_id: logId, log_name: logName,
        plant: params.plant_name, count: params.count, notes: params.notes,
        timestamp: formatTimestamp(timestamp),
      }, null, 2) }],
    };
  },
};
