import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { getFarmOSClient } from '../clients/index.js';
import { formatPlantAsset } from '../helpers/index.js';

export const getInventoryTool: Tool = {
  namespace: 'fc',
  name: 'get_inventory',
  title: 'Get Inventory',
  description: 'Get current inventory (plant counts) for a section or specific species.\n\nArgs:\n    section_id: Section to check inventory for (e.g., "P2R3.15-21"). Optional.\n    species: Species to check across all sections (e.g., "Pigeon Pea"). Optional.\n    At least one of section_id or species should be provided.\n\nReturns:\n    Plant inventory with current counts.',
  paramsSchema: z.object({
    section_id: z.string().optional().describe('Section to check inventory for'),
    species: z.string().optional().describe('Species to check across all sections'),
  }).shape,
  options: { readOnlyHint: true },
  handler: async (params, extra) => {
    if (!params.section_id && !params.species) {
      return { content: [{ type: 'text' as const, text: JSON.stringify({ error: 'Please provide section_id or species (or both)' }) }] };
    }
    const client = getFarmOSClient(extra);
    const plants = await client.getPlantAssets(params.section_id, params.species);
    const formatted = plants.map(formatPlantAsset);

    let totalPlantCount = 0;
    let unknownCount = 0;
    const inventoryItems: any[] = [];
    const sectionTotals: Record<string, any> = {};

    for (const p of formatted) {
      const count = p.inventory_count;
      const item: any = { name: p.name, species: p.species, section: p.section, inventory_count: count ?? 'unknown', status: p.status };
      if (p.notes) item.notes = p.notes;
      inventoryItems.push(item);

      if (count != null) totalPlantCount += count;
      else unknownCount++;

      const sec = p.section;
      if (!sectionTotals[sec]) sectionTotals[sec] = { section: sec, species_count: 0, plant_count: 0 };
      sectionTotals[sec].species_count++;
      if (typeof count === 'number') sectionTotals[sec].plant_count += count;
    }

    const result: any = {
      query: { section_id: params.section_id, species: params.species },
      summary: { total_species_entries: inventoryItems.length, total_plant_count: totalPlantCount },
      plants: inventoryItems,
    };
    if (unknownCount > 0) result.summary.entries_without_count = unknownCount;
    if (params.species && !params.section_id && Object.keys(sectionTotals).length > 1) {
      result.by_section = Object.values(sectionTotals).sort((a: any, b: any) => a.section.localeCompare(b.section));
    }
    return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
  },
};
