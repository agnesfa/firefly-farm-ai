/**
 * Client factory functions.
 *
 * farmOS auth is now framework-managed (ADR 0010): the FA framework's
 * FarmOSPlatformAuthHandler runs the OAuth2 password grant at session
 * creation, stores the token in the unified session store, and surfaces
 * it to tool handlers as `extra.authInfo.token`. This factory consumes
 * that token plus the farmUrl from `extra.authInfo.clientMetadata.farmUrl`,
 * and wires up `createAuthRefreshCallback(extra)` for in-flight 401 recovery.
 *
 * Each call constructs a fresh FarmOSClient (no singleton) — cheap, and
 * avoids any stale-token risk between sessions/users.
 *
 * User identity (userName) comes from credentials.json metadata via
 * `extra.authInfo.metadata.userName` or `extra.authInfo.clientMetadata.userName`.
 *
 * Apps Script endpoints (Observe/Memory/PlantTypes/Knowledge) still come
 * from server-level env vars — they're shared infrastructure, not per-tenant.
 */

import { createAuthRefreshCallback } from '@fireflyagents/mcp-server-core';
import { createHttpClient } from '@fireflyagents/mcp-shared-utils';
import { FarmOSClient } from './farmos-client.js';
import { parseApiVersion } from './api-version.js';
import { ObservationClient } from './observe-client.js';
import { MemoryClient } from './memory-client.js';
import { PlantTypesClient } from './plant-types-client.js';
import { KnowledgeClient } from './knowledge-client.js';

export { FarmOSClient } from './farmos-client.js';
export { ObservationClient } from './observe-client.js';
export { MemoryClient } from './memory-client.js';
export { PlantTypesClient } from './plant-types-client.js';
export { KnowledgeClient } from './knowledge-client.js';

/**
 * Get a FarmOS client from the framework auth context (extra.authInfo).
 *
 * The framework's `injectAuthContext` (request-helpers.js) renames
 * `authContext.clientMetadata` to `req.auth.metadata` when populating
 * the request — so `extra.authInfo.metadata` (NOT clientMetadata) is
 * the correct path for tool handlers. The fallback to clientMetadata
 * covers older framework versions and direct test contexts.
 *
 * Throws with a clear message if extra is missing the access token or farmUrl —
 * usually caused by a credentials.json entry that lacks `metadata.farmUrl` or
 * `platformCredentials.{username,password}` (see ADR 0010 §Implementation).
 *
 * Constructs a new framework HttpClient per call (no singleton). The
 * HttpClient holds the bearer token in default headers and uses
 * `onUnauthorized: createAuthRefreshCallback(extra)` so a mid-session 401
 * triggers transparent re-auth via the axios interceptor. FarmOSClient is
 * stateless w.r.t. auth — it just consumes the configured HttpClient.
 */
export function getFarmOSClient(extra?: any): FarmOSClient {
  const accessToken = extra?.authInfo?.token;
  const farmUrl =
    extra?.authInfo?.metadata?.farmUrl
    ?? extra?.authInfo?.clientMetadata?.farmUrl;

  if (!accessToken) {
    throw new Error(
      'farmOS access token missing from extra.authInfo.token. ' +
        'The framework PlatformAuthHandler did not run — check the credentials.json ' +
        'entry for this tenant has a populated platformCredentials block.',
    );
  }
  if (!farmUrl) {
    throw new Error(
      'farmOS farmUrl missing from extra.authInfo.metadata.farmUrl. ' +
        'Add metadata.farmUrl to the credentials.json entry for this tenant.',
    );
  }

  const baseURL = farmUrl.replace(/\/+$/, '');
  const httpClient = createHttpClient({
    baseURL,
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/vnd.api+json',
      Accept: 'application/vnd.api+json',
    },
    onUnauthorized: createAuthRefreshCallback(extra),
  });

  // FARMOS_API_VERSION is a server-level flag (see ADR 0009): default '3'
  // (margregen pre-cutover); flipped to '4' on Railway after Mike upgrades.
  const apiVersion = parseApiVersion(process.env.FARMOS_API_VERSION);

  return new FarmOSClient({ farmUrl, httpClient, apiVersion });
}

/**
 * Get userName from auth context metadata (credentials.json).
 * Falls back to FARMOS_DEFAULT_USER env var, then 'Unknown'.
 */
export function getUserName(extra?: any): string {
  return extra?.authInfo?.metadata?.userName
    ?? extra?.authInfo?.clientMetadata?.userName
    ?? process.env.FARMOS_DEFAULT_USER
    ?? 'Unknown';
}

/**
 * Get the human-readable farm name from auth context metadata
 * (credentials.json `metadata.farmName`). Use this for any tool output
 * that mentions "your farm" — forward-compatible with the multi-farm
 * future where each tenant has its own farmOS instance and display name.
 *
 * Note: `farmName` is a label for humans; the source-of-truth identifier
 * is `metadata.farmUrl` which determines which farmOS instance auth +
 * API calls target.
 *
 * Falls back to clientMetadata path (older framework) then 'Unknown Farm'.
 */
export function getFarmName(extra?: any): string {
  return extra?.authInfo?.metadata?.farmName
    ?? extra?.authInfo?.clientMetadata?.farmName
    ?? 'Unknown Farm';
}

/** Get an observation client from env vars. Returns null if not configured. */
export function getObserveClient(): ObservationClient | null {
  const endpoint = process.env.OBSERVE_ENDPOINT;
  if (!endpoint) return null;
  return new ObservationClient(endpoint);
}

/** Get a memory client from env vars. Returns null if not configured. */
export function getMemoryClient(): MemoryClient | null {
  const endpoint = process.env.MEMORY_ENDPOINT;
  if (!endpoint) return null;
  return new MemoryClient(endpoint);
}

/** Get a plant types client from env vars. Returns null if not configured. */
export function getPlantTypesClient(): PlantTypesClient | null {
  const endpoint = process.env.PLANT_TYPES_ENDPOINT;
  if (!endpoint) return null;
  return new PlantTypesClient(endpoint);
}

/** Get a knowledge client from env vars. Returns null if not configured. */
export function getKnowledgeClient(): KnowledgeClient | null {
  const endpoint = process.env.KNOWLEDGE_ENDPOINT;
  if (!endpoint) return null;
  return new KnowledgeClient(endpoint);
}
