/**
 * Regression tests for the system_health team dimension counter bug (April 9, 2026).
 *
 * The Apps Script clients return wrapper objects like
 * {success, summaries: [...], count} and {success, entries: [...], total}.
 * A prior implementation checked `Array.isArray(x) ? x.length : 0` and
 * silently short-circuited to 0, making system_health report Team stage as
 * permanently dormant. These tests lock in the unwrap behaviour.
 */

import { describe, it, expect } from 'vitest';
import { extractMemorySummaries, countKbEntries } from '../helpers/apps-script-unwrap.js';

describe('extractMemorySummaries', () => {
  it('unwraps the Apps Script wrapper dict', () => {
    const resp = {
      success: true,
      summaries: [
        { user: 'Agnes', summary: '...' },
        { user: 'James', summary: '...' },
        { user: 'James', summary: '...' },
      ],
      count: 3,
    };
    const summaries = extractMemorySummaries(resp);
    expect(summaries).toHaveLength(3);
    expect(new Set(summaries.map((s) => s.user)).size).toBe(2);
  });

  it('passes bare arrays through unchanged', () => {
    const resp = [{ user: 'Agnes' }, { user: 'James' }];
    expect(extractMemorySummaries(resp)).toHaveLength(2);
  });

  it('returns [] for wrapper with empty summaries', () => {
    expect(extractMemorySummaries({ success: true, summaries: [], count: 0 })).toEqual([]);
  });

  it('returns [] for null/undefined', () => {
    expect(extractMemorySummaries(null)).toEqual([]);
    expect(extractMemorySummaries(undefined)).toEqual([]);
  });

  it('returns [] when the wrapper has no summaries field', () => {
    expect(extractMemorySummaries({ success: false, error: 'x' })).toEqual([]);
  });
});

describe('countKbEntries', () => {
  it('prefers `total` from the wrapper dict when present', () => {
    const resp = {
      success: true,
      entries: [{ entry_id: '1' }, { entry_id: '2' }],
      count: 2,
      total: 18,
    };
    expect(countKbEntries(resp)).toBe(18);
  });

  it('falls back to entries.length when total is absent', () => {
    const resp = {
      success: true,
      entries: Array.from({ length: 12 }, (_, i) => ({ entry_id: String(i) })),
    };
    expect(countKbEntries(resp)).toBe(12);
  });

  it('counts a bare array directly', () => {
    expect(countKbEntries([{ entry_id: '1' }, { entry_id: '2' }, { entry_id: '3' }])).toBe(3);
  });

  it('returns 0 for null/undefined/unknown shapes', () => {
    expect(countKbEntries(null)).toBe(0);
    expect(countKbEntries(undefined)).toBe(0);
    expect(countKbEntries({ success: false })).toBe(0);
    expect(countKbEntries('not a response')).toBe(0);
  });

  it('returns 0 for an empty wrapper', () => {
    expect(countKbEntries({ success: true, entries: [], count: 0, total: 0 })).toBe(0);
  });
});
