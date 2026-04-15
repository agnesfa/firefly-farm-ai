/**
 * Photo pipeline helpers for import_observations.
 *
 * Architecture (as of April 15 2026 redesign):
 *
 *   EVERY photo is attached to the farmOS log. No exceptions.
 *   PlantNet verification is only used to decide whether the photo is
 *   also promoted to the species reference photo in plant_type taxonomy.
 *
 * This inverts the previous design where rejected photos were discarded.
 * The old design coupled two concerns — photo upload and species
 * verification — and made photos silently vanish whenever PlantNet was
 * down, rate-limited, or the deploy env was misconfigured. April 14
 * Leah walk regression was a symptom of that coupling.
 *
 * Rule: photos are primary evidence. Verification is a quality check.
 * Evidence must always be preserved. Quality checks may be degraded.
 *
 * Every failure mode below surfaces in a PhotoPipelineReport so the
 * operator can see exactly what happened — no more silent no-ops.
 */

/** A decoded media file ready for farmOS upload. */
export interface DecodedMedia {
  filename: string;
  mimeType: string;
  bytes: ArrayBuffer;
}

/**
 * Per-import diagnostics. Every import_observations call returns one of
 * these so the operator can see the ACTUAL state of the photo pipeline,
 * not a lying zero.
 */
export interface PhotoPipelineReport {
  /** Media files the importer received from Drive. */
  media_files_fetched: number;
  /** Files that could not be base64-decoded (corrupt payload). */
  decode_failures: number;
  /** Files successfully uploaded as farmOS file attachments on logs. */
  photos_uploaded: number;
  /** Upload attempts that failed — one entry per failure with reason. */
  upload_errors: string[];
  /** Plant-type reference photos refreshed this run. */
  species_reference_photos_updated: number;

  /** PlantNet verification state — present regardless of whether it ran. */
  verification: {
    /** Was PLANTNET_API_KEY present in env? */
    plantnet_key_present: boolean;
    /** Could botanical lookup be built (from farmOS or CSV)? */
    botanical_lookup_size: number;
    /** Number of PlantNet API calls actually made. */
    plantnet_api_calls: number;
    /** Photos PlantNet confirmed matched their claimed species. */
    photos_verified: number;
    /** Photos PlantNet rejected (with reasons). */
    photos_rejected: number;
    /**
     * True when verification had to be degraded mid-import — e.g. the
     * first PlantNet call returned an auth error, so we disabled verify
     * for the rest of the session. Photos still flow through to upload.
     */
    degraded: boolean;
    /** Human-readable note explaining degradation (for operator). */
    degraded_reason: string;
  };
}

export function newPhotoPipelineReport(): PhotoPipelineReport {
  return {
    media_files_fetched: 0,
    decode_failures: 0,
    photos_uploaded: 0,
    upload_errors: [],
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
}

/**
 * Decode a single Apps Script media payload
 * ({filename, mime_type, data_base64}) into a binary ArrayBuffer.
 *
 * A ``data:image/jpeg;base64,`` prefix is tolerated — older submissions
 * stored the payload with it attached.
 *
 * Returns ``null`` if the file cannot be decoded (empty payload, invalid
 * base64, etc.). Callers MUST treat null as "skip this file, keep going",
 * never as a reason to abort the import.
 */
export function decodeMediaFile(file: any): DecodedMedia | null {
  if (!file || typeof file !== 'object') return null;
  let data: unknown = file.data_base64 ?? file.data ?? '';
  if (typeof data !== 'string' || data === '') return null;

  // Strip "data:image/jpeg;base64," prefix if present.
  if (data.trim().startsWith('data:') && data.includes(',')) {
    data = data.slice(data.indexOf(',') + 1);
  }
  if (typeof data !== 'string') return null;

  let bytes: ArrayBuffer;
  try {
    // Node 18+ and modern browsers both expose Buffer / atob; prefer
    // Buffer in Node since it tolerates padding issues.
    if (typeof Buffer !== 'undefined') {
      const buf = Buffer.from(data, 'base64');
      bytes = buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
    } else {
      const bin = atob(data);
      const arr = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
      bytes = arr.buffer;
    }
  } catch {
    return null;
  }

  return {
    filename: file.filename || 'photo.jpg',
    mimeType: file.mime_type || 'image/jpeg',
    bytes,
  };
}

/** Shape required of the farmOS client for photo uploads. */
export interface PhotoUploadClient {
  uploadFile(
    entityType: string,
    entityId: string,
    fieldName: string,
    filename: string,
    binaryData: ArrayBuffer,
    mimeType?: string,
  ): Promise<string | null>;
  getPlantTypeUuid(farmosName: string): Promise<string | null>;
}

/**
 * Attach a list of media files to a farmOS log, recording every outcome
 * into the PhotoPipelineReport. Returns the list of successfully
 * uploaded file UUIDs so the caller can attach them elsewhere if needed.
 *
 * Every failure mode is captured in report.upload_errors — NO silent
 * returns. Photo failures still do not block the import; they are
 * visible in the response instead of invisible.
 */
export async function uploadMediaToLog(
  client: PhotoUploadClient,
  logType: string,
  logId: string,
  files: any[],
  report: PhotoPipelineReport,
  contextLabel = '',
): Promise<string[]> {
  const uploaded: string[] = [];
  if (!logId) {
    report.upload_errors.push(`${contextLabel}: missing log id`);
    return uploaded;
  }
  if (!files || files.length === 0) return uploaded;

  for (const f of files) {
    const decoded = decodeMediaFile(f);
    if (!decoded) {
      report.decode_failures += 1;
      report.upload_errors.push(`${contextLabel}: decode_failed (${f?.filename ?? 'unknown'})`);
      continue;
    }
    try {
      const id = await client.uploadFile(
        `log/${logType}`,
        logId,
        'image',
        decoded.filename,
        decoded.bytes,
        decoded.mimeType,
      );
      if (id) {
        uploaded.push(id);
        report.photos_uploaded += 1;
      } else {
        // uploadFile returned null — file may still have landed in
        // farmOS but we lost the id. Log loudly so the operator sees it.
        report.upload_errors.push(
          `${contextLabel}: upload_returned_null (${decoded.filename})`,
        );
      }
    } catch (err: any) {
      // Continue the loop on a per-file failure — import must not abort,
      // but the operator MUST see this.
      const msg = err?.message ?? String(err);
      report.upload_errors.push(
        `${contextLabel}: upload_threw (${decoded.filename}): ${msg}`,
      );
    }
  }
  return uploaded;
}

/**
 * Refresh the plant_type taxonomy reference photo for a species
 * (latest-wins). Only the first decodable file is used. Returns the
 * uploaded file UUID or null.
 *
 * Unlike `uploadMediaToLog`, this is a QUALITY decision — it's only
 * called after PlantNet verification confirmed the photo matches the
 * claimed species. A null return here is not an error per se, just
 * "don't promote".
 */
export async function updateSpeciesReferencePhoto(
  client: PhotoUploadClient,
  species: string,
  files: any[],
): Promise<string | null> {
  if (!species || !files || files.length === 0) return null;
  let uuid: string | null = null;
  try {
    uuid = await client.getPlantTypeUuid(species);
  } catch {
    return null;
  }
  if (!uuid) return null;
  for (const f of files) {
    const decoded = decodeMediaFile(f);
    if (!decoded) continue;
    try {
      return await client.uploadFile(
        'taxonomy_term/plant_type',
        uuid,
        'image',
        decoded.filename,
        decoded.bytes,
        decoded.mimeType,
      );
    } catch {
      return null;
    }
  }
  return null;
}
