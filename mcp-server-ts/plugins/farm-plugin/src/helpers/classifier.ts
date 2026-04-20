/**
 * ADR 0008 I11 — deterministic log-type classifier.
 *
 * Given a notes text, classify log type + status:
 *   - type:   observation | activity | transplanting | seeding | harvest
 *   - status: done | pending (pending == TODO / action needed)
 *
 * Rules match against lowercased notes in precedence order. Ambiguity
 * (no rule matched, or competing verbs) returns type=observation,
 * status=pending with a reason string so the importer can flag the log
 * for human review.
 *
 * Upgrade path (Step 9, post-FASF ADR 0006): swap this deterministic
 * function for an agent-skill implementation with confidence scoring.
 * The I11 contract is stable across both implementations.
 */

const RE_SEEDING = /\b(seeded|sowed|sowing|germinated|seeding)\b/;
// Note: bare "plant" excluded — it's a noun in most field contexts.
const RE_TRANSPLANTING = /\b(transplanted|transplants|transplanting|transplant|planted|planting|replanted|replanting|relocated|relocating|moved(?!\s+in))\b/;
const RE_HARVEST = /\b(harvested|harvesting|harvest|picked|picking|collected|collecting|yielded|yielding|gathered|gathering)\b/;
const RE_ACTIVITY = /\b(chopped|chopping|chop|dropped|dropping|pruned|pruning|prune|mulched|mulching|mulch|weeded|weeding|weed|watered|watering|sprayed|spraying|applied|applying|inoculated|inoculating|fertilised|fertilising|fertilized|fertilizing|composted|composting|dug|digging|tilled|tilling)\b|cut back|chop and drop/;
const RE_PENDING = /\b(needs|need|should|to do|todo|urgent|action required|action needed|please|must|tbd|pending)\b/;

export type LogType = 'observation' | 'activity' | 'transplanting' | 'seeding' | 'harvest';
export type LogStatus = 'done' | 'pending';

export interface ClassifyResult {
  type: LogType;
  status: LogStatus;
  confidence: number;
  reason: string;
  ambiguous: boolean;
}

export function classifyObservation(notes: string | null | undefined): ClassifyResult {
  if (!notes) {
    return {
      type: 'observation',
      status: 'pending',
      confidence: 0.0,
      reason: 'empty_notes',
      ambiguous: true,
    };
  }
  const text = String(notes).toLowerCase();

  let type: LogType;
  let typeReason: string;
  let confidence = 0.5;

  if (RE_SEEDING.test(text)) {
    type = 'seeding';
    typeReason = 'verb_seeding';
    confidence = 0.85;
  } else if (RE_TRANSPLANTING.test(text)) {
    type = 'transplanting';
    typeReason = 'verb_transplanting';
    confidence = 0.85;
  } else if (RE_HARVEST.test(text)) {
    type = 'harvest';
    typeReason = 'verb_harvest';
    confidence = 0.85;
  } else if (RE_ACTIVITY.test(text)) {
    type = 'activity';
    typeReason = 'verb_activity';
    confidence = 0.85;
  } else {
    type = 'observation';
    typeReason = 'no_action_verb';
    confidence = 0.6;
  }

  let status: LogStatus = 'done';
  let statusReason = '';
  if (RE_PENDING.test(text)) {
    status = 'pending';
    statusReason = 'verb_pending';
  }

  const typeMatches =
    (RE_SEEDING.test(text) ? 1 : 0) +
    (RE_TRANSPLANTING.test(text) ? 1 : 0) +
    (RE_HARVEST.test(text) ? 1 : 0) +
    (RE_ACTIVITY.test(text) ? 1 : 0);
  const ambiguous = typeMatches >= 2 || (typeMatches === 0 && !RE_PENDING.test(text));
  if (ambiguous) confidence = Math.min(confidence, 0.4);

  const reasons: string[] = [typeReason];
  if (statusReason) reasons.push(statusReason);
  if (typeMatches >= 2) reasons.push('multi_verb_match');

  return { type, status, confidence, reason: reasons.join(','), ambiguous };
}

export function applyClassifierToNotes(notes: string | null | undefined): {
  notes: string;
  result: ClassifyResult;
} {
  const result = classifyObservation(notes ?? '');
  if (result.ambiguous) {
    const flag = `[FLAG classifier-ambiguous: ${result.reason}]`;
    return { notes: `${flag}\n${notes ?? ''}`.trim(), result };
  }
  return { notes: notes ?? '', result };
}
