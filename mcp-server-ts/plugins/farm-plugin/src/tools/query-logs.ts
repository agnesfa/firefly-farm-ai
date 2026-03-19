import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { getFarmOSClient } from '../clients/index.js';
import { formatLog } from '../helpers/index.js';

export const queryLogsTool: Tool = {
  namespace: 'fc',
  name: 'query_logs',
  title: 'Search Logs',
  description: 'Search logs by type, section, or species.\n\nArgs:\n    log_type: Filter by log type: observation, activity, transplanting, harvest, seeding. Optional.\n    section_id: Filter by section ID in log name. Optional.\n    species: Filter by species name in log name. Optional.\n    max_results: Maximum number of results (default 20, max 50).\n\nReturns:\n    List of matching logs with name, type, timestamp, and notes.',
  paramsSchema: z.object({
    log_type: z.string().optional().describe('Filter by log type'),
    section_id: z.string().optional().describe('Filter by section ID in log name'),
    species: z.string().optional().describe('Filter by species name in log name'),
    max_results: z.number().default(20).describe('Maximum number of results'),
  }).shape,
  options: { readOnlyHint: true },
  handler: async (params, extra) => {
    const client = getFarmOSClient(extra);
    const maxResults = Math.min(params.max_results ?? 20, 50);
    const logs = await client.getLogs(params.log_type, params.section_id, params.species, maxResults);
    const formatted = logs.map(formatLog);
    return {
      content: [{ type: 'text' as const, text: JSON.stringify({
        count: formatted.length,
        filters: { log_type: params.log_type, section_id: params.section_id, species: params.species },
        logs: formatted,
      }, null, 2) }],
    };
  },
};
