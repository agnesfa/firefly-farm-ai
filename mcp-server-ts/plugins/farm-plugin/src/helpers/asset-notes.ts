/**
 * ADR 0008 I8 — Asset notes hygiene.
 *
 * Plant asset `notes` must contain only stable planting-context text.
 * The InteractionStamp, submission UUID, and pure-metadata headers
 * (Reporter/Submitted/Mode/Count) belong on the observation log, not
 * on the asset. The submitter's narrative (text after `Plant notes:`)
 * IS preserved — it's useful context on the QR page.
 *
 * Design (clarified 2026-04-20):
 *   - `[ontology:InteractionStamp]` lines     → dropped
 *   - `submission=<uuid>` lines               → dropped
 *   - `Reporter:/Submitted:/Mode:/Count:`     → dropped (pure metadata)
 *   - `Plant notes: <narrative>`              → `Plant notes:` prefix
 *                                               stripped; narrative kept
 *   - "New plant added via field observation" → dropped (boilerplate)
 *   - Everything else                         → kept
 */

const STAMP_MARKER = '[ontology:InteractionStamp]';

// Pure-metadata headers — line is dropped entirely.
const METADATA_PREFIXES = [
  'reporter:',
  'submitted:',
  'mode:',
  'count:',
];

// Narrative-carrying prefix — strip just the prefix, keep the rest of the line.
const NARRATIVE_PREFIX_RE = /^plant notes:\s*/i;

const BOILERPLATE_PHRASES = ['New plant added via field observation'];

export function sanitiseAssetNotes(notes: string | undefined | null): string {
  if (!notes) return '';
  const kept: string[] = [];
  for (const ln of String(notes).split(/\r?\n/)) {
    if (ln.includes(STAMP_MARKER)) continue;
    const low = ln.trim().toLowerCase();
    if (low.startsWith('submission=')) continue;
    if (METADATA_PREFIXES.some((p) => low.startsWith(p))) continue;
    // "Plant notes: <narrative>" — strip only the prefix.
    const lnStripped = ln.replace(NARRATIVE_PREFIX_RE, '');
    kept.push(lnStripped.replace(/\s+$/, ''));
  }
  let out = kept.join('\n').trim();
  for (const phrase of BOILERPLATE_PHRASES) {
    out = out.split(phrase).join('').trim();
  }
  out = out.replace(/\n{3,}/g, '\n\n').trim();
  return out;
}
