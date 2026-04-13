import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { getFarmOSClient } from '../clients/index.js';
import { parseDate, formatTimestamp, buildMcpStamp, appendStamp } from '../helpers/index.js';

export const createActivityTool: Tool = {
  namespace: 'fc',
  name: 'create_activity',
  title: 'Create Activity',
  description: 'Log a field activity (watering, weeding, mulching, etc.) for a section.\n\nArgs:\n    section_id: Section where the activity happened (e.g., "P2R3.15-21").\n    activity_type: Type of activity (e.g., "watering", "weeding", "mulching", "pruning").\n    notes: Description of the activity.\n    date: Activity date in ISO format. Defaults to today.\n    status: Log status — "done" (completed activity) or "pending" (action needed/TODO).\n\nReturns:\n    Created log details or error message.',
  paramsSchema: z.object({
    section_id: z.string().describe('Section where the activity happened'),
    activity_type: z.string().describe('Type of activity'),
    notes: z.string().describe('Description of the activity'),
    date: z.string().optional().describe('Activity date in ISO format'),
    status: z.enum(['done', 'pending']).optional().describe('Log status — "done" (default) or "pending" (TODO/action needed)'),
  }).shape,
  options: { readOnlyHint: false },
  handler: async (params, extra) => {
    const client = getFarmOSClient(extra);
    const sectionUuid = await client.getSectionUuid(params.section_id);
    if (!sectionUuid) {
      return { content: [{ type: 'text' as const, text: JSON.stringify({ error: `Section '${params.section_id}' not found in farmOS` }) }] };
    }
    const locationType = await client.getSectionType(params.section_id);
    const logStatus = params.status || 'done';
    const timestamp = parseDate(params.date);
    const logName = `${params.activity_type.charAt(0).toUpperCase() + params.activity_type.slice(1)} — ${params.section_id}`;
    const stamp = buildMcpStamp('created', 'activity', { relatedEntities: [params.section_id] });
    const stampedNotes = appendStamp(params.notes, stamp);
    const logId = await client.createActivityLog(sectionUuid, timestamp, logName, stampedNotes, undefined, locationType, logStatus);
    return {
      content: [{ type: 'text' as const, text: JSON.stringify({
        status: 'created', log_id: logId, log_name: logName,
        section: params.section_id, activity_type: params.activity_type,
        notes: params.notes, log_status: logStatus,
        timestamp: formatTimestamp(timestamp),
      }, null, 2) }],
    };
  },
};
