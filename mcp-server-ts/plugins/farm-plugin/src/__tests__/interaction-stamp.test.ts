/**
 * Tests for InteractionStamp — ontology-linked provenance metadata.
 *
 * Pure function tests — no I/O, no mocking needed.
 */

import { describe, it, expect } from 'vitest';
import {
  buildStamp,
  appendStamp,
  hasStamp,
  parseStamp,
  countStampsInLogs,
  buildMcpStamp,
} from '../helpers/interaction-stamp.js';
import type { StampFields } from '../helpers/interaction-stamp.js';

const BASE_FIELDS: StampFields = {
  initiator: 'Agnes',
  role: 'manager',
  channel: 'claude_code',
  executor: 'farmos_api',
  action: 'created',
  target: 'plant',
};

// ── buildStamp ──────────────────────────────────────────────

describe('buildStamp', () => {
  it('produces [ontology:InteractionStamp] prefix', () => {
    const stamp = buildStamp(BASE_FIELDS);
    expect(stamp).toContain('[ontology:InteractionStamp]');
  });

  it('includes all required fields', () => {
    const stamp = buildStamp(BASE_FIELDS);
    expect(stamp).toContain('initiator=Agnes');
    expect(stamp).toContain('role=manager');
    expect(stamp).toContain('channel=claude_code');
    expect(stamp).toContain('executor=farmos_api');
    expect(stamp).toContain('action=created');
    expect(stamp).toContain('target=plant');
    expect(stamp).toContain('outcome=success');
    expect(stamp).toMatch(/ts=\d{4}-\d{2}-\d{2}T/);
  });

  it('defaults outcome to success', () => {
    const stamp = buildStamp(BASE_FIELDS);
    expect(stamp).toContain('outcome=success');
  });

  it('includes optional fields when provided', () => {
    const stamp = buildStamp({
      ...BASE_FIELDS,
      outcome: 'timeout',
      errorDetail: 'MCP server timeout after 30s',
      relatedEntities: ['Pigeon Pea', 'P2R5.29-38'],
      sessionId: 'sess-123',
      sourceSubmission: 'sub-456',
      confidence: 0.85,
    });
    expect(stamp).toContain('outcome=timeout');
    expect(stamp).toContain('error=MCP server timeout after 30s');
    expect(stamp).toContain('related=Pigeon Pea,P2R5.29-38');
    expect(stamp).toContain('session=sess-123');
    expect(stamp).toContain('submission=sub-456');
    expect(stamp).toContain('confidence=0.85');
  });

  it('omits optional fields when not provided', () => {
    const stamp = buildStamp(BASE_FIELDS);
    expect(stamp).not.toContain('error=');
    expect(stamp).not.toContain('related=');
    expect(stamp).not.toContain('session=');
    expect(stamp).not.toContain('submission=');
    expect(stamp).not.toContain('confidence=');
  });
});

// ── appendStamp ─────────────────────────────────────────────

describe('appendStamp', () => {
  it('returns stamp alone when notes empty', () => {
    const stamp = buildStamp(BASE_FIELDS);
    expect(appendStamp('', stamp)).toBe(stamp);
    expect(appendStamp(null, stamp)).toBe(stamp);
    expect(appendStamp(undefined, stamp)).toBe(stamp);
  });

  it('appends after existing notes with newline', () => {
    const stamp = buildStamp(BASE_FIELDS);
    const result = appendStamp('Some existing notes', stamp);
    expect(result).toContain('Some existing notes\n');
    expect(result).toContain('[ontology:InteractionStamp]');
  });
});

// ── hasStamp ────────────────────────────────────────────────

describe('hasStamp', () => {
  it('detects stamp in notes', () => {
    const stamp = buildStamp(BASE_FIELDS);
    expect(hasStamp(stamp)).toBe(true);
    expect(hasStamp(`Notes here\n${stamp}`)).toBe(true);
  });

  it('returns false for notes without stamp', () => {
    expect(hasStamp('Regular notes')).toBe(false);
    expect(hasStamp('')).toBe(false);
    expect(hasStamp(null)).toBe(false);
    expect(hasStamp(undefined)).toBe(false);
  });

  it('does not false-positive on partial prefix', () => {
    expect(hasStamp('[ontology:Interaction] something')).toBe(false);
  });
});

// ── parseStamp ──────────────────────────────────────────────

describe('parseStamp', () => {
  it('parses all required fields', () => {
    const stamp = buildStamp(BASE_FIELDS);
    const parsed = parseStamp(stamp);
    expect(parsed).not.toBeNull();
    expect(parsed!.initiator).toBe('Agnes');
    expect(parsed!.role).toBe('manager');
    expect(parsed!.channel).toBe('claude_code');
    expect(parsed!.executor).toBe('farmos_api');
    expect(parsed!.action).toBe('created');
    expect(parsed!.target).toBe('plant');
  });

  it('parses optional fields', () => {
    const stamp = buildStamp({
      ...BASE_FIELDS,
      outcome: 'failed',
      errorDetail: 'timeout',
      relatedEntities: ['Okra', 'P2R5.22-29'],
      confidence: 0.42,
    });
    const parsed = parseStamp(stamp);
    expect(parsed!.outcome).toBe('failed');
    expect(parsed!.errorDetail).toBe('timeout');
    expect(parsed!.relatedEntities).toEqual(['Okra', 'P2R5.22-29']);
    expect(parsed!.confidence).toBeCloseTo(0.42);
  });

  it('returns null for notes without stamp', () => {
    expect(parseStamp('Just some notes')).toBeNull();
    expect(parseStamp(null)).toBeNull();
  });

  it('parses stamp embedded in longer notes', () => {
    const stamp = buildStamp(BASE_FIELDS);
    const notes = `Created plant asset for Pigeon Pea.\n${stamp}\nMore notes below.`;
    const parsed = parseStamp(notes);
    expect(parsed!.initiator).toBe('Agnes');
    expect(parsed!.target).toBe('plant');
  });
});

// ── countStampsInLogs ───────────────────────────────────────

describe('countStampsInLogs', () => {
  it('counts stamped vs total logs', () => {
    const stamp = buildStamp(BASE_FIELDS);
    const logs = [
      { notes: stamp },
      { notes: 'no stamp here' },
      { notes: `some notes\n${stamp}` },
    ];
    const result = countStampsInLogs(logs);
    expect(result.stamped).toBe(2);
    expect(result.total).toBe(3);
    expect(result.coverage).toBeCloseTo(0.667, 2);
  });

  it('handles object-style notes (farmOS format)', () => {
    const stamp = buildStamp(BASE_FIELDS);
    const logs = [{ notes: { value: stamp } }];
    const result = countStampsInLogs(logs);
    expect(result.stamped).toBe(1);
  });

  it('returns 0 coverage for empty list', () => {
    const result = countStampsInLogs([]);
    expect(result.coverage).toBe(0);
  });
});

// ── buildMcpStamp ───────────────────────────────────────────

describe('buildMcpStamp', () => {
  it('defaults to Claude_user / manager / claude_session / farmos_api', () => {
    const stamp = buildMcpStamp('created', 'observation');
    expect(stamp).toContain('initiator=Claude_user');
    expect(stamp).toContain('role=manager');
    expect(stamp).toContain('channel=claude_session');
    expect(stamp).toContain('executor=farmos_api');
  });

  it('uses provided initiator', () => {
    const stamp = buildMcpStamp('created', 'knowledge', { initiator: 'Claire', executor: 'apps_script' });
    expect(stamp).toContain('initiator=Claire');
    expect(stamp).toContain('executor=apps_script');
  });

  it('passes related entities through', () => {
    const stamp = buildMcpStamp('created', 'plant', { relatedEntities: ['Pigeon Pea', 'P2R3.15-21'] });
    expect(stamp).toContain('related=Pigeon Pea,P2R3.15-21');
  });
});
