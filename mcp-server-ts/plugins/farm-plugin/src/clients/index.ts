/**
 * Client factory functions.
 *
 * farmOS credentials come from server-level env vars (FARMOS_URL, FARMOS_USERNAME,
 * FARMOS_PASSWORD) because all users share the same farmOS account and the FA Framework
 * only injects auth context (extra.authInfo) when a platform OAuth handler is configured.
 * Without a platform handler, extra.authInfo is undefined — so env vars are the reliable path.
 *
 * User identity (userName) comes from credentials.json metadata via extra.authInfo.
 * Apps Script endpoints come from server-level env vars.
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
 * Get a FarmOS client from server-level env vars.
 *
 * farmOS credentials are shared across all users (single farmOS account),
 * so they live as env vars rather than per-user auth context.
 * Uses singleton pattern — one client per farmUrl.
 */
export function getFarmOSClient(_extra?: any): FarmOSClient {
  const farmUrl = process.env.FARMOS_URL;
  const username = process.env.FARMOS_USERNAME;
  const password = process.env.FARMOS_PASSWORD;

  if (!farmUrl || !username || !password) {
    throw new Error(
      'FarmOS credentials not found. Set FARMOS_URL, FARMOS_USERNAME, and FARMOS_PASSWORD env vars.',
    );
  }

  return FarmOSClient.getInstance({ farmUrl, username, password });
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
