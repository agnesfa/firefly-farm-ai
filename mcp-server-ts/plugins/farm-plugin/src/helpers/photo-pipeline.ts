/**
 * Photo pipeline helpers for import_observations.
 *
 * Mirrors mcp-server/server.py's _decode_media_file, _upload_media_to_log
 * and _update_species_reference_photo. Ported so the Railway TypeScript
 * server attaches photos to farmOS logs on import, matching the Python
 * behaviour. See claude-docs/photo-pipeline-and-plant-id-design.md.
 */

/** A decoded media file ready for farmOS upload. */
export interface DecodedMedia {
  filename: string;
  mimeType: string;
  bytes: ArrayBuffer;
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
 * Attach a list of media files to a farmOS log. Returns the list of
 * successfully uploaded file UUIDs. Errors are swallowed — photo
 * failures must never block an observation import.
 */
export async function uploadMediaToLog(
  client: PhotoUploadClient,
  logType: string,
  logId: string,
  files: any[],
): Promise<string[]> {
  const uploaded: string[] = [];
  if (!logId || !files || files.length === 0) return uploaded;
  for (const f of files) {
    const decoded = decodeMediaFile(f);
    if (!decoded) continue;
    try {
      const id = await client.uploadFile(
        `log/${logType}`,
        logId,
        'image',
        decoded.filename,
        decoded.bytes,
        decoded.mimeType,
      );
      if (id) uploaded.push(id);
    } catch {
      // Continue — do not block the import on a failed upload.
    }
  }
  return uploaded;
}

/**
 * Refresh the plant_type taxonomy reference photo for a species
 * (latest-wins). Only the first decodable file is used. Returns the
 * uploaded file UUID or null.
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
