import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { getKnowledgeClient } from '../clients/index.js';

export const updateKnowledgeTool: Tool = {
  namespace: 'fc',
  name: 'update_knowledge',
  title: 'Update Knowledge Entry',
  description: 'Update an existing knowledge base entry.\n\nOnly the fields you provide will be updated — others are preserved.\n\nArgs:\n    entry_id: The UUID of the entry to update (from search_knowledge or list_knowledge).\n    title: New title (optional).\n    content: New/updated content (optional).\n    category: New category (optional).\n    tags: New comma-separated tags (optional).\n    topics: New comma-separated farm domain topics (optional).\n            Valid topics: nursery, compost, irrigation, syntropic, seeds,\n            harvest, paddock, equipment, cooking, infrastructure, camp.\n    related_plants: New related plant types (optional).\n    related_sections: New related sections (optional).\n    media_links: New media links (optional).',
  paramsSchema: z.object({
    entry_id: z.string().describe('The UUID of the entry to update'),
    title: z.string().optional(), content: z.string().optional(),
    category: z.string().optional(), tags: z.string().optional(),
    topics: z.string().optional(), related_plants: z.string().optional(),
    related_sections: z.string().optional(), media_links: z.string().optional(),
  }).shape,
  options: { readOnlyHint: false },
  handler: async (params) => {
    const kbClient = getKnowledgeClient();
    if (!kbClient) return { content: [{ type: 'text' as const, text: JSON.stringify({ error: 'Knowledge base not available', hint: 'KNOWLEDGE_ENDPOINT not configured' }) }] };

    const fields: Record<string, string> = {};
    for (const [key, val] of Object.entries(params)) {
      if (key !== 'entry_id' && val != null) fields[key] = val as string;
    }
    if (Object.keys(fields).length === 0) return { content: [{ type: 'text' as const, text: JSON.stringify({ error: 'No fields to update' }) }] };

    try {
      const result = await kbClient.update(params.entry_id, fields);
      return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
    } catch (e: any) {
      return { content: [{ type: 'text' as const, text: JSON.stringify({ error: `Failed to update knowledge entry: ${e.message}` }) }] };
    }
  },
};
