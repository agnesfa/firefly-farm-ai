import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { getMemoryClient } from '../clients/index.js';

export const acknowledgeMemoryTool: Tool = {
  namespace: 'fc',
  name: 'acknowledge_memory',
  title: 'Acknowledge Memory',
  description: 'Mark a team memory entry as acknowledged (read and processed).\n\nCall this after reading and acting on a team memory entry so it won\'t\nappear again in fresh-only queries for this user.\n\nArgs:\n    summary_id: The summary/entry ID to acknowledge.\n    user: Who is acknowledging (e.g., "Claire", "Agnes", "James").',
  paramsSchema: z.object({
    summary_id: z.string().describe('The summary/entry ID to acknowledge'),
    user: z.string().describe('Who is acknowledging'),
  }).shape,
  options: { readOnlyHint: false },
  handler: async (params) => {
    const memClient = getMemoryClient();
    if (!memClient) return { content: [{ type: 'text' as const, text: JSON.stringify({ error: 'MEMORY_ENDPOINT not configured' }) }] };
    try {
      const result = await memClient.acknowledgeMemory(params.summary_id, params.user);
      return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
    } catch (e: any) {
      return { content: [{ type: 'text' as const, text: JSON.stringify({ error: `Failed to acknowledge memory: ${e.message}` }) }] };
    }
  },
};
