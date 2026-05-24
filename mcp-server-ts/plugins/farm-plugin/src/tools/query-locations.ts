import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { getFarmOSClient } from '../clients/index.js';

/**
 * Surface every land + structure asset, classified by level.
 *
 * Exists because `query_sections` filters to the section-name regex
 * (`P\dR\d\.\d+-\d+`), which silently hides row-level (P1R2) and
 * paddock-level (P1) assets — a 2026-05-24 diagnostic session almost
 * created duplicate row assets after `query_sections` returned 0 for
 * "P1R2". The data was there; the tool surface didn't enumerate it.
 *
 * Levels:
 *   - paddock:   /^P\d$/        (P1, P2, ...)
 *   - row:       /^P\dR\d$/     (P1R2, P2R5, ...)
 *   - section:   /^P\dR\d\.\d+-\d+$/  (P1R2.0-14, ...)
 *   - nursery:   name starts with NURS.
 *   - compost:   name starts with COMP.
 *   - structure: asset/structure (regardless of name)
 *   - other:     anything else on asset/land (dams, infrastructure, ...)
 */
export const queryLocationsTool: Tool = {
  namespace: 'fc',
  name: 'query_locations',
  title: 'List All Locations (Land + Structure Assets)',
  description: 'Enumerate ALL land + structure assets — paddocks, rows, sections, nursery, compost, structures, and other land — classified by level. Use this when query_sections returns nothing for what you think should be a row or paddock name; query_sections only matches section-shaped names (P1R2.0-14) and silently hides row-level (P1R2) and paddock-level (P1) assets.\n\nArgs:\n    name: Exact name match (e.g. "P1R2"). Optional.\n    name_prefix: Prefix match (e.g. "P1R" returns all P1 rows). Optional.\n    level: One of paddock | row | section | nursery | compost | structure | other | all (default all).\n    include_archived: Include archived assets (default false).\n\nReturns:\n    List of locations with name, uuid, level, asset_type, archived, parent_uuids.',
  paramsSchema: z.object({
    name: z.string().optional().describe('Exact name match (e.g. "P1R2")'),
    name_prefix: z.string().optional().describe('Prefix match (e.g. "P1R" returns all P1 rows)'),
    level: z.enum(['paddock', 'row', 'section', 'nursery', 'compost', 'structure', 'other', 'all'])
      .optional()
      .default('all')
      .describe('Filter by classification level'),
    include_archived: z.boolean().optional().default(false).describe('Include archived assets'),
  }).shape,
  options: { readOnlyHint: true },
  handler: async (params, extra) => {
    const client = getFarmOSClient(extra);
    const level = params.level ?? 'all';
    const includeArchived = params.include_archived ?? false;

    const all = await client.getLocations({ includeArchived });

    let filtered = all;
    if (level !== 'all') {
      filtered = filtered.filter((loc) => loc.level === level);
    }
    if (params.name) {
      filtered = filtered.filter((loc) => loc.name === params.name);
    }
    if (params.name_prefix) {
      filtered = filtered.filter((loc) => loc.name.startsWith(params.name_prefix!));
    }

    // Per-level count summary (always over the level-filtered set, not the
    // name-narrowed result — so callers can see "level=row returned 5, your
    // name filter narrowed it to 1").
    const byLevel: Record<string, number> = {};
    for (const loc of all) {
      byLevel[loc.level] = (byLevel[loc.level] ?? 0) + 1;
    }

    return {
      content: [{ type: 'text' as const, text: JSON.stringify({
        count: filtered.length,
        total: all.length,
        filters: {
          name: params.name ?? null,
          name_prefix: params.name_prefix ?? null,
          level,
          include_archived: includeArchived,
        },
        by_level: byLevel,
        locations: filtered,
      }, null, 2) }],
    };
  },
};
