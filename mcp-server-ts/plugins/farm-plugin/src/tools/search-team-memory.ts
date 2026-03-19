import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { getMemoryClient } from '../clients/index.js';

export const searchTeamMemoryTool: Tool = {
  namespace: 'fc',
  name: 'search_team_memory',
  title: 'Search Team Memory',
  description: 'Search team memory for matching session summaries.\n\nSearches across topics, decisions, questions, and summary text.\n\nArgs:\n    query: Text to search for (e.g., "compost", "pigeon pea", "nursery").\n    days: How many days back to search (default 30).',
  paramsSchema: z.object({
    query: z.string().describe('Text to search for'),
    days: z.number().default(30).describe('How many days back to search'),
  }).shape,
  options: { readOnlyHint: true },
  handler: async (params) => {
    const memClient = getMemoryClient();
    if (!memClient) return { content: [{ type: 'text' as const, text: JSON.stringify({ error: 'MEMORY_ENDPOINT not configured' }) }] };
    try {
      const result = await memClient.searchMemory(params.query, params.days);
      return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
    } catch (e: any) {
      return { content: [{ type: 'text' as const, text: JSON.stringify({ error: `Failed to search team memory: ${e.message}` }) }] };
    }
  },
};
