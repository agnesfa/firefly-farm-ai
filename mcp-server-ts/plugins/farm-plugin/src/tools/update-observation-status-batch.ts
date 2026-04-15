import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { getObserveClient } from '../clients/index.js';

/**
 * Batch version of update_observation_status. Updates N submissions in
 * a single Apps Script call instead of N calls — the underlying endpoint
 * already accepts a list, so this collapses to one round trip.
 *
 * Reduces tool-call overhead on multi-submission flows by ~N×. The
 * classic trigger was Leah's April 14 walk: 15 submissions × 2 status
 * flips × tool-call overhead. With this tool, that's 1 call instead of
 * 15. Same for import_observations_batch (see neighbouring file).
 */
export const updateObservationStatusBatchTool: Tool = {
  namespace: 'fc',
  name: 'update_observation_status_batch',
  title: 'Update Observation Status (batch)',
  description: 'Batch version of update_observation_status. Updates the review status of many submissions in one Apps Script call.\n\nUse this when you need to flip more than 2-3 submissions at once — e.g. marking all of a walker\'s observations as approved before running import_observations_batch.\n\nArgs:\n    submission_ids: Array of submission IDs to update.\n    new_status: New status (applied to all): reviewed, approved, rejected, or imported.\n    reviewer: Name of the reviewer.\n    notes: Review notes applied to all entries. Optional.\n\nReturns:\n    Batch update summary with per-submission outcome and the total row count.',
  paramsSchema: z.object({
    submission_ids: z.array(z.string()).min(1).describe('Array of submission IDs to update (must contain at least one).'),
    new_status: z.string().describe('New status: reviewed, approved, rejected, or imported'),
    reviewer: z.string().describe('Name of the reviewer'),
    notes: z.string().default('').describe('Review notes applied to every entry'),
  }).shape,
  options: { readOnlyHint: false },
  handler: async (params) => {
    const validStatuses = ['reviewed', 'approved', 'rejected', 'imported'];
    if (!validStatuses.includes(params.new_status)) {
      return { content: [{ type: 'text' as const, text: JSON.stringify({
        error: `Invalid status '${params.new_status}'. Must be one of: ${validStatuses.join(', ')}`,
      }) }] };
    }
    const obsClient = getObserveClient();
    if (!obsClient) {
      return { content: [{ type: 'text' as const, text: JSON.stringify({
        error: 'OBSERVE_ENDPOINT not configured',
      }) }] };
    }

    const ids: string[] = Array.from(new Set(params.submission_ids as string[]));
    const entries = ids.map((id: string) => ({
      submission_id: id,
      status: String(params.new_status),
      reviewer: String(params.reviewer),
      notes: String(params.notes ?? ''),
    }));

    const result = await obsClient.updateStatus(entries);
    if (!result.success) {
      return { content: [{ type: 'text' as const, text: JSON.stringify({
        error: result.error ?? 'Failed to update status',
        submission_ids: ids,
      }) }] };
    }

    return {
      content: [{ type: 'text' as const, text: JSON.stringify({
        status: 'updated',
        submission_count: ids.length,
        submission_ids: ids,
        new_status: params.new_status,
        reviewer: params.reviewer,
        notes: params.notes,
        rows_updated: result.updated ?? 0,
      }, null, 2) }],
    };
  },
};
