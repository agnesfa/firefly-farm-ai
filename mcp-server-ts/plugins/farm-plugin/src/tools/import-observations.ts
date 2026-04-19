import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { logger as baseLogger } from '@fireflyagents/mcp-shared-utils';
import { getFarmOSClient, getObserveClient } from '../clients/index.js';
import {
  parseDate,
  formatPlantAsset,
  buildAssetName,
  uploadMediaToLog,
  updateSpeciesReferencePhoto,
  buildStamp,
  appendStamp,
  parsePlantTypeMetadata,
  buildPlantTypeDescription,
} from '../helpers/index.js';
import { newPhotoPipelineReport, decodeMediaFile, type PhotoPipelineReport } from '../helpers/photo-pipeline.js';
import {
  buildBotanicalLookupFromCsv,
  verifySpeciesPhoto,
  getPlantnetCallCount,
  resetPlantnetCallCount,
  type BotanicalLookup,
} from '../helpers/plantnet-verify.js';
import * as fs from 'node:fs';
import * as path from 'node:path';

const logger = baseLogger.child({ context: 'import-observations' });

/**
 * Resolve the knowledge directory in a way that survives different
 * build layouts. On Railway the Dockerfile copies `knowledge/` into
 * `/app/knowledge/`, and the plugin compiles to
 * `/app/plugins/farm-plugin/dist/tools/...`. The original resolve() was
 * brittle to refactors that move files between `tools/` and `helpers/`.
 */
function resolveKnowledgePath(filename: string): string | null {
  const candidates = [
    // Dockerfile layout: /app/knowledge/
    path.resolve('/app/knowledge', filename),
    // Local dev: compiled output at dist/tools/
    path.resolve(__dirname, '../../../../knowledge', filename),
    // Local dev: compiled output at dist/helpers/
    path.resolve(__dirname, '../../../../../knowledge', filename),
    // Fallback: repo root when CWD is repo root
    path.resolve(process.cwd(), 'knowledge', filename),
    // Fallback: CWD itself has a knowledge folder (rare)
    path.resolve(process.cwd(), filename),
  ];
  for (const p of candidates) {
    try {
      if (fs.existsSync(p)) return p;
    } catch { /* stat-failure tolerated */ }
  }
  return null;
}

/**
 * Build a botanical-name lookup using farmOS plant_type taxonomy as the
 * primary source (no filesystem dependency), with the knowledge/plant_types.csv
 * file as a fallback for local dev.
 */
async function buildBotanicalLookupResilient(
  client: any,
): Promise<{ lookup: BotanicalLookup; source: string; size: number }> {
  // Primary: farmOS plant_type taxonomy (cached).
  try {
    const plantTypes = await client.getAllPlantTypesCached();
    if (Array.isArray(plantTypes) && plantTypes.length > 0) {
      const forward = new Map<string, string>();
      const reverse = new Map<string, string>();
      for (const pt of plantTypes) {
        const name = (pt.attributes?.name ?? '').trim();
        const desc = pt.attributes?.description;
        const descText = typeof desc === 'object' ? desc?.value ?? '' : String(desc ?? '');
        const meta = parsePlantTypeMetadata(descText);
        const botanical = (meta?.botanical_name ?? '').trim();
        if (name && botanical) {
          forward.set(botanical.toLowerCase(), name);
          reverse.set(name, botanical.toLowerCase());
        }
      }
      if (reverse.size > 0) {
        return { lookup: { forward, reverse }, source: 'farmos_plant_types', size: reverse.size };
      }
    }
  } catch (err: any) {
    logger.warn(`farmOS plant_type lookup failed, falling back to CSV: ${err?.message ?? err}`);
  }

  // Fallback: knowledge/plant_types.csv
  const csvPath = resolveKnowledgePath('plant_types.csv');
  if (csvPath) {
    try {
      const csv = fs.readFileSync(csvPath, 'utf-8');
      const lookup = buildBotanicalLookupFromCsv(csv);
      return { lookup, source: `csv:${csvPath}`, size: lookup.reverse.size };
    } catch (err: any) {
      logger.warn(`Failed to read plant_types.csv: ${err?.message ?? err}`);
    }
  }

  return {
    lookup: { forward: new Map(), reverse: new Map() },
    source: 'empty',
    size: 0,
  };
}

function buildImportNotes(obs: any, extra = ''): string {
  const parts: string[] = [];
  if (obs.observer) parts.push(`Reporter: ${obs.observer}`);
  if (obs.timestamp) parts.push(`Submitted: ${(obs.timestamp ?? '').slice(0, 19)}`);
  if (obs.mode) parts.push(`Mode: ${obs.mode}`);
  if (obs.condition && obs.condition !== 'alive') parts.push(`Condition: ${obs.condition}`);
  if (obs.section_notes) parts.push(`Section notes: ${obs.section_notes}`);
  if (obs.plant_notes) parts.push(`Plant notes: ${obs.plant_notes}`);
  if (obs.previous_count != null && obs.new_count != null) parts.push(`Count: ${obs.previous_count} → ${obs.new_count}`);
  if (extra) parts.push(extra);
  const notes = parts.join('\n');
  const stamp = buildStamp({
    initiator: obs.observer ?? 'system',
    role: obs.observer ? 'farmhand' : 'system',
    channel: 'automated',
    executor: 'farmos_api',
    action: 'created',
    target: 'observation',
    relatedEntities: [obs.species, obs.section_id].filter(Boolean),
    sourceSubmission: obs.submission_id,
  });
  return appendStamp(notes, stamp);
}

/** Tag a plant_type's description with photo_source after setting a reference photo. */
async function tagPhotoSource(client: any, species: string, photoSource: string): Promise<void> {
  try {
    const uuid = await client.getPlantTypeUuid(species);
    if (!uuid) return;
    const allTypes = await client.getAllPlantTypesCached();
    const term = allTypes.find((t: any) => t.id === uuid);
    if (!term) return;
    const desc = term.attributes?.description;
    const descText = typeof desc === 'object' ? desc?.value ?? '' : String(desc ?? '');
    const meta = parsePlantTypeMetadata(descText);
    meta.photo_source = photoSource;
    const newDesc = buildPlantTypeDescription(meta);
    await client.updatePlantType(uuid, { description: { value: newDesc, format: 'default' } });
  } catch { /* non-critical — photo uploaded, tag failed */ }
}

export const importObservationsTool: Tool = {
  namespace: 'fc',
  name: 'import_observations',
  title: 'Import Observations',
  description: 'Import approved/reviewed observations from the Sheet into farmOS.\n\nFetches observations for the submission, validates against farmOS,\ncreates appropriate logs/assets, and updates Sheet status to imported.\n\nArgs:\n    submission_id: The submission ID to import.\n    reviewer: Who is performing the import. Default "Claude".\n    dry_run: If true, show what would happen without making changes. Default false.\n\nReturns:\n    Import results: what was created/updated in farmOS, any errors.',
  paramsSchema: z.object({
    submission_id: z.string().describe('The submission ID to import'),
    reviewer: z.string().default('Claude').describe('Who is performing the import'),
    dry_run: z.boolean().default(false).describe('If true, show what would happen without making changes'),
  }).shape,
  options: { readOnlyHint: false },
  handler: async (params, extra) => {
    const obsClient = getObserveClient();
    if (!obsClient) return { content: [{ type: 'text' as const, text: JSON.stringify({ error: 'OBSERVE_ENDPOINT not configured' }) }] };
    const client = getFarmOSClient(extra);

    const result = await obsClient.listObservations({ submission_id: params.submission_id });
    if (!result.success) return { content: [{ type: 'text' as const, text: JSON.stringify({ error: result.error ?? 'Failed to fetch observations' }) }] };

    const observations: any[] = result.observations ?? [];
    if (observations.length === 0) {
      // Empty result can mean either (a) submission_id is truly unknown, or
      // (b) the submission was previously imported and delete_imported
      // cleaned up its rows. ADR 0007 Fix 2: treat this as idempotent
      // "already imported" rather than a hard error, so retries are safe.
      return { content: [{ type: 'text' as const, text: JSON.stringify({
        status: 'already_imported_or_unknown',
        submission_id: params.submission_id,
        message: `No observations found for submission '${params.submission_id}'. This submission may already have been imported (rows deleted after successful import) or the ID is unknown. Check farmOS for logs with "submission=${params.submission_id}" in notes.`,
        actions: 0,
      }) }] };
    }

    const statuses = new Set(observations.map((o: any) => o.status));
    // ADR 0007 Fix 2: if all observations for this submission are already
    // imported, skip gracefully with success. Retries must be idempotent.
    if ([...statuses].every((s) => s === 'imported')) {
      return { content: [{ type: 'text' as const, text: JSON.stringify({
        status: 'already_imported',
        submission_id: params.submission_id,
        message: 'All observations for this submission have already been imported. Skipping.',
        observation_count: observations.length,
        actions: 0,
      }) }] };
    }
    const invalidStatuses = [...statuses].filter((s) => s !== 'reviewed' && s !== 'approved' && s !== 'imported');
    if (invalidStatuses.length > 0) {
      return { content: [{ type: 'text' as const, text: JSON.stringify({ error: `Submission has unexpected statuses: ${[...statuses].join(', ')}. Only 'reviewed', 'approved', or 'imported' (skipped) can be processed.` }) }] };
    }

    const sectionId = observations[0].section_id ?? '';
    const mode = observations[0].mode ?? '';
    const obsDate = (observations[0].timestamp ?? '').slice(0, 10);
    const actions: any[] = [];
    const errors: string[] = [];

    // ── Photo pipeline setup ─────────────────────────────────
    //
    // Architecture (April 15 2026 redesign):
    //   1. Fetch all submission media from Drive ONCE.
    //   2. Attach EVERY photo to the log unconditionally. Photos are
    //      primary evidence and must never be discarded by a broken
    //      verification gate.
    //   3. Run PlantNet verification in PARALLEL (not as a gate) to
    //      decide which photos are good enough to promote as the
    //      plant_type reference photo. Verification failure never
    //      loses the photo, only demotes the quality signal.
    //   4. Report EVERY failure mode in the response so the operator
    //      can see what happened.
    const report: PhotoPipelineReport = newPhotoPipelineReport();
    resetPlantnetCallCount();
    report.verification.plantnet_key_present =
      (process.env.PLANTNET_API_KEY ?? '').trim().length > 0;

    let submissionMedia: any[] = [];
    const anyMediaListed = observations.some(
      (obs: any) => typeof obs.media_files === 'string' && obs.media_files.trim().length > 0,
    );
    if (!params.dry_run && anyMediaListed) {
      try {
        const mediaResp: any = await obsClient.getMedia(params.submission_id);
        if (mediaResp && mediaResp.success) {
          submissionMedia = mediaResp.files ?? [];
        } else if (mediaResp && !mediaResp.success) {
          errors.push(`Media fetch returned not-ok: ${mediaResp.error ?? 'unknown'}`);
        }
      } catch (err: any) {
        errors.push(`Media fetch threw: ${err?.message ?? err}`);
        submissionMedia = [];
      }
    }
    report.media_files_fetched = submissionMedia.length;
    const speciesPhotoUpdates = new Set<string>();

    // Botanical lookup — resilient across deploy layouts. Prefer farmOS
    // taxonomy (no filesystem dependency), fall back to CSV.
    let botanicalLookup: BotanicalLookup = { forward: new Map(), reverse: new Map() };
    let lookupSource = 'not_loaded';
    if (submissionMedia.length > 0) {
      const built = await buildBotanicalLookupResilient(client);
      botanicalLookup = built.lookup;
      lookupSource = built.source;
      report.verification.botanical_lookup_size = built.size;
    }

    // Once verification is marked degraded (e.g. first call hits HTTP 403),
    // stop making PlantNet calls for the rest of the import — photos still
    // attach, we just stop burning quota on calls that will all fail.
    async function verifyOnePhoto(
      media: any,
      species: string,
    ): Promise<{ verified: boolean; reason: string }> {
      if (report.verification.degraded) {
        return { verified: false, reason: 'verification_degraded' };
      }
      if (!report.verification.plantnet_key_present) {
        return { verified: false, reason: 'no_api_key' };
      }
      if (botanicalLookup.reverse.size === 0) {
        return { verified: false, reason: 'no_botanical_lookup' };
      }
      if (!species) {
        return { verified: true, reason: 'no_species_claim' };
      }
      const decoded = decodeMediaFile(media);
      if (!decoded) return { verified: false, reason: 'decode_failed' };
      const result = await verifySpeciesPhoto(decoded.bytes, species, botanicalLookup);
      // If the first call came back with an auth error, disable verification
      // for the rest of this import to avoid retrying on every photo.
      if (!result.verified && /api_http_(401|403)/i.test(result.reason)) {
        report.verification.degraded = true;
        report.verification.degraded_reason =
          `PlantNet authentication failed (${result.reason}). ` +
          `Check the API key and its authorized domains on my.plantnet.org. ` +
          `Photos are still being attached to logs — only species-reference ` +
          `promotion is disabled.`;
        logger.warn(report.verification.degraded_reason);
      }
      return {
        verified: result.verified,
        reason: result.reason || (result.verified ? 'match' : 'mismatch'),
      };
    }

    /**
     * Attach all submission photos to `logId`, and if any of them verify
     * via PlantNet for `species`, also promote the first verified photo
     * as the species reference photo.
     *
     * Every photo is uploaded UNCONDITIONALLY. Verification only affects
     * the species-reference-photo promotion step.
     */
    async function attachAndMaybePromote(
      logId: string | null,
      logType: string,
      species: string,
      contextLabel: string,
    ): Promise<number> {
      if (!logId || submissionMedia.length === 0) return 0;

      // Step 1: upload everything. Never skipped.
      const uploadedIds = await uploadMediaToLog(
        client as any,
        logType,
        logId,
        submissionMedia,
        report,
        contextLabel,
      );

      // Step 2: verify each photo (quality signal, not a gate) and if
      // any verify, promote the first verified one as species reference.
      if (!species || speciesPhotoUpdates.has(species)) {
        return uploadedIds.length;
      }
      const verifiedForPromotion: any[] = [];
      for (const f of submissionMedia) {
        const v = await verifyOnePhoto(f, species);
        if (v.verified) {
          report.verification.photos_verified += 1;
          verifiedForPromotion.push(f);
          // One verified photo is enough for promotion — stop verifying
          // the rest of this submission for this species to save quota.
          break;
        } else if (v.reason !== 'verification_degraded' && v.reason !== 'no_api_key' && v.reason !== 'no_botanical_lookup') {
          report.verification.photos_rejected += 1;
        }
      }
      if (verifiedForPromotion.length > 0) {
        const refId = await updateSpeciesReferencePhoto(
          client as any,
          species,
          verifiedForPromotion,
        );
        if (refId) {
          speciesPhotoUpdates.add(species);
          report.species_reference_photos_updated += 1;
          // Non-critical tagging step
          tagPhotoSource(client, species, 'farm_observation').catch(() => {});
          return uploadedIds.length;
        }
      }
      return uploadedIds.length;
    }

    for (const obs of observations) {
      const species = (obs.species ?? '').trim();
      const newCount = obs.new_count;
      const previousCount = obs.previous_count;
      const sectionNotes = obs.section_notes ?? '';
      const obsSection = obs.section_id ?? sectionId;
      const obsMode = obs.mode ?? mode;

      // Case A: Section comment only
      if (!species && sectionNotes) {
        const action: any = { type: 'activity', section: obsSection, notes: sectionNotes };
        if (!params.dry_run) {
          try {
            const sectionUuid = await client.getSectionUuid(obsSection);
            if (sectionUuid) {
              const ts = parseDate(obsDate || undefined);
              const logId = await client.createActivityLog(sectionUuid, ts, `Observation — ${obsSection}`, buildImportNotes(obs));
              action.result = 'created'; action.log_id = logId;
              const count = await attachAndMaybePromote(logId, 'activity', '', `activity/${obsSection}`);
              if (count > 0) action.photos_uploaded = count;
            } else { action.result = 'error'; errors.push(`Section ${obsSection} not found`); }
          } catch (e: any) { action.result = 'error'; errors.push(`Activity for ${obsSection}: ${e.message}`); }
        } else { action.result = 'dry_run'; }
        actions.push(action);
        continue;
      }
      if (!species) continue;

      // Case B: New plant
      if (obsMode === 'new_plant' || (previousCount === 0 && newCount && newCount > 0)) {
        const count = newCount ? parseInt(newCount) : 1;
        const action: any = { type: 'create_plant', species, section: obsSection, count };
        if (!params.dry_run) {
          try {
            const ptUuid = await client.getPlantTypeUuid(species);
            if (!ptUuid) { action.result = 'error'; errors.push(`Plant type '${species}' not found`); actions.push(action); continue; }
            const secUuid = await client.getSectionUuid(obsSection);
            if (!secUuid) { action.result = 'error'; errors.push(`Section '${obsSection}' not found`); actions.push(action); continue; }
            const dateStr = obsDate || new Date(Date.now() + 10*60*60*1000).toISOString().slice(0,10);
            const assetName = buildAssetName(dateStr, species, obsSection);
            const existing = await client.plantAssetExists(assetName);
            if (existing) { action.result = 'skipped'; action.plant_name = assetName; actions.push(action); continue; }
            const plantId = await client.createPlantAsset(assetName, ptUuid, buildImportNotes(obs, 'New plant added via field observation'));
            if (plantId) {
              const qtyId = await client.createQuantity(plantId, count, 'reset');
              const inventoryLogId = await client.createObservationLog(plantId, secUuid, qtyId, parseDate(dateStr), `Inventory ${obsSection} — ${species}`, '');
              action.result = 'created'; action.plant_name = assetName;
              const photoCount = await attachAndMaybePromote(
                inventoryLogId,
                'observation',
                species,
                `new_plant/${obsSection}/${species}`,
              );
              if (photoCount > 0) action.photos_uploaded = photoCount;
              if (speciesPhotoUpdates.has(species)) action.species_reference_photo = true;
            }
          } catch (e: any) { action.result = 'error'; errors.push(`Create ${species} in ${obsSection}: ${e.message}`); }
        } else { action.result = 'dry_run'; }
        actions.push(action);
        continue;
      }

      // Case C: Inventory update
      if (newCount != null || obs.plant_notes || obs.condition) {
        const plants = await client.getPlantAssets(obsSection, species);
        if (plants.length === 0) { errors.push(`Plant '${species}' not found in section ${obsSection}`); continue; }
        const plant = plants[0];
        const plantName = plant.attributes?.name ?? '';
        const combinedNotes = buildImportNotes(obs);
        const countVal = newCount != null ? parseInt(newCount) : null;
        const prevVal = previousCount != null ? parseInt(previousCount) : null;
        const countChanged = countVal != null && countVal !== prevVal;

        if (countChanged || combinedNotes) {
          const action: any = { type: 'observation', plant_name: plantName, species, section: obsSection, previous_count: prevVal, new_count: countVal, notes: combinedNotes };
          if (!params.dry_run) {
            try {
              if (countVal != null) {
                const formatted = formatPlantAsset(plant);
                const secUuid = await client.getSectionUuid(formatted.section);
                if (secUuid) {
                  const ts = parseDate(obsDate || undefined);
                  const dateStr = new Date((ts*1000)+10*60*60*1000).toISOString().slice(0,10);
                  const logName = `Observation ${formatted.section} — ${species} — ${dateStr}`;
                  const existing = await client.logExists(logName, 'observation');
                  if (existing) { action.result = 'skipped'; } else {
                    const qtyId = await client.createQuantity(plant.id, countVal, 'reset');
                    const obsLogId = await client.createObservationLog(plant.id, secUuid, qtyId, ts, logName, combinedNotes);
                    action.result = 'created';
                    if (obsLogId) action.log_id = obsLogId;
                    const photoCount = await attachAndMaybePromote(
                      obsLogId,
                      'observation',
                      species,
                      `observation/${obsSection}/${species}`,
                    );
                    if (photoCount > 0) action.photos_uploaded = photoCount;
                    if (speciesPhotoUpdates.has(species)) action.species_reference_photo = true;
                  }
                }
              } else {
                const secUuid = await client.getSectionUuid(obsSection);
                if (secUuid) {
                  const activityLogId = await client.createActivityLog(secUuid, parseDate(obsDate || undefined), `Observation — ${obsSection}`, combinedNotes);
                  action.result = 'created'; action.type = 'activity';
                  const photoCount = await attachAndMaybePromote(
                    activityLogId,
                    'activity',
                    species,
                    `activity/${obsSection}/${species}`,
                  );
                  if (photoCount > 0) action.photos_uploaded = photoCount;
                  if (speciesPhotoUpdates.has(species)) action.species_reference_photo = true;
                }
              }
            } catch (e: any) { action.result = 'error'; errors.push(`Observation for ${species} in ${obsSection}: ${e.message}`); }
          } else { action.result = 'dry_run'; }
          actions.push(action);
        }
      }
    }

    // Update Sheet status
    const importedCount = actions.filter((a) => a.result === 'created').length;
    let sheetStatus = params.dry_run ? 'dry_run' : 'pending';
    if (!params.dry_run && (importedCount > 0 || errors.length === 0)) {
      try {
        await obsClient.updateStatus([{
          submission_id: params.submission_id, status: 'imported',
          reviewer: params.reviewer, notes: `${importedCount} actions imported to farmOS`,
        }]);
        sheetStatus = 'imported';
        try { await obsClient.deleteImported(params.submission_id); sheetStatus = 'imported_and_cleaned'; }
        catch (e: any) { errors.push(`Failed to clean up Sheet rows: ${e.message}`); }
      } catch (e: any) { errors.push(`Failed to update Sheet status: ${e.message}`); sheetStatus = 'partial'; }
    }

    // Snapshot PlantNet call count into the report (reset at import start)
    report.verification.plantnet_api_calls = getPlantnetCallCount();

    // Emit a loud warning in the response if photos were submitted but
    // none got uploaded — the operator must not have to go digging.
    const photoHealthWarnings: string[] = [];
    if (report.media_files_fetched > 0 && report.photos_uploaded === 0) {
      photoHealthWarnings.push(
        `CRITICAL: ${report.media_files_fetched} media files fetched but 0 uploaded. ` +
        `Check upload_errors in photo_pipeline for specifics.`,
      );
    }
    if (
      report.media_files_fetched > 0 &&
      report.verification.photos_verified === 0 &&
      report.verification.plantnet_api_calls === 0 &&
      report.verification.plantnet_key_present &&
      report.verification.botanical_lookup_size > 0 &&
      !report.verification.degraded
    ) {
      photoHealthWarnings.push(
        `WARNING: PlantNet is configured but was never called. ` +
        `Verification may be silently short-circuiting. lookup_source=${lookupSource}`,
      );
    }
    if (report.verification.degraded) {
      photoHealthWarnings.push(
        `INFO: Verification degraded mid-import. Photos still attached to logs; ` +
        `species-reference-photo promotion disabled. Reason: ${report.verification.degraded_reason}`,
      );
    }

    return {
      content: [{ type: 'text' as const, text: JSON.stringify({
        submission_id: params.submission_id, section_id: sectionId,
        dry_run: params.dry_run, total_actions: actions.length,
        actions, errors: errors.length > 0 ? errors : null,
        sheet_status: sheetStatus,
        pages_regenerated: !params.dry_run && actions.length > 0
          ? 'Pages need regeneration. Run regenerate_pages tool on Agnes\'s machine.'
          : null,

        // Flat metrics (backwards compatible with earlier callers that
        // still read these keys directly)
        photos_uploaded: report.photos_uploaded,
        photos_verified: report.verification.photos_verified,
        photos_rejected: report.verification.photos_rejected,
        plantnet_api_calls: report.verification.plantnet_api_calls,
        species_reference_photos_updated: report.species_reference_photos_updated,
        submission_media_fetched: params.dry_run ? 0 : report.media_files_fetched,

        // Rich pipeline diagnostics — this is where the operator looks
        // to understand what actually happened. "photos_uploaded: 0"
        // is never a mystery anymore.
        photo_pipeline: {
          ...report,
          lookup_source: lookupSource,
          warnings: photoHealthWarnings.length > 0 ? photoHealthWarnings : null,
        },
      }, null, 2) }],
    };
  },
};
