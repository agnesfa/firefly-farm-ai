import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { getFarmOSClient } from '../clients/index.js';

const SEEDBANK_ENDPOINT = process.env.SEEDBANK_ENDPOINT
  || 'https://script.google.com/macros/s/AKfycbwm2YllQ0vi-vSz_aruKXGxVL3klbSE7F_85dS4qIlxoy3TP4DA0VkAPcI3izNgj7hMIg/exec';

export const syncSeedTransactionsTool: Tool = {
  namespace: 'fc',
  name: 'sync_seed_transactions',
  title: 'Sync Seed Transactions',
  description: `Sync seed bank transactions from Google Sheet to farmOS seed assets.

Fetches recent transactions from the SeedBank.gs Transactions tab,
finds the corresponding farmOS seed asset for each, and creates an
observation log with quantity to update the farmOS inventory.

This closes the loop: QR page → Sheet → farmOS.

Args:
    days: How many days of transactions to sync (default 7).
    dry_run: If true, show what would happen without making changes. Default false.

Returns:
    Summary of synced/skipped/failed transactions.`,
  paramsSchema: z.object({
    days: z.number().default(7).describe('How many days of transactions to sync'),
    dry_run: z.boolean().default(false).describe('If true, show what would happen without making changes'),
  }).shape,
  options: { readOnlyHint: false },

  handler: async (params, extra) => {
    const days = params.days ?? 7;
    const dryRun = params.dry_run ?? false;

    // Step 1: Fetch transactions from Sheet
    let transactions: any[];
    try {
      const url = new URL(SEEDBANK_ENDPOINT);
      url.searchParams.set('action', 'transactions');
      url.searchParams.set('days', String(days));
      const resp = await fetch(url.toString(), { redirect: 'follow' });
      const data: any = await resp.json();
      if (!data.success) {
        return { content: [{ type: 'text' as const, text: JSON.stringify({ error: data.error ?? 'Failed to fetch transactions' }) }], isError: true };
      }
      transactions = data.transactions ?? [];
    } catch (e: any) {
      return { content: [{ type: 'text' as const, text: JSON.stringify({ error: `Failed to fetch transactions: ${e.message}` }) }], isError: true };
    }

    if (transactions.length === 0) {
      return { content: [{ type: 'text' as const, text: JSON.stringify({ message: `No transactions in the last ${days} days`, synced: 0 }) }] };
    }

    const client = getFarmOSClient(extra);
    const results: { synced: any[]; skipped: any[]; failed: any[] } = { synced: [], skipped: [], failed: [] };

    for (const txn of transactions) {
      const seedSpecies = txn.seed ?? '';
      const txnType = txn.type ?? '';
      const amount = txn.amount ?? '';
      const txnUser = txn.user ?? '';
      const txnDate = txn.date ?? '';
      const txnNotes = txn.notes ?? '';

      if (!seedSpecies) {
        results.skipped.push({ reason: 'No seed name', txn });
        continue;
      }

      // Step 2: Find farmOS seed asset
      const seedName = `${seedSpecies} Seeds`;
      try {
        let seedAssets = await client.fetchByName('asset/seed', seedName);
        if (seedAssets.length === 0) {
          seedAssets = await client.getSeedAssets(undefined, seedSpecies);
        }
        if (seedAssets.length === 0) {
          results.failed.push({ seed: seedSpecies, reason: `Seed asset not found for '${seedSpecies}'`, txn_date: txnDate });
          continue;
        }

        const seedAsset = seedAssets[0];
        const seedId = seedAsset.id;

        // Get current inventory
        const currentInv = seedAsset.attributes?.inventory ?? [];
        let currentValue = 0;
        for (const q of currentInv) {
          if (q.value != null) {
            const v = parseFloat(q.value);
            if (!isNaN(v)) currentValue = v;
          }
        }

        const txnAmount = parseFloat(amount) || 0;

        // Step 3: Calculate new value
        let newValue: number;
        let adjustment: 'increment' | 'reset';
        if (txnType === 'take') {
          newValue = -txnAmount;
          adjustment = 'increment';
        } else if (txnType === 'add') {
          newValue = txnAmount;
          adjustment = 'increment';
        } else {
          // status_change or unknown — skip
          results.skipped.push({ seed: seedSpecies, reason: `Unsupported type '${txnType}'`, txn_date: txnDate });
          continue;
        }

        // Check for duplicate (idempotency)
        const logName = `Seed sync — ${seedSpecies} — ${txnType} ${txnAmount}g — ${txnDate}`;
        const existingLog = await client.logExists(logName, 'observation');
        if (existingLog) {
          results.skipped.push({ seed: seedSpecies, reason: 'Already synced', txn_date: txnDate, log_id: existingLog });
          continue;
        }

        if (dryRun) {
          results.synced.push({
            seed: seedSpecies,
            type: txnType,
            amount: txnAmount,
            current_inventory: currentValue,
            new_inventory: currentValue + newValue,
            user: txnUser,
            date: txnDate,
            dry_run: true,
          });
          continue;
        }

        // Step 4: Create quantity + observation log
        const qtyId = await client.createSeedQuantity(seedId, newValue, 'grams', adjustment);
        const notes = `${txnUser}: ${txnNotes || `${txnType} ${txnAmount}g`}`;
        const timestamp = Math.floor(new Date(txnDate.replace(' ', 'T') + '+11:00').getTime() / 1000);
        const logId = await client.createSeedObservationLog(seedId, qtyId, timestamp, logName, notes, false);

        results.synced.push({
          seed: seedSpecies,
          type: txnType,
          amount: txnAmount,
          new_inventory: currentValue + newValue,
          user: txnUser,
          date: txnDate,
          log_id: logId,
        });
      } catch (e: any) {
        results.failed.push({ seed: seedSpecies, error: e.message, txn_date: txnDate });
      }
    }

    const summary = {
      days,
      dry_run: dryRun,
      total_transactions: transactions.length,
      synced: results.synced.length,
      skipped: results.skipped.length,
      failed: results.failed.length,
      details: results,
    };

    return { content: [{ type: 'text' as const, text: JSON.stringify(summary, null, 2) }] };
  },
};
