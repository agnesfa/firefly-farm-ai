/**
 * InteractionStamp — ontology-linked provenance metadata.
 *
 * Every MCP write tool must produce a stamp. Without a stamp, a change
 * is untraceable and untrusted. The stamp feeds system_health metrics:
 *   - provenance_coverage: count(logs with stamp) / count(all recent logs)
 *   - source_conflict_count: count(stamps with outcome=conflict)
 *   - entity_touch_rate: avg(related_entities.length) per stamp
 *   - mcp_reliability: success / total attempts
 *
 * Dual-actor design: most interactions have a human initiator (who has
 * intent and trust) and a system executor (which has a channel chain
 * and an outcome). Both are captured.
 *
 * @see knowledge/farm_ontology.yaml — InteractionStamp entity
 */

// ── Types linked to ontology ─────────────────────────────────

export type Channel =
  | 'claude_code'
  | 'claude_desktop'
  | 'claude_session'    // when we can't distinguish code vs desktop
  | 'qr_page'
  | 'farmos_ui'
  | 'automated';

export type Executor =
  | 'farmos_api'
  | 'apps_script'
  | 'mcp_tool'
  | 'plantnet_api'
  | 'wikimedia_api';

export type StampAction =
  | 'created'
  | 'updated'
  | 'archived'
  | 'verified'
  | 'rejected'
  | 'attempted';

export type TargetEntity =
  | 'plant'
  | 'observation'
  | 'activity'
  | 'knowledge'
  | 'seed'
  | 'plant_type'
  | 'session_summary';

export type Outcome = 'success' | 'failed' | 'partial' | 'timeout' | 'conflict';

export type InitiatorRole = 'manager' | 'farmhand' | 'visitor' | 'system';

export interface StampFields {
  initiator: string;
  role: InitiatorRole;
  channel: Channel;
  executor: Executor;
  action: StampAction;
  target: TargetEntity;
  outcome?: Outcome;
  errorDetail?: string;
  relatedEntities?: string[];
  sessionId?: string;
  sourceSubmission?: string;
  confidence?: number;
}

// ── Stamp prefix — links to ontology definition ──────────────

const STAMP_PREFIX = '[ontology:InteractionStamp]';

// ── Build / Append / Parse ───────────────────────────────────

/**
 * Build a stamp string from structured fields.
 * Format: [ontology:InteractionStamp] key=value | key=value | ...
 */
export function buildStamp(fields: StampFields): string {
  const parts: string[] = [
    `initiator=${fields.initiator}`,
    `role=${fields.role}`,
    `channel=${fields.channel}`,
    `executor=${fields.executor}`,
    `action=${fields.action}`,
    `target=${fields.target}`,
  ];

  const outcome = fields.outcome ?? 'success';
  parts.push(`outcome=${outcome}`);

  parts.push(`ts=${new Date().toISOString()}`);

  if (fields.errorDetail) parts.push(`error=${fields.errorDetail}`);
  if (fields.relatedEntities?.length) parts.push(`related=${fields.relatedEntities.join(',')}`);
  if (fields.sessionId) parts.push(`session=${fields.sessionId}`);
  if (fields.sourceSubmission) parts.push(`submission=${fields.sourceSubmission}`);
  if (fields.confidence != null) parts.push(`confidence=${fields.confidence.toFixed(2)}`);

  return `${STAMP_PREFIX} ${parts.join(' | ')}`;
}

/**
 * Append a stamp to existing notes. Adds a separator line if notes
 * are non-empty.
 */
export function appendStamp(notes: string | undefined | null, stamp: string): string {
  const existing = (notes ?? '').trim();
  if (!existing) return stamp;
  return `${existing}\n${stamp}`;
}

/**
 * Check whether notes contain a valid InteractionStamp.
 */
export function hasStamp(notes: string | undefined | null): boolean {
  return (notes ?? '').includes(STAMP_PREFIX);
}

/**
 * Parse a stamp from notes. Returns the first stamp found, or null.
 */
export function parseStamp(notes: string | undefined | null): StampFields | null {
  const text = notes ?? '';
  const idx = text.indexOf(STAMP_PREFIX);
  if (idx === -1) return null;

  // Extract the stamp line (from prefix to end of line)
  const lineStart = idx + STAMP_PREFIX.length;
  const lineEnd = text.indexOf('\n', lineStart);
  const line = (lineEnd === -1 ? text.substring(lineStart) : text.substring(lineStart, lineEnd)).trim();

  const pairs = line.split('|').map(s => s.trim());
  const map = new Map<string, string>();
  for (const pair of pairs) {
    const eq = pair.indexOf('=');
    if (eq > 0) {
      map.set(pair.substring(0, eq).trim(), pair.substring(eq + 1).trim());
    }
  }

  const initiator = map.get('initiator');
  const action = map.get('action') as StampAction | undefined;
  const target = map.get('target') as TargetEntity | undefined;
  if (!initiator || !action || !target) return null;

  const result: StampFields = {
    initiator,
    role: (map.get('role') as InitiatorRole) ?? 'system',
    channel: (map.get('channel') as Channel) ?? 'automated',
    executor: (map.get('executor') as Executor) ?? 'mcp_tool',
    action,
    target,
  };

  const outcome = map.get('outcome') as Outcome | undefined;
  if (outcome) result.outcome = outcome;
  if (map.has('error')) result.errorDetail = map.get('error');
  if (map.has('related')) result.relatedEntities = map.get('related')!.split(',');
  if (map.has('session')) result.sessionId = map.get('session');
  if (map.has('submission')) result.sourceSubmission = map.get('submission');
  if (map.has('confidence')) result.confidence = parseFloat(map.get('confidence')!);

  return result;
}

/**
 * Count stamps in a list of logs (for provenance_coverage metric).
 * Each log must have a `notes` field (string or {value: string}).
 */
export function countStampsInLogs(logs: any[]): { stamped: number; total: number; coverage: number } {
  let stamped = 0;
  const total = logs.length;
  for (const log of logs) {
    const notes = typeof log.notes === 'object' ? log.notes?.value ?? '' : String(log.notes ?? '');
    if (hasStamp(notes)) stamped++;
  }
  return { stamped, total, coverage: total > 0 ? stamped / total : 0 };
}

// ── Convenience: default stamp for MCP tools ─────────────────

/**
 * Build a default stamp for an MCP tool invocation.
 * Uses 'Claude_user' as initiator when the human identity is unknown.
 */
export function buildMcpStamp(
  action: StampAction,
  target: TargetEntity,
  opts?: {
    initiator?: string;
    role?: InitiatorRole;
    executor?: Executor;
    relatedEntities?: string[];
    sourceSubmission?: string;
    confidence?: number;
  },
): string {
  return buildStamp({
    initiator: opts?.initiator ?? 'Claude_user',
    role: opts?.role ?? 'manager',
    channel: 'claude_session',
    executor: opts?.executor ?? 'farmos_api',
    action,
    target,
    relatedEntities: opts?.relatedEntities,
    sourceSubmission: opts?.sourceSubmission,
    confidence: opts?.confidence,
  });
}
