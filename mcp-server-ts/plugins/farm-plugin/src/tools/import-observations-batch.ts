import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { logger as baseLogger } from '@fireflyagents/mcp-shared-utils';
import { importObservationsTool } from './import-observations.js';

const logger = baseLogger.child({ context: 'import-observations-batch' });

/**
 * Batch wrapper around import_observations. Runs the existing
 * single-submission importer once per submission_id and aggregates the
 * per-submission results + a combined photo_pipeline report.
 *
 * Why this exists: Leah's April 14 walk required ~45 tool calls to
 * import 15 submissions through the single-submission tool. The bulk
 * of that was "one approve + one import per submission". Batch
 * versions of both collapse the work to a handful of calls. The
 * status-batch is genuinely one API round trip (the Apps Script
 * endpoint takes a list). The import-batch is a server-side loop —
 * still one tool call from the caller's perspective, still one
 * request/response cycle, but it runs N internal loops to process
 * each submission through the existing validated single-submission
 * logic.
 *
 * The loop is sequential (not parallel) by design — parallel imports
 * would race on farmOS deduplication checks and the PlantNet rate
 * limit, and the Apps Script backend is single-threaded anyway.
 */
export const importObservationsBatchTool: Tool = {
  namespace: 'fc',
  name: 'import_observations_batch',
  title: 'Import Observations (batch)',
  description: 'Batch version of import_observations. Imports many submissions in one tool call by looping the existing single-submission importer internally.\n\nUse this when you need to import more than 2-3 submissions at once — e.g. clearing a WWOOFer\'s field walk. For single submissions, use import_observations directly.\n\nArgs:\n    submission_ids: Array of submission IDs to import (1+).\n    reviewer: Who is performing the import. Default "Claude".\n    dry_run: If true, show what would happen without making changes.\n    continue_on_error: If true (default), keep importing remaining submissions after one fails. If false, abort on the first error.\n\nReturns:\n    Per-submission results + aggregated photo_pipeline metrics + any errors.',
  paramsSchema: z.object({
    submission_ids: z.array(z.string()).min(1).describe('Array of submission IDs to import'),
    reviewer: z.string().default('Claude').describe('Who is performing the import'),
    dry_run: z.boolean().default(false).describe('If true, preview only'),
    continue_on_error: z.boolean().default(true).describe('Keep going after failures'),
  }).shape,
  options: { readOnlyHint: false },
  handler: async (params, extra) => {
    const uniqueIds = Array.from(new Set(params.submission_ids));

    const perSubmission: any[] = [];
    let totalActions = 0;
    const batchErrors: string[] = [];

    // Aggregated photo pipeline report — sum the per-submission reports
    // into one roll-up the operator can scan without flipping between
    // submissions.
    const aggregate = {
      media_files_fetched: 0,
      decode_failures: 0,
      photos_uploaded: 0,
      upload_errors: [] as string[],
      species_reference_photos_updated: 0,
      verification: {
        plantnet_key_present: false,
        botanical_lookup_size: 0,
        plantnet_api_calls: 0,
        photos_verified: 0,
        photos_rejected: 0,
        degraded: false,
        degraded_reason: '',
      },
    };

    for (const id of uniqueIds) {
      let parsed: any;
      try {
        const res = await importObservationsTool.handler(
          { submission_id: id, reviewer: params.reviewer, dry_run: params.dry_run },
          extra,
        );
        const first = res.content[0] as any;
        parsed = JSON.parse(first.text ?? '{}');
      } catch (err: any) {
        const msg = `import failed for ${id}: ${err?.message ?? err}`;
        logger.warn(msg);
        batchErrors.push(msg);
        perSubmission.push({ submission_id: id, error: msg });
        if (!params.continue_on_error) break;
        continue;
      }

      // The single-submission tool can also return a fatal error via a
      // top-level `error` field in the JSON response (e.g. when
      // list_observations says the submission doesn't exist). That's
      // different from per-action errors in the `errors` array.
      if (parsed.error) {
        const msg = `import returned error for ${id}: ${parsed.error}`;
        logger.warn(msg);
        batchErrors.push(msg);
        perSubmission.push({ submission_id: id, error: msg });
        if (!params.continue_on_error) break;
        continue;
      }

      perSubmission.push({
        submission_id: id,
        section_id: parsed.section_id,
        total_actions: parsed.total_actions,
        sheet_status: parsed.sheet_status,
        photos_uploaded: parsed.photos_uploaded,
        species_reference_photos_updated: parsed.species_reference_photos_updated,
        errors: parsed.errors,
      });
      totalActions += parsed.total_actions ?? 0;

      // Aggregate photo pipeline metrics
      const pp = parsed.photo_pipeline ?? {};
      aggregate.media_files_fetched += pp.media_files_fetched ?? 0;
      aggregate.decode_failures += pp.decode_failures ?? 0;
      aggregate.photos_uploaded += pp.photos_uploaded ?? 0;
      aggregate.species_reference_photos_updated += pp.species_reference_photos_updated ?? 0;
      if (Array.isArray(pp.upload_errors)) {
        for (const e of pp.upload_errors) aggregate.upload_errors.push(`[${id}] ${e}`);
      }
      const vv = pp.verification ?? {};
      aggregate.verification.plantnet_key_present =
        aggregate.verification.plantnet_key_present || (vv.plantnet_key_present ?? false);
      aggregate.verification.botanical_lookup_size = Math.max(
        aggregate.verification.botanical_lookup_size,
        vv.botanical_lookup_size ?? 0,
      );
      aggregate.verification.plantnet_api_calls += vv.plantnet_api_calls ?? 0;
      aggregate.verification.photos_verified += vv.photos_verified ?? 0;
      aggregate.verification.photos_rejected += vv.photos_rejected ?? 0;
      if (vv.degraded) {
        aggregate.verification.degraded = true;
        if (!aggregate.verification.degraded_reason) {
          aggregate.verification.degraded_reason = vv.degraded_reason ?? '';
        }
      }

      if (parsed.errors && Array.isArray(parsed.errors)) {
        for (const e of parsed.errors) batchErrors.push(`[${id}] ${e}`);
      }
    }

    const processed = perSubmission.length;
    const succeeded = perSubmission.filter((r) => !r.error).length;

    return {
      content: [{ type: 'text' as const, text: JSON.stringify({
        status: succeeded === uniqueIds.length ? 'ok' : 'partial',
        submitted: uniqueIds.length,
        processed,
        succeeded,
        dry_run: params.dry_run,
        total_actions: totalActions,
        submissions: perSubmission,
        errors: batchErrors.length > 0 ? batchErrors : null,
        photo_pipeline: aggregate,
      }, null, 2) }],
    };
  },
};
