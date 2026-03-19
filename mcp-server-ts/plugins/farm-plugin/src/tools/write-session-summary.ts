import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { getMemoryClient } from '../clients/index.js';

export const writeSessionSummaryTool: Tool = {
  namespace: 'fc',
  name: 'write_session_summary',
  title: 'Write Session Summary',
  description: 'Write a session summary to the shared Team Memory.\n\nCall this at the end of significant sessions to share what was discussed\nand decided with the rest of the team.\n\nArgs:\n    user: Who this summary is from (e.g., "Claire", "Agnes", "Olivier").\n    topics: Comma-separated topic keywords (e.g., "compost, P2R3, pigeon pea").\n    decisions: Key decisions made in this session.\n    farmos_changes: JSON string of farmOS changes made, e.g., \'[{"type":"observation","id":"uuid","name":"..."}]\'.\n    questions: Open questions or things to follow up on.\n    summary: Free-text session summary.\n    skip: If True, mark as private/skipped (not shared with team). Default False.',
  paramsSchema: z.object({
    user: z.string().describe('Who this summary is from'),
    topics: z.string().default('').describe('Comma-separated topic keywords'),
    decisions: z.string().default('').describe('Key decisions made'),
    farmos_changes: z.string().default('').describe('JSON string of farmOS changes'),
    questions: z.string().default('').describe('Open questions'),
    summary: z.string().default('').describe('Free-text session summary'),
    skip: z.boolean().default(false).describe('Mark as private/skipped'),
  }).shape,
  options: { readOnlyHint: false },
  handler: async (params) => {
    const memClient = getMemoryClient();
    if (!memClient) return { content: [{ type: 'text' as const, text: JSON.stringify({ error: 'MEMORY_ENDPOINT not configured' }) }] };
    try {
      const result = await memClient.writeSummary({
        user: params.user, topics: params.topics, decisions: params.decisions,
        farmos_changes: params.farmos_changes, questions: params.questions,
        summary: params.summary, skip: params.skip,
      });
      return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
    } catch (e: any) {
      return { content: [{ type: 'text' as const, text: JSON.stringify({ error: `Failed to write summary: ${e.message}` }) }] };
    }
  },
};
