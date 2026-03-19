/**
 * Client factory functions — resolve clients from auth context or env vars.
 *
 * In the FA Framework, credentials flow through the auth context per-tenant.
 * Shared endpoints (Apps Script) come from server-level env vars.
 */

import { FarmOSClient } from './farmos-client.js';
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
 * Get a FarmOS client from the tool handler's auth context.
 * Uses singleton pattern — one client per farmUrl.
 */
export function getFarmOSClient(extra?: any): FarmOSClient {
  const auth = extra?.auth;
  const farmUrl = auth?.clientMetadata?.farmUrl;
  const creds = auth?.platformCredentials?.credentials;

  if (!farmUrl || !creds?.username || !creds?.password) {
    throw new Error(
      'FarmOS credentials not found in auth context. ' +
      'Ensure credentials.json has farmUrl in metadata and username/password in credentials.',
    );
  }

  return FarmOSClient.getInstance({
    farmUrl,
    username: creds.username,
    password: creds.password,
  });
}

/** Get userName from auth context metadata. */
export function getUserName(extra?: any): string {
  return extra?.auth?.clientMetadata?.userName ?? 'Unknown';
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
