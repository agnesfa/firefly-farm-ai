import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { getFarmOSClient } from '../clients/index.js';
import { parseDate, formatTimestamp } from '../helpers/index.js';

export const createActivityTool: Tool = {
  namespace: 'fc',
  name: 'create_activity',
  title: 'Create Activity',
  description: 'Log a field activity (watering, weeding, mulching, etc.) for a section.\n\nArgs:\n    section_id: Section where the activity happened (e.g., "P2R3.15-21").\n    activity_type: Type of activity (e.g., "watering", "weeding", "mulching", "pruning").\n    notes: Description of the activity.\n    date: Activity date in ISO format. Defaults to today.\n\nReturns:\n    Created log details or error message.',
  paramsSchema: z.object({
    section_id: z.string().describe('Section where the activity happened'),
    activity_type: z.string().describe('Type of activity'),
    notes: z.string().describe('Description of the activity'),
    date: z.string().optional().describe('Activity date in ISO format'),
  }).shape,
  options: { readOnlyHint: false },
  handler: async (params, extra) => {
    const client = getFarmOSClient(extra);
    const sectionUuid = await client.getSectionUuid(params.section_id);
    if (!sectionUuid) {
      return { content: [{ type: 'text' as const, text: JSON.stringify({ error: `Section '${params.section_id}' not found in farmOS` }) }] };
    }
    const locationType = await client.getSectionType(params.section_id);
    const timestamp = parseDate(params.date);
    const logName = `${params.activity_type.charAt(0).toUpperCase() + params.activity_type.slice(1)} — ${params.section_id}`;
    const logId = await client.createActivityLog(sectionUuid, timestamp, logName, params.notes, undefined, locationType);
    return {
      content: [{ type: 'text' as const, text: JSON.stringify({
        status: 'created', log_id: logId, log_name: logName,
        section: params.section_id, activity_type: params.activity_type,
        notes: params.notes, timestamp: formatTimestamp(timestamp),
      }, null, 2) }],
    };
  },
};
