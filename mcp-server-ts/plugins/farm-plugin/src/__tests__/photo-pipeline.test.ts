/**
 * Unit tests for the photo pipeline helpers.
 *
 * These helpers are the TypeScript port of the Python
 * _decode_media_file / _upload_media_to_log / _update_species_reference_photo
 * functions in mcp-server/server.py. They are exercised end-to-end by the
 * import-workflow test suite, but it's useful to pin the decode behaviour
 * independently so regressions show up in the smallest possible test.
 */

import { describe, it, expect, vi } from 'vitest';
import {
  decodeMediaFile,
  uploadMediaToLog,
  updateSpeciesReferencePhoto,
} from '../helpers/photo-pipeline.js';

const TINY_PNG_B64 =
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';

describe('decodeMediaFile', () => {
  it('decodes a plain base64 payload', () => {
    const result = decodeMediaFile({
      filename: 'photo.jpg',
      mime_type: 'image/jpeg',
      data_base64: TINY_PNG_B64,
    });
    expect(result).not.toBeNull();
    expect(result!.filename).toBe('photo.jpg');
    expect(result!.mimeType).toBe('image/jpeg');
    expect(result!.bytes.byteLength).toBeGreaterThan(0);
  });

  it('strips a data: URL prefix before decoding', () => {
    const result = decodeMediaFile({
      filename: 'legacy.jpg',
      mime_type: 'image/jpeg',
      data_base64: `data:image/jpeg;base64,${TINY_PNG_B64}`,
    });
    expect(result).not.toBeNull();
    expect(result!.bytes.byteLength).toBeGreaterThan(0);
  });

  it('falls back to defaults when filename / mime_type are missing', () => {
    const result = decodeMediaFile({ data_base64: TINY_PNG_B64 });
    expect(result!.filename).toBe('photo.jpg');
    expect(result!.mimeType).toBe('image/jpeg');
  });

  it('returns null for empty / missing / invalid payloads', () => {
    expect(decodeMediaFile(null)).toBeNull();
    expect(decodeMediaFile({})).toBeNull();
    expect(decodeMediaFile({ data_base64: '' })).toBeNull();
    expect(decodeMediaFile('not an object' as any)).toBeNull();
  });
});

describe('uploadMediaToLog', () => {
  it('uploads every file and returns their UUIDs', async () => {
    const client = {
      uploadFile: vi.fn().mockResolvedValueOnce('uuid-a').mockResolvedValueOnce('uuid-b'),
      getPlantTypeUuid: vi.fn(),
    };
    const ids = await uploadMediaToLog(
      client,
      'observation',
      'log-1',
      [
        { filename: 'a.jpg', mime_type: 'image/jpeg', data_base64: TINY_PNG_B64 },
        { filename: 'b.jpg', mime_type: 'image/jpeg', data_base64: TINY_PNG_B64 },
      ],
    );
    expect(ids).toEqual(['uuid-a', 'uuid-b']);
    expect(client.uploadFile).toHaveBeenCalledTimes(2);
    expect(client.uploadFile.mock.calls[0][0]).toBe('log/observation');
    expect(client.uploadFile.mock.calls[0][1]).toBe('log-1');
  });

  it('swallows upload errors so the import continues', async () => {
    const client = {
      uploadFile: vi.fn().mockRejectedValue(new Error('farmOS 500')),
      getPlantTypeUuid: vi.fn(),
    };
    const ids = await uploadMediaToLog(
      client,
      'activity',
      'log-1',
      [{ filename: 'a.jpg', mime_type: 'image/jpeg', data_base64: TINY_PNG_B64 }],
    );
    expect(ids).toEqual([]);
  });

  it('short-circuits on empty inputs', async () => {
    const client = { uploadFile: vi.fn(), getPlantTypeUuid: vi.fn() };
    expect(await uploadMediaToLog(client, 'activity', '', [])).toEqual([]);
    expect(await uploadMediaToLog(client, 'activity', 'log-1', [])).toEqual([]);
    expect(client.uploadFile).not.toHaveBeenCalled();
  });
});

describe('updateSpeciesReferencePhoto', () => {
  it('uploads only the first decodable file to the taxonomy term', async () => {
    const client = {
      uploadFile: vi.fn().mockResolvedValue('file-uuid'),
      getPlantTypeUuid: vi.fn().mockResolvedValue('pt-uuid'),
    };
    const id = await updateSpeciesReferencePhoto(client, 'Pigeon Pea', [
      { filename: 'first.jpg', mime_type: 'image/jpeg', data_base64: TINY_PNG_B64 },
      { filename: 'second.jpg', mime_type: 'image/jpeg', data_base64: TINY_PNG_B64 },
    ]);
    expect(id).toBe('file-uuid');
    expect(client.uploadFile).toHaveBeenCalledTimes(1);
    expect(client.uploadFile.mock.calls[0][0]).toBe('taxonomy_term/plant_type');
    expect(client.uploadFile.mock.calls[0][1]).toBe('pt-uuid');
  });

  it('returns null when the species has no taxonomy term', async () => {
    const client = {
      uploadFile: vi.fn(),
      getPlantTypeUuid: vi.fn().mockResolvedValue(null),
    };
    const id = await updateSpeciesReferencePhoto(client, 'Unknown Species', [
      { filename: 'first.jpg', mime_type: 'image/jpeg', data_base64: TINY_PNG_B64 },
    ]);
    expect(id).toBeNull();
    expect(client.uploadFile).not.toHaveBeenCalled();
  });

  it('returns null on missing species or empty files', async () => {
    const client = { uploadFile: vi.fn(), getPlantTypeUuid: vi.fn() };
    expect(await updateSpeciesReferencePhoto(client, '', [])).toBeNull();
    expect(await updateSpeciesReferencePhoto(client, 'Pigeon Pea', [])).toBeNull();
  });
});
