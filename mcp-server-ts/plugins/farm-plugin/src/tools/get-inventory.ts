import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { getFarmOSClient } from '../clients/index.js';
import { formatPlantAsset } from '../helpers/index.js';

export const getInventoryTool: Tool = {
  namespace: 'fc',
  name: 'get_inventory',
  title: 'Get Inventory',
  description: 'Get current inventory (plant counts) for a section or specific species.\n\nArgs:\n    section_id: Section to check inventory for (e.g., "P2R3.15-21"). Optional.\n    species: Species to check across all sections (e.g., "Pigeon Pea"). Optional.\n    section_prefix: Prefix to query all matching sections in one call (e.g., "NURS",\n        "P2R3", "COMP"). Fetches inventory for every section matching the prefix.\n        Mutually exclusive with section_id.\n    At least one of section_id, species, or section_prefix should be provided.\n\nReturns:\n    Plant inventory with current counts.',
  paramsSchema: z.object({
    section_id: z.string().optional().describe('Section to check inventory for'),
    species: z.string().optional().describe('Species to check across all sections'),
    section_prefix: z.string().optional().describe('Prefix to query all matching sections in one call (e.g., "NURS", "P2R3", "COMP"). Mutually exclusive with section_id.'),
  }).shape,
  options: { readOnlyHint: true },
  handler: async (params, extra) => {
    if (!params.section_id && !params.species && !params.section_prefix) {
      return { content: [{ type: 'text' as const, text: JSON.stringify({ error: 'Please provide section_id, species, section_prefix (or a combination)' }) }] };
    }
    const client = getFarmOSClient(extra);

    let formatted: any[];
    let queryInfo: any;

    // --- section_prefix mode: resolve prefix to section list, aggregate ---
    if (params.section_prefix) {
      const prefixUpper = params.section_prefix.toUpperCase();
      let sectionsList: string[];

      if (prefixUpper.startsWith('NURS')) {
        const locations = await client.getAllLocations('nursery');
        sectionsList = (locations.nursery ?? []).map((s: any) => s.name);
      } else if (prefixUpper.startsWith('COMP')) {
        const locations = await client.getAllLocations('compost');
        sectionsList = (locations.compost ?? []).map((s: any) => s.name);
      } else {
        // Paddock row prefix (e.g., "P2R3")
        const sections = await client.getSectionAssets(params.section_prefix);
        sectionsList = sections.map((s: any) => s.attributes?.name ?? '');
      }

      if (sectionsList.length === 0) {
        return { content: [{ type: 'text' as const, text: JSON.stringify({ error: `No sections found matching prefix '${params.section_prefix}'` }) }] };
      }

      // Fetch plants for each section and aggregate
      const allPlants: any[] = [];
      for (const secId of sectionsList.sort()) {
        const plants = await client.getPlantAssets(secId, params.species);
        allPlants.push(...plants);
      }

      formatted = allPlants.map(formatPlantAsset);
      queryInfo = { section_prefix: params.section_prefix } as any;
      if (params.species) queryInfo.species = params.species;
    } else {
      // --- original single-section / species mode ---
      const plants = await client.getPlantAssets(params.section_id, params.species);
      formatted = plants.map(formatPlantAsset);
      queryInfo = { section_id: params.section_id, species: params.species };
    }

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
      query: queryInfo,
      summary: { total_species_entries: inventoryItems.length, total_plant_count: totalPlantCount },
      plants: inventoryItems,
    };
    if (unknownCount > 0) result.summary.entries_without_count = unknownCount;
    // Add section breakdown for multi-section results
    if (Object.keys(sectionTotals).length > 1) {
      result.by_section = Object.values(sectionTotals).sort((a: any, b: any) => a.section.localeCompare(b.section));
    }
    return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
  },
};
