import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { getFarmOSClient } from '../clients/index.js';
import { parseDate, formatPlantAsset, buildMcpStamp, appendStamp } from '../helpers/index.js';

export const archivePlantTool: Tool = {
  namespace: 'fc',
  name: 'archive_plant',
  title: 'Archive Plant',
  description: 'Archive a plant asset in farmOS (mark as no longer active).\n\nUse this when a plant has died, been removed, or is no longer being tracked.\nOptionally records an activity log explaining why.\n\nArgs:\n    plant_name: Exact plant asset name (e.g., "25 APR 2025 - Pigeon Pea - P2R2.0-3")\n               or UUID.\n    reason: Why the plant is being archived (e.g., "Died from frost", "Removed during\n           renovation"). Optional — if provided, an activity log is created.\n\nReturns:\n    Confirmation with archived asset details, or error message.',
  paramsSchema: z.object({
    plant_name: z.string().describe('Exact plant asset name or UUID'),
    reason: z.string().default('').describe('Why the plant is being archived'),
  }).shape,
  options: { readOnlyHint: false },
  handler: async (params, extra) => {
    const client = getFarmOSClient(extra);
    let updated: any;
    try {
      updated = await client.archivePlant(params.plant_name);
    } catch (e: any) {
      return { content: [{ type: 'text' as const, text: JSON.stringify({ error: e.message }) }] };
    }

    const formatted = formatPlantAsset(updated);
    const result: any = {
      status: 'archived',
      plant: { id: updated.id ?? '', name: formatted.name ?? params.plant_name, species: formatted.species ?? '', section: formatted.section ?? '' },
    };

    if (params.reason) {
      const sectionId = formatted.section;
      const sectionUuid = sectionId ? await client.getSectionUuid(sectionId) : null;
      if (sectionUuid) {
        const stamp = buildMcpStamp('archived', 'plant', { relatedEntities: [params.plant_name] });
        const stampedReason = appendStamp(params.reason, stamp);
        const timestamp = parseDate(null);
        const logName = `Archived — ${formatted.species} — ${sectionId}`;
        const logId = await client.createActivityLog(sectionUuid, timestamp, logName, stampedReason, [updated.id ?? '']);
        result.activity_log = { id: logId, name: logName, reason: params.reason };
      }
    }

    return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
  },
};
