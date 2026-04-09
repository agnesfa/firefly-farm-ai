import { z, type Tool } from '@fireflyagents/mcp-server-plugin-sdk';
import { getFarmOSClient, getObserveClient } from '../clients/index.js';
import { parseDate, formatPlantAsset, buildAssetName, uploadMediaToLog, updateSpeciesReferencePhoto } from '../helpers/index.js';

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
  return parts.join('\n');
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
    if (observations.length === 0) return { content: [{ type: 'text' as const, text: JSON.stringify({ error: `No observations found for submission '${params.submission_id}'` }) }] };

    const statuses = new Set(observations.map((o: any) => o.status));
    const invalidStatuses = [...statuses].filter((s) => s !== 'reviewed' && s !== 'approved');
    if (invalidStatuses.length > 0) {
      return { content: [{ type: 'text' as const, text: JSON.stringify({ error: `Submission has unexpected statuses: ${[...statuses].join(', ')}. Only 'reviewed' or 'approved' can be imported.` }) }] };
    }

    const sectionId = observations[0].section_id ?? '';
    const mode = observations[0].mode ?? '';
    const obsDate = (observations[0].timestamp ?? '').slice(0, 10);
    const actions: any[] = [];
    const errors: string[] = [];

    // Photo pipeline — fetch all media files for this submission once.
    // Photos attach at the submission level (one set per QR form
    // submission), not per species row, so we fetch once and distribute.
    // Failures here must never block the observation import.
    let submissionMedia: any[] = [];
    const anyMediaListed = observations.some(
      (obs: any) => typeof obs.media_files === 'string' && obs.media_files.trim().length > 0,
    );
    if (!params.dry_run && anyMediaListed) {
      try {
        const mediaResp: any = await obsClient.getMedia(params.submission_id);
        if (mediaResp && mediaResp.success) {
          submissionMedia = mediaResp.files ?? [];
        }
      } catch {
        submissionMedia = [];
      }
    }
    const speciesPhotoUpdates = new Set<string>();

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
              if (submissionMedia.length > 0 && logId) {
                const photos = await uploadMediaToLog(client as any, 'activity', logId, submissionMedia);
                if (photos.length > 0) action.photos_uploaded = photos.length;
              }
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
              if (submissionMedia.length > 0 && inventoryLogId) {
                const photos = await uploadMediaToLog(client as any, 'observation', inventoryLogId, submissionMedia);
                if (photos.length > 0) action.photos_uploaded = photos.length;
              }
              if (submissionMedia.length > 0 && !speciesPhotoUpdates.has(species)) {
                const refId = await updateSpeciesReferencePhoto(client as any, species, submissionMedia);
                if (refId) {
                  action.species_reference_photo = true;
                  speciesPhotoUpdates.add(species);
                }
              }
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
                    if (submissionMedia.length > 0 && obsLogId) {
                      const photos = await uploadMediaToLog(client as any, 'observation', obsLogId, submissionMedia);
                      if (photos.length > 0) action.photos_uploaded = photos.length;
                    }
                    if (submissionMedia.length > 0 && !speciesPhotoUpdates.has(species)) {
                      const refId = await updateSpeciesReferencePhoto(client as any, species, submissionMedia);
                      if (refId) {
                        action.species_reference_photo = true;
                        speciesPhotoUpdates.add(species);
                      }
                    }
                  }
                }
              } else {
                const secUuid = await client.getSectionUuid(obsSection);
                if (secUuid) {
                  const activityLogId = await client.createActivityLog(secUuid, parseDate(obsDate || undefined), `Observation — ${obsSection}`, combinedNotes);
                  action.result = 'created'; action.type = 'activity';
                  if (submissionMedia.length > 0 && activityLogId) {
                    const photos = await uploadMediaToLog(client as any, 'activity', activityLogId, submissionMedia);
                    if (photos.length > 0) action.photos_uploaded = photos.length;
                  }
                  if (submissionMedia.length > 0 && !speciesPhotoUpdates.has(species)) {
                    const refId = await updateSpeciesReferencePhoto(client as any, species, submissionMedia);
                    if (refId) {
                      action.species_reference_photo = true;
                      speciesPhotoUpdates.add(species);
                    }
                  }
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

    const totalPhotos = actions.reduce((sum, a) => sum + (a.photos_uploaded ?? 0), 0);
    const speciesRefCount = actions.filter((a) => a.species_reference_photo).length;

    return {
      content: [{ type: 'text' as const, text: JSON.stringify({
        submission_id: params.submission_id, section_id: sectionId,
        dry_run: params.dry_run, total_actions: actions.length,
        actions, errors: errors.length > 0 ? errors : null,
        sheet_status: sheetStatus,
        pages_regenerated: !params.dry_run && actions.length > 0
          ? 'Pages need regeneration. Run regenerate_pages tool on Agnes\'s machine.'
          : null,
        photos_uploaded: totalPhotos,
        species_reference_photos_updated: speciesRefCount,
        submission_media_fetched: params.dry_run ? 0 : submissionMedia.length,
      }, null, 2) }],
    };
  },
};
