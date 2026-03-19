import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { getObserveClient } from '../clients/index.js';

export const listObservationsTool: Tool = {
  namespace: 'fc',
  name: 'list_observations',
  title: 'List Field Observations',
  description: 'List field observations from the observation sheet.\n\nWorkers submit observations via QR code pages. This tool queries those\nobservations from the Google Sheet, grouped by submission.\n\nArgs:\n    status: Filter by status (pending, reviewed, approved, imported, rejected). Optional.\n    section: Filter by section ID (e.g., "P2R3.15-21"). Optional.\n    observer: Filter by observer name. Optional.\n    date: Filter by date (YYYY-MM-DD). Optional.\n\nReturns:\n    Observations grouped by submission with summary.',
  paramsSchema: z.object({
    status: z.string().optional().describe('Filter by status'),
    section: z.string().optional().describe('Filter by section ID'),
    observer: z.string().optional().describe('Filter by observer name'),
    date: z.string().optional().describe('Filter by date (YYYY-MM-DD)'),
  }).shape,
  options: { readOnlyHint: true },
  handler: async (params) => {
    const obsClient = getObserveClient();
    if (!obsClient) return { content: [{ type: 'text' as const, text: JSON.stringify({ error: 'OBSERVE_ENDPOINT not configured' }) }] };

    const result = await obsClient.listObservations(params);
    if (!result.success) return { content: [{ type: 'text' as const, text: JSON.stringify({ error: result.error ?? 'Failed to fetch observations' }) }] };

    const observations: any[] = result.observations ?? [];
    const submissions: Record<string, any> = {};
    for (const obs of observations) {
      const sid = obs.submission_id ?? 'unknown';
      if (!submissions[sid]) {
        submissions[sid] = {
          submission_id: sid, section_id: obs.section_id ?? '', observer: obs.observer ?? '',
          timestamp: obs.timestamp ?? '', mode: obs.mode ?? '', status: obs.status ?? '',
          section_notes: obs.section_notes ?? '', plants: [],
        };
      }
      if (obs.species) {
        submissions[sid].plants.push({
          species: obs.species, strata: obs.strata ?? '', previous_count: obs.previous_count,
          new_count: obs.new_count, condition: obs.condition ?? '', notes: obs.plant_notes ?? '',
        });
      }
    }

    const grouped = Object.values(submissions).sort((a: any, b: any) => (b.timestamp ?? '').localeCompare(a.timestamp ?? ''));
    return {
      content: [{ type: 'text' as const, text: JSON.stringify({
        filters: params, total_observations: observations.length,
        total_submissions: grouped.length, submissions: grouped,
      }, null, 2) }],
    };
  },
};
