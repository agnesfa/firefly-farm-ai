/**
 * Unwrap helpers for Apps Script client responses.
 *
 * The Apps Script clients (MemoryClient.readActivity, KnowledgeClient.listEntries)
 * return wrapper objects like {success, summaries: [...], count} and
 * {success, entries: [...], total}. A prior implementation checked
 * `Array.isArray(x) ? x.length : 0` and silently short-circuited to 0,
 * making `system_health` report the Team dimension as permanently dormant.
 *
 * These helpers tolerate both shapes so that future client refactors can
 * return either a bare array or the wrapper dict without breaking metrics.
 */

/** Extract the summaries array from a MemoryClient.readActivity response. */
export function extractMemorySummaries(resp: unknown): any[] {
  if (Array.isArray(resp)) return resp;
  if (resp && typeof resp === 'object') {
    const summaries = (resp as any).summaries;
    if (Array.isArray(summaries)) return summaries;
  }
  return [];
}

/** Count KB entries from a KnowledgeClient.listEntries response. */
export function countKbEntries(resp: unknown): number {
  if (Array.isArray(resp)) return resp.length;
  if (resp && typeof resp === 'object') {
    const obj = resp as any;
    if (typeof obj.total === 'number') return obj.total;
    if (Array.isArray(obj.entries)) return obj.entries.length;
  }
  return 0;
}
