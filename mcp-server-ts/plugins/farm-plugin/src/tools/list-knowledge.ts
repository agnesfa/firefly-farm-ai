import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { getKnowledgeClient } from '../clients/index.js';

export const listKnowledgeTool: Tool = {
  namespace: 'fc',
  name: 'list_knowledge',
  title: 'List Knowledge Base',
  description: 'List knowledge base entries, optionally filtered by category.\n\nUse this to browse the farm knowledge library or see what\'s available\nin a specific category.\n\nArgs:\n    category: Optional category filter (e.g., "syntropic", "composting").\n    limit: Max entries to return (default 20).\n    topics: Optional farm domain filter (e.g., "nursery", "compost").\n            Valid topics: nursery, compost, irrigation, syntropic, seeds,\n            harvest, paddock, equipment, cooking, infrastructure, camp.',
  paramsSchema: z.object({
    category: z.string().optional().describe('Optional category filter'),
    limit: z.number().default(20).describe('Max entries to return'),
    topics: z.string().optional().describe('Optional farm domain filter (e.g., "nursery", "compost")'),
  }).shape,
  options: { readOnlyHint: true },
  handler: async (params) => {
    const kbClient = getKnowledgeClient();
    if (!kbClient) return { content: [{ type: 'text' as const, text: JSON.stringify({ error: 'Knowledge base not available', hint: 'KNOWLEDGE_ENDPOINT not configured' }) }] };
    try {
      const result = await kbClient.listEntries(params.category, params.limit, 0, params.topics);
      return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
    } catch (e: any) {
      return { content: [{ type: 'text' as const, text: JSON.stringify({ error: `Failed to list knowledge entries: ${e.message}` }) }] };
    }
  },
};
