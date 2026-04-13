import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { getKnowledgeClient } from '../clients/index.js';
import { buildMcpStamp, appendStamp } from '../helpers/index.js';

export const addKnowledgeTool: Tool = {
  namespace: 'fc',
  name: 'add_knowledge',
  title: 'Add Knowledge Entry',
  description: 'Add a new entry to the farm knowledge base.\n\nUse this to document farming practices, field learnings, tutorials,\ncomposting methods, pest solutions, or any knowledge that should be\npreserved and shared with the team and future workers.\n\nArgs:\n    title: Article/guide title (e.g., "Pigeon Pea Chop-and-Drop Technique").\n    content: Full text content of the knowledge entry.\n    category: Category tag — one of: syntropic, composting, irrigation,\n              nursery, pests, harvest, equipment, general.\n    author: Who wrote/contributed this (e.g., "Claire", "Olivier").\n    tags: Comma-separated search tags (e.g., "nitrogen_fixer,biomass,pioneer").\n    source_type: Type of entry — tutorial, sop, guide, observation, recipe, reference, source-material.\n    related_plants: Comma-separated farmos_names of related plant types\n                    (e.g., "Pigeon Pea,Comfrey,Sweet Potato").\n    related_sections: Comma-separated section IDs (e.g., "P2R3.15-21,P2R4.20-30").\n    media_links: Comma-separated Google Drive file IDs or URLs for\n                 photos, PDFs, or audio files related to this entry.\n    topics: Comma-separated farm domain topics (e.g., "nursery,propagation").\n            Valid topics: nursery, compost, irrigation, syntropic, seeds,\n            harvest, paddock, equipment, cooking, infrastructure, camp.',
  paramsSchema: z.object({
    title: z.string().describe('Article/guide title'),
    content: z.string().describe('Full text content'),
    category: z.string().describe('Category tag'),
    author: z.string().default('').describe('Who wrote this'),
    tags: z.string().default('').describe('Comma-separated search tags'),
    source_type: z.string().default('guide').describe('Type of entry'),
    related_plants: z.string().default('').describe('Comma-separated farmos_names'),
    related_sections: z.string().default('').describe('Comma-separated section IDs'),
    media_links: z.string().default('').describe('Comma-separated Drive file IDs or URLs'),
    topics: z.string().default('').describe('Comma-separated farm domain topics'),
  }).shape,
  options: { readOnlyHint: false },
  handler: async (params) => {
    const kbClient = getKnowledgeClient();
    if (!kbClient) return { content: [{ type: 'text' as const, text: JSON.stringify({ error: 'Knowledge base not available', hint: 'KNOWLEDGE_ENDPOINT not configured' }) }] };
    try {
      const stamp = buildMcpStamp('created', 'knowledge', { initiator: params.author || undefined, executor: 'apps_script', relatedEntities: params.title ? [params.title] : undefined });
      const stampedContent = appendStamp(params.content, stamp);
      const result = await kbClient.add({ ...params, content: stampedContent });
      return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
    } catch (e: any) {
      return { content: [{ type: 'text' as const, text: JSON.stringify({ error: `Failed to add knowledge entry: ${e.message}` }) }] };
    }
  },
};
