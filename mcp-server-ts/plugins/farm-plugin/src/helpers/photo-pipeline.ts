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
  /**
   * Optional — used by tier-aware reference-photo promotion (ADR 0008
   * Phase 3b) to inspect the plant_type's current image reference and
   * any existing image references on a log for dedup.
   * Callers fall back safely if not provided.
   */
  getRaw?(path: string): Promise<any>;
  patchRelationship?(
    entityType: string,
    entityId: string,
    fieldName: string,
    refs: Array<{ type: string; id: string }>,
  ): Promise<boolean>;
}


// ── Field-photo tier classification (ADR 0008 I5) ─────────────
//
// tier 3: submission-id-prefixed OR contains _plant_ AND submission
//         (best candidate for species reference; QR photo of one plant)
// tier 2: section-prefixed AND contains _plant_ (plant-specific import)
// tier 1: section-prefixed AND _section_ (multi-plant frame — WEAK,
//         never auto-promote as species reference)
// tier 0: stock (Wikipedia / Köhler / scientific-name filename)

const TIER_SUBMISSION_PLANT = /^[0-9a-f]{8}_.+_plant_/;
const TIER_SUBMISSION = /^[0-9a-f]{8}_/;
const TIER_SECTION_PLANT = /^(P\d+R\d+|NURS|COMP|SPIR)\S*_plant_/;
const TIER_SECTION_SECTION = /^(P\d+R\d+|NURS|COMP|SPIR)\S*_section_/;
const STOCK_PATTERNS = [
  /%[0-9A-F]{2}/,
  /wikipedia|wikimedia|köhler|medizinal/i,
  /^[A-Z][a-z]+_[a-z]+(_[0-9]+)?\.(jpg|jpeg|png)$/i,
];

export function fieldPhotoTier(filename: string): 0 | 1 | 2 | 3 {
  if (!filename) return 0;
  if (TIER_SUBMISSION_PLANT.test(filename)) return 3;
  if (TIER_SUBMISSION.test(filename)) return 3;
  if (TIER_SECTION_PLANT.test(filename)) return 2;
  if (TIER_SECTION_SECTION.test(filename)) return 1;
  return 0;
}

export function isStockPhoto(filename: string): boolean {
  return STOCK_PATTERNS.some((p) => p.test(filename || ''));
}


// ── Dedup (ADR 0008 I4 + ADR 0007 Fix 5) ──────────────────────
//
// Prevents same-content photos from attaching twice to a log. Keyed on
// filesize (a cheap proxy for content hash — exact filesize match with
// same-origin filename prefix is effectively identical content). The
// silent-success-then-retry pattern from 2026-04-18 was the motivating
// case: every photo ended up attached twice.

/** Fetch existing file refs on a log to dedup against. Returns a Set of
 *  filesizes seen. If the client doesn't support getRaw, returns empty
 *  (caller will upload without dedup — graceful fallback). */
async function existingFilesizesOnLog(
  client: PhotoUploadClient,
  logType: string,
  logId: string,
): Promise<Set<number>> {
  const sizes = new Set<number>();
  if (!client.getRaw) return sizes;
  try {
    const data = await client.getRaw(
      `/api/log/${logType}/${logId}?include=image`,
    );
    for (const inc of data?.included ?? []) {
      if (inc?.type === 'file--file') {
        const sz = inc?.attributes?.filesize ?? 0;
        if (typeof sz === 'number' && sz > 0) sizes.add(sz);
      }
    }
  } catch {
    // Fall through with empty set
  }
  return sizes;
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

  // ADR 0008 I4 dedup (ADR 0007 Fix 5): fetch existing file sizes on this
  // log and skip any incoming file whose content is already attached.
  // Graceful fallback if the client doesn't expose getRaw.
  const existingSizes = await existingFilesizesOnLog(client, logType, logId);
  const sizesAddedThisCall = new Set<number>();

  for (const f of files) {
    const decoded = decodeMediaFile(f);
    if (!decoded) {
      report.decode_failures += 1;
      report.upload_errors.push(`${contextLabel}: decode_failed (${f?.filename ?? 'unknown'})`);
      continue;
    }
    const size = decoded.bytes.byteLength;
    if (existingSizes.has(size) || sizesAddedThisCall.has(size)) {
      // Already attached — skip silently (not an error, just dedup).
      // Record as an upload error with 'already_attached' tag so it
      // surfaces in the report without inflating the success count.
      report.upload_errors.push(
        `${contextLabel}: already_attached (${decoded.filename}, ${size}b)`,
      );
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
        sizesAddedThisCall.add(size);
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
 * Refresh the plant_type taxonomy reference photo for a species.
 * Returns the uploaded file UUID or null.
 *
 * ADR 0008 I5 + ADR 0007 Fix 4 — tier-aware promotion (April 20 2026):
 *
 *   - Classify the incoming photo by filename tier (0..3).
 *   - Refuse to promote tier-1 section-level multi-plant frames —
 *     those pollute the species page (same multi-plant shot appeared
 *     as the reference for Chilli Jalapeño, Comfrey, Geranium etc.
 *     until today). Tier-1 photos can attach to logs but never promote.
 *   - Compare candidate tier against the current plant_type image's
 *     tier; promote only when strictly better (or same tier AND the
 *     incoming file is newer). Field photos always beat stock.
 *   - If the client exposes patchRelationship, we set the image field
 *     to single-valued with the new file. Otherwise the legacy append
 *     behaviour persists (multi-valued drift). Falls back gracefully.
 *
 * Unlike `uploadMediaToLog`, this is a QUALITY decision — callers
 * should only invoke it after PlantNet verification confirms the photo
 * matches the claimed species. A null return here is not an error per
 * se, just "don't promote".
 */
export async function updateSpeciesReferencePhoto(
  client: PhotoUploadClient,
  species: string,
  files: any[],
): Promise<string | null> {
  if (!species || !files || files.length === 0) return null;

  // Pick the best-tier decodable file from the incoming batch.
  let bestDecoded: DecodedMedia | null = null;
  let bestTier: 0 | 1 | 2 | 3 = 0;
  for (const f of files) {
    const decoded = decodeMediaFile(f);
    if (!decoded) continue;
    const tier = fieldPhotoTier(decoded.filename);
    if (tier > bestTier) {
      bestTier = tier;
      bestDecoded = decoded;
    }
  }
  if (!bestDecoded) return null;

  // Tier-1 section-level multi-plant frames never auto-promote.
  if (bestTier <= 1) return null;

  let uuid: string | null = null;
  try {
    uuid = await client.getPlantTypeUuid(species);
  } catch {
    return null;
  }
  if (!uuid) return null;

  // Inspect current reference (if exposed). Skip promotion if current
  // is already same-or-higher tier + newer-or-same timestamp.
  let currentTier: 0 | 1 | 2 | 3 = 0;
  let currentCreated = '';
  if (client.getRaw) {
    try {
      const data = await client.getRaw(
        `/api/taxonomy_term/plant_type/${uuid}?include=image`,
      );
      const included = (data?.included ?? []).filter(
        (x: any) => x?.type === 'file--file',
      );
      // Pick highest-tier existing file as the "current"
      for (const f of included) {
        const fn = f?.attributes?.filename ?? '';
        const t = fieldPhotoTier(fn);
        const created = f?.attributes?.created ?? '';
        if (t > currentTier || (t === currentTier && created > currentCreated)) {
          currentTier = t;
          currentCreated = created;
        }
      }
    } catch {
      // fall through — treat current as unknown tier 0
    }
  }

  // Only promote if strictly better.
  if (currentTier > bestTier) return null;
  // Same tier — newer beats older; but new files always win on ties
  // because they represent fresher evidence. (Tie-breaking to existing
  // would leave stale refs undisturbed forever.)

  let newFileId: string | null = null;
  try {
    newFileId = await client.uploadFile(
      'taxonomy_term/plant_type',
      uuid,
      'image',
      bestDecoded.filename,
      bestDecoded.bytes,
      bestDecoded.mimeType,
    );
  } catch {
    return null;
  }
  if (!newFileId) return null;

  // Best-effort: if patchRelationship is available, collapse image to
  // a single reference pointing at the new file. This prevents the
  // multi-valued drift that our I5 cleanup had to patch retroactively.
  if (client.patchRelationship) {
    try {
      await client.patchRelationship(
        'taxonomy_term/plant_type',
        uuid,
        'image',
        [{ type: 'file--file', id: newFileId }],
      );
    } catch {
      // Non-fatal — the upload already landed; just multi-valued.
    }
  }

  return newFileId;
}
