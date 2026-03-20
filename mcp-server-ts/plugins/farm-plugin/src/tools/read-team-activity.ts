import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { getMemoryClient } from '../clients/index.js';

export const readTeamActivityTool: Tool = {
  namespace: 'fc',
  name: 'read_team_activity',
  title: 'Read Team Activity',
  description: 'Read recent team session summaries from shared memory.\n\nCall this at the start of sessions to see what the team has been doing.\n\nArgs:\n    days: How many days back to look (default 7).\n    user: Filter by team member name (optional).\n    limit: Max results to return (default 20).\n    only_fresh_for: If set, exclude entries already acknowledged by this\n        user. Use at session start to see only new updates (e.g., "Claire").',
  paramsSchema: z.object({
    days: z.number().default(7).describe('How many days back to look'),
    user: z.string().optional().describe('Filter by team member name'),
    limit: z.number().default(20).describe('Max results to return'),
    only_fresh_for: z.string().optional().describe('Exclude entries already acknowledged by this user'),
  }).shape,
  options: { readOnlyHint: true },
  handler: async (params) => {
    const memClient = getMemoryClient();
    if (!memClient) return { content: [{ type: 'text' as const, text: JSON.stringify({ error: 'MEMORY_ENDPOINT not configured' }) }] };
    try {
      const result = await memClient.readActivity(params.days, params.user, params.limit, params.only_fresh_for);
      return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
    } catch (e: any) {
      return { content: [{ type: 'text' as const, text: JSON.stringify({ error: `Failed to read team activity: ${e.message}` }) }] };
    }
  },
};
