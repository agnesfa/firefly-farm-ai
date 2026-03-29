import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { getKnowledgeClient } from '../clients/index.js';
import { summarizeKbEntries } from '../helpers/formatters.js';

export const searchKnowledgeTool: Tool = {
  namespace: 'fc',
  name: 'search_knowledge',
  title: 'Search Knowledge Base',
  description: 'Search the farm knowledge base for articles, tutorials, guides, and SOPs.\n\nSearches across titles, content, tags, related plants, and authors.\nUse this to find farm practices, syntropic agriculture guides, composting\nmethods, pest management strategies, or any documented farm knowledge.\n\nArgs:\n    query: Text to search for (e.g., "pigeon pea", "frost damage", "composting").\n    category: Optional category filter (e.g., "syntropic", "composting",\n              "irrigation", "nursery", "pests", "harvest", "equipment", "general").\n    topics: Optional farm domain filter (e.g., "nursery", "compost", "syntropic").\n            Valid topics: nursery, compost, irrigation, syntropic, seeds,\n            harvest, paddock, equipment, cooking, infrastructure, camp.\n    summary_only: If true, return only entry_id, title, category, topics, tags,\n                  author, and first 100 chars of content. Default false.',
  paramsSchema: z.object({
    query: z.string().describe('Text to search for'),
    category: z.string().optional().describe('Optional category filter'),
    topics: z.string().optional().describe('Optional farm domain filter (e.g., "nursery", "compost")'),
    summary_only: z.boolean().default(false).describe('If true, return summary only (no full content)'),
  }).shape,
  options: { readOnlyHint: true },
  handler: async (params) => {
    const kbClient = getKnowledgeClient();
    if (!kbClient) return { content: [{ type: 'text' as const, text: JSON.stringify({ error: 'Knowledge base not available', hint: 'KNOWLEDGE_ENDPOINT not configured' }) }] };
    try {
      const result = await kbClient.search(params.query, params.category, params.topics);
      if (params.summary_only && result.results) {
        result.results = summarizeKbEntries(result.results);
      }
      return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
    } catch (e: any) {
      return { content: [{ type: 'text' as const, text: JSON.stringify({ error: `Knowledge search failed: ${e.message}` }) }] };
    }
  },
};
