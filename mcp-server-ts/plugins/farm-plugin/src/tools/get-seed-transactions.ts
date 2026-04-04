import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';

const SEEDBANK_ENDPOINT = process.env.SEEDBANK_ENDPOINT
  || 'https://script.google.com/macros/s/AKfycbwm2YllQ0vi-vSz_aruKXGxVL3klbSE7F_85dS4qIlxoy3TP4DA0VkAPcI3izNgj7hMIg/exec';

export const getSeedTransactionsTool: Tool = {
  namespace: 'fc',
  name: 'get_seed_transactions',
  title: 'Get Seed Transactions',
  description: 'Query seed bank transactions (withdrawals, additions, stock changes). Reads from the Seed Bank Google Sheet Transactions tab via Apps Script.',
  paramsSchema: z.object({
    days: z.number().optional().describe('How many days back to search (default 30)'),
    species: z.string().optional().describe('Filter by species name (partial match)'),
    user: z.string().optional().describe('Filter by who made the transaction'),
    transaction_type: z.string().optional().describe('Filter by type: "take" or "add"'),
  }).shape,
  options: { readOnlyHint: true },

  handler: async (params) => {
    const url = new URL(SEEDBANK_ENDPOINT);
    url.searchParams.set('action', 'transactions');
    url.searchParams.set('days', String(params.days ?? 30));
    if (params.species) url.searchParams.set('species', params.species);
    if (params.user) url.searchParams.set('user', params.user);
    if (params.transaction_type) url.searchParams.set('type', params.transaction_type);

    try {
      const resp = await fetch(url.toString(), { redirect: 'follow' });
      const data: any = await resp.json();
      if (!data.success) {
        return { content: [{ type: 'text' as const, text: JSON.stringify({ error: data.error ?? 'Unknown error' }) }], isError: true };
      }
      return { content: [{ type: 'text' as const, text: JSON.stringify(data, null, 2) }] };
    } catch (e: any) {
      return { content: [{ type: 'text' as const, text: JSON.stringify({ error: `Failed to query seed transactions: ${e.message}` }) }], isError: true };
    }
  },
};
