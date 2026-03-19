import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { getObserveClient } from '../clients/index.js';

export const updateObservationStatusTool: Tool = {
  namespace: 'fc',
  name: 'update_observation_status',
  title: 'Update Observation Status',
  description: 'Update the review status of field observations.\n\nUse this after reviewing observations to mark them as reviewed, approved, or rejected.\n\nArgs:\n    submission_id: The submission ID to update (all rows with this ID).\n    new_status: New status: reviewed, approved, rejected, or imported.\n    reviewer: Name of the reviewer (e.g., "Claire", "Agnes", "James").\n    notes: Review notes. Optional.\n\nReturns:\n    Update confirmation with count of rows changed.',
  paramsSchema: z.object({
    submission_id: z.string().describe('The submission ID to update'),
    new_status: z.string().describe('New status: reviewed, approved, rejected, or imported'),
    reviewer: z.string().describe('Name of the reviewer'),
    notes: z.string().default('').describe('Review notes'),
  }).shape,
  options: { readOnlyHint: false },
  handler: async (params) => {
    const validStatuses = ['reviewed', 'approved', 'rejected', 'imported'];
    if (!validStatuses.includes(params.new_status)) {
      return { content: [{ type: 'text' as const, text: JSON.stringify({ error: `Invalid status '${params.new_status}'. Must be one of: ${validStatuses.join(', ')}` }) }] };
    }
    const obsClient = getObserveClient();
    if (!obsClient) return { content: [{ type: 'text' as const, text: JSON.stringify({ error: 'OBSERVE_ENDPOINT not configured' }) }] };

    const result = await obsClient.updateStatus([{
      submission_id: params.submission_id, status: params.new_status,
      reviewer: params.reviewer, notes: params.notes,
    }]);
    if (!result.success) return { content: [{ type: 'text' as const, text: JSON.stringify({ error: result.error ?? 'Failed to update status' }) }] };

    return {
      content: [{ type: 'text' as const, text: JSON.stringify({
        status: 'updated', submission_id: params.submission_id,
        new_status: params.new_status, reviewer: params.reviewer,
        notes: params.notes, rows_updated: result.updated ?? 0,
      }, null, 2) }],
    };
  },
};
