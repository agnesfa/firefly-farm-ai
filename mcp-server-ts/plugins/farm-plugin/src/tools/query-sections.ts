import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { getFarmOSClient } from '../clients/index.js';

export const querySectionsTool: Tool = {
  namespace: 'fc',
  name: 'query_sections',
  title: 'List Sections',
  description: 'List sections with optional row filter.\n\nArgs:\n    row: Filter by row prefix (e.g., "P2R1", "P2R3"). Optional.\n         Also supports "NURS" for nursery locations and "COMP" for compost locations.\n         When omitted, returns ALL location types (paddock, nursery, compost).\n\nReturns:\n    List of section IDs grouped by row with plant counts.',
  paramsSchema: z.object({
    row: z.string().optional().describe('Filter by row prefix (e.g., "P2R1", "P2R3"). Also supports "NURS" for nursery, "COMP" for compost. Omit for all locations.'),
  }).shape,
  options: { readOnlyHint: true },
  handler: async (params, extra) => {
    const client = getFarmOSClient(extra);
    const row = params.row;

    let sectionsList: Array<{ name: string; uuid: string }>;

    if (row && row.toUpperCase().startsWith('NURS')) {
      const locations = await client.getAllLocations('nursery');
      sectionsList = (locations.nursery ?? []).map((s: any) => ({ name: s.name, uuid: s.uuid }));
    } else if (row && row.toUpperCase().startsWith('COMP')) {
      const locations = await client.getAllLocations('compost');
      sectionsList = (locations.compost ?? []).map((s: any) => ({ name: s.name, uuid: s.uuid }));
    } else if (!row) {
      // Return ALL location types: paddock sections + nursery + compost
      const allLocations = await client.getAllLocations();
      sectionsList = [
        ...(allLocations.paddock ?? []).map((s: any) => ({ name: s.name, uuid: s.uuid })),
        ...(allLocations.nursery ?? []).map((s: any) => ({ name: s.name, uuid: s.uuid })),
        ...(allLocations.compost ?? []).map((s: any) => ({ name: s.name, uuid: s.uuid })),
      ];
    } else {
      const sections = await client.getSectionAssets(row);
      sectionsList = sections.map((s: any) => ({ name: s.attributes?.name ?? '', uuid: s.id }));
    }

    // Fetch ALL plant assets once for count index
    const allPlants = await client.fetchAllPaginated('asset/plant', client.assetStatusFilter('active'));
    const plantCounts: Record<string, number> = {};
    for (const p of allPlants) {
      const pname = p.attributes?.name ?? '';
      const parts = pname.split(' - ');
      if (parts.length >= 2) {
        const sec = parts[parts.length - 1];
        plantCounts[sec] = (plantCounts[sec] ?? 0) + 1;
      }
    }

    const results = sectionsList
      .map((s) => ({ section_id: s.name, uuid: s.uuid, plant_count: plantCounts[s.name] ?? 0 }))
      .sort((a, b) => a.section_id.localeCompare(b.section_id));

    // Group by prefix
    const rows: Record<string, any[]> = {};
    for (const r of results) {
      const prefix = r.section_id.split('.')[0];
      if (!rows[prefix]) rows[prefix] = [];
      rows[prefix].push(r);
    }

    return {
      content: [{ type: 'text' as const, text: JSON.stringify({
        total_sections: results.length,
        filter: { row },
        rows,
      }, null, 2) }],
    };
  },
};
