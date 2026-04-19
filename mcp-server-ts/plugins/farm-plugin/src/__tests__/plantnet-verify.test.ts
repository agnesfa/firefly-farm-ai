/**
 * Tests for plantnet-verify helper.
 *
 * Primary purpose: verify that the Origin header is sent on every
 * PlantNet request, matching an authorised domain from the API key's
 * allowlist. Without this, PlantNet returns HTTP 403 for any call from
 * an IP not on the allowlist — which silently breaks Railway if its
 * outbound IP changes, plus all local/CI invocations.
 * See reference_plantnet_cors.md memory.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  verifySpeciesPhoto,
  buildBotanicalLookup,
  resetPlantnetCallCount,
} from '../helpers/plantnet-verify.js';

const lookup = buildBotanicalLookup([
  { name: 'Pigeon Pea', botanical_name: 'Cajanus cajan' },
]);

const fakeImageBytes = Buffer.from([0xff, 0xd8, 0xff]);

describe('verifySpeciesPhoto', () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    resetPlantnetCallCount();
    fetchSpy = vi.fn();
    globalThis.fetch = fetchSpy as any;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('sends Origin header on every PlantNet request', async () => {
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ results: [] }),
    });

    await verifySpeciesPhoto(fakeImageBytes, 'Pigeon Pea', lookup, 'test-key');

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [, init] = fetchSpy.mock.calls[0];
    const headers = (init?.headers ?? {}) as Record<string, string>;
    expect(headers.Origin).toBe('https://agnesfa.github.io');
  });

  it('returns verified=true for a top-match above threshold', async () => {
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        results: [
          { species: { scientificNameWithoutAuthor: 'Cajanus cajan' }, score: 0.72 },
        ],
      }),
    });

    const result = await verifySpeciesPhoto(fakeImageBytes, 'Pigeon Pea', lookup, 'test-key');
    expect(result.verified).toBe(true);
    expect(result.confidence).toBe(0.72);
  });

  it('returns verified=false with HTTP 403 reason on CORS rejection', async () => {
    fetchSpy.mockResolvedValueOnce({
      ok: false,
      status: 403,
      text: async () => 'CORS error: Origin not allowed',
    });

    const result = await verifySpeciesPhoto(fakeImageBytes, 'Pigeon Pea', lookup, 'test-key');
    expect(result.verified).toBe(false);
    expect(result.reason).toBe('api_http_403');
  });
});
