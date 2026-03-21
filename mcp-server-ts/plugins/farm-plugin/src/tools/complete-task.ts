import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { getFarmOSClient } from '../clients/index.js';

export const completeTaskTool: Tool = {
  namespace: 'fc',
  name: 'complete_task',
  title: 'Complete Task',
  description: 'Mark a pending activity log as done (complete a TODO task).\n\nUse query_logs(log_type="activity", status="pending") to find pending tasks first.\n\nArgs:\n    log_name: The exact log name to mark as done (from query_logs results).\n    notes: Optional completion notes.\n\nReturns:\n    Confirmation or error message.',
  paramsSchema: z.object({
    log_name: z.string().describe('The exact log name to mark as done'),
    notes: z.string().optional().describe('Optional completion notes'),
  }).shape,
  options: { readOnlyHint: false },
  handler: async (params, extra) => {
    const client = getFarmOSClient(extra);

    const logId = await client.logExists(params.log_name, 'activity');
    if (!logId) {
      return {
        content: [{ type: 'text' as const, text: JSON.stringify({ error: `Activity log '${params.log_name}' not found in farmOS` }) }],
      };
    }

    const success = await client.updateLogStatus(logId, 'activity', 'done');
    if (!success) {
      return {
        content: [{ type: 'text' as const, text: JSON.stringify({ error: `Failed to update status for '${params.log_name}'` }) }],
      };
    }

    const result: any = {
      status: 'completed',
      log_id: logId,
      log_name: params.log_name,
      new_status: 'done',
    };
    if (params.notes) result.completion_notes = params.notes;

    return {
      content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }],
    };
  },
};
