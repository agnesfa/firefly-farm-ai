// ADR 0008 I8 — asset notes sanitiser tests.
import { describe, it, expect } from 'vitest';
import { sanitiseAssetNotes } from '../helpers/asset-notes.js';

describe('sanitiseAssetNotes (I8)', () => {
  it('returns empty string for null or empty input', () => {
    expect(sanitiseAssetNotes('')).toBe('');
    expect(sanitiseAssetNotes(null)).toBe('');
    expect(sanitiseAssetNotes(undefined)).toBe('');
  });

  it('passes stable notes through unchanged', () => {
    const note = 'Rootstock: Anna, grafted April 2026';
    expect(sanitiseAssetNotes(note)).toBe(note);
  });

  it('strips interaction-stamp line', () => {
    const notes = 'Rootstock: Anna\n[ontology:InteractionStamp] initiator=X | ts=2026';
    expect(sanitiseAssetNotes(notes)).toBe('Rootstock: Anna');
  });

  it('strips submission= line', () => {
    const notes = 'Rootstock: Anna\nsubmission=abc-123-def';
    expect(sanitiseAssetNotes(notes)).toBe('Rootstock: Anna');
  });

  it('strips Reporter header', () => {
    expect(sanitiseAssetNotes('Reporter: Leah')).toBe('');
  });

  it('strips metadata headers but keeps Plant notes narrative', () => {
    const dump = [
      'Reporter: Leah',
      'Submitted: 2026-04-14T06:46:00',
      'Mode: new_plant',
      'Plant notes: two flowers observed',
      'Count: 0 -> 1',
    ].join('\n');
    expect(sanitiseAssetNotes(dump)).toBe('two flowers observed');
  });

  it('strips boilerplate phrase', () => {
    const notes = 'Rootstock: Anna\nNew plant added via field observation';
    expect(sanitiseAssetNotes(notes)).toBe('Rootstock: Anna');
  });

  it('full Leah-style dump reduces to narrative only', () => {
    const dump = [
      'Reporter: Leah',
      'Submitted: 2026-04-14T06:46:00',
      'Mode: new_plant',
      'Plant notes: Leah transcript 14 Apr 2026.  two flowers observed',
      'Count: 0 -> 1',
      'New plant added via field observation',
      '[ontology:InteractionStamp] initiator=Leah | submission=479332c9',
    ].join('\n');
    expect(sanitiseAssetNotes(dump)).toBe(
      'Leah transcript 14 Apr 2026.  two flowers observed',
    );
  });

  it('strips Plant notes prefix case-insensitively', () => {
    expect(sanitiseAssetNotes('PLANT NOTES: urgent chop needed')).toBe('urgent chop needed');
    expect(sanitiseAssetNotes('plant notes:     spaces before')).toBe('spaces before');
  });

  it('stamp-only reduces to empty', () => {
    expect(sanitiseAssetNotes('[ontology:InteractionStamp] initiator=x | submission=abc')).toBe('');
  });

  it('preserves user narrative mixed with stamp', () => {
    const notes = 'Grafted April 2026, rootstock Anna\n[ontology:InteractionStamp] initiator=X';
    expect(sanitiseAssetNotes(notes)).toBe('Grafted April 2026, rootstock Anna');
  });

  it('is case-insensitive for header matching', () => {
    expect(sanitiseAssetNotes('REPORTER: Leah')).toBe('');
    expect(sanitiseAssetNotes('reporter: Leah')).toBe('');
  });
});
