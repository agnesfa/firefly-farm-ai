import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { createObservationTool } from './create-observation.js';
import { buildMcpStamp, appendStamp } from '../helpers/index.js';

export const updateInventoryTool: Tool = {
  namespace: 'fc',
  name: 'update_inventory',
  title: 'Update Inventory',
  description: 'Reset the inventory count for a plant asset.\n\nCreates a new observation log with the updated count.\n\nArgs:\n    plant_name: Exact plant asset name (e.g., "25 APR 2025 - Pigeon Pea - P2R2.0-3").\n    new_count: New inventory count.\n    notes: Reason for the update. Optional.\n\nReturns:\n    Updated inventory details.',
  paramsSchema: z.object({
    plant_name: z.string().describe('Exact plant asset name'),
    new_count: z.number().describe('New inventory count'),
    notes: z.string().default('').describe('Reason for the update'),
  }).shape,
  options: { readOnlyHint: false },
  handler: async (params, extra) => {
    const today = new Date(Date.now() + 10 * 60 * 60 * 1000).toISOString().slice(0, 10);
    const stamp = buildMcpStamp('updated', 'observation', { relatedEntities: [params.plant_name] });
    const rawNotes = params.notes ? `Inventory update: ${params.notes}` : 'Inventory update';
    const updateNotes = appendStamp(rawNotes, stamp);
    return createObservationTool.handler(
      { plant_name: params.plant_name, count: params.new_count, notes: updateNotes, date: today },
      extra,
    );
  },
};
