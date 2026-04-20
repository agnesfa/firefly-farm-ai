// ADR 0008 I11 — deterministic classifier tests.
import { describe, it, expect } from 'vitest';
import { classifyObservation, applyClassifierToNotes } from '../helpers/classifier.js';

describe('classifyObservation (I11)', () => {
  describe('type classification', () => {
    it('seeding verbs', () => {
      expect(classifyObservation('Seeded pigeon pea in row 3').type).toBe('seeding');
      expect(classifyObservation('Sowed tomato seeds').type).toBe('seeding');
    });

    it('transplanting verbs', () => {
      expect(classifyObservation('Transplanted 5 papayas').type).toBe('transplanting');
      expect(classifyObservation('Planted new citrus in P2R3').type).toBe('transplanting');
      expect(classifyObservation('Moved the basil from nursery').type).toBe('transplanting');
    });

    it('harvest verbs', () => {
      expect(classifyObservation('Harvested 3kg of mangoes').type).toBe('harvest');
      expect(classifyObservation('Picked the ripe tomatoes').type).toBe('harvest');
    });

    it('activity verbs', () => {
      expect(classifyObservation('Chopped and dropped pigeon pea').type).toBe('activity');
      expect(classifyObservation('Cut back the banana leaves').type).toBe('activity');
      expect(classifyObservation('Mulched the bed heavily').type).toBe('activity');
    });

    it('observation default', () => {
      expect(classifyObservation('Two flowers observed; looks healthy').type).toBe('observation');
    });

    it('does NOT match bare "plant" as noun', () => {
      // This was the bug: "plant looks healthy" triggered transplanting.
      expect(classifyObservation('Two flowers observed; plant looks healthy').type).toBe('observation');
    });

    it('seeding wins over transplanting in precedence', () => {
      expect(classifyObservation('Seeded and planted more rows').type).toBe('seeding');
    });
  });

  describe('status classification', () => {
    it('detects pending markers', () => {
      expect(classifyObservation('Needs watering soon').status).toBe('pending');
      expect(classifyObservation('Should prune next week').status).toBe('pending');
      expect(classifyObservation('Todo: transplant Okra').status).toBe('pending');
    });

    it('defaults to done for past-tense', () => {
      expect(classifyObservation('Harvested 5kg').status).toBe('done');
    });

    it('pending compounds with activity type', () => {
      const r = classifyObservation('Needs pruning of pigeon pea branches');
      expect(r.type).toBe('activity');
      expect(r.status).toBe('pending');
    });

    it('pending compounds with transplanting', () => {
      const r = classifyObservation('Should transplant tomorrow');
      expect(r.type).toBe('transplanting');
      expect(r.status).toBe('pending');
    });
  });

  describe('ambiguity handling', () => {
    it('empty notes are ambiguous', () => {
      const r = classifyObservation('');
      expect(r.ambiguous).toBe(true);
      expect(r.type).toBe('observation');
      expect(r.status).toBe('pending');
      expect(r.confidence).toBe(0.0);
    });

    it('notes with no signal are ambiguous', () => {
      const r = classifyObservation('hello world xyzzy');
      expect(r.ambiguous).toBe(true);
      expect(r.confidence).toBeLessThanOrEqual(0.4);
    });

    it('multi-verb match is ambiguous', () => {
      const r = classifyObservation('Harvested mangoes and planted new citrus');
      expect(r.ambiguous).toBe(true);
      expect(r.reason).toContain('multi_verb_match');
    });

    it('clear activity is not ambiguous', () => {
      const r = classifyObservation('Pruned the pigeon pea heavily');
      expect(r.ambiguous).toBe(false);
      expect(r.confidence).toBeGreaterThanOrEqual(0.5);
    });
  });

  describe('applyClassifierToNotes', () => {
    it('flags ambiguous with marker', () => {
      const { notes, result } = applyClassifierToNotes('xyzzy hello');
      expect(result.ambiguous).toBe(true);
      expect(notes).toContain('[FLAG classifier-ambiguous:');
    });

    it('passes clear notes unchanged', () => {
      const { notes, result } = applyClassifierToNotes('Pruned the pigeon pea');
      expect(result.ambiguous).toBe(false);
      expect(notes).not.toContain('[FLAG');
      expect(notes).toBe('Pruned the pigeon pea');
    });

    it('handles null input', () => {
      const { result } = applyClassifierToNotes(null);
      expect(result.type).toBe('observation');
      expect(result.status).toBe('pending');
    });
  });
});
