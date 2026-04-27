import { describe, it, expect } from 'vitest';
import {
  parseApiVersion,
  assetStatusFilter,
  assetStatusFilterParam,
  assetArchivePayload,
  readAssetStatus,
  ACTIVE,
  ARCHIVED,
  type ApiVersion,
  type AssetStatus,
} from '../clients/api-version.js';

describe('api-version helpers', () => {
  describe('parseApiVersion', () => {
    it('defaults to "3" when env is undefined', () => {
      expect(parseApiVersion(undefined)).toBe('3');
    });

    it('accepts "3" and "4"', () => {
      expect(parseApiVersion('3')).toBe('3');
      expect(parseApiVersion('4')).toBe('4');
    });

    it('throws on unknown value with explanatory message', () => {
      expect(() => parseApiVersion('5')).toThrow(/must be one of 3\/4/);
      expect(() => parseApiVersion('v3')).toThrow();
      expect(() => parseApiVersion('three')).toThrow();
    });

    it('throws on empty string (catches typos)', () => {
      expect(() => parseApiVersion('')).toThrow();
    });
  });

  describe('assetStatusFilter (dict)', () => {
    it('v3 active → {status: active}', () => {
      expect(assetStatusFilter('3', ACTIVE)).toEqual({ status: 'active' });
    });

    it('v3 archived → {status: archived}', () => {
      expect(assetStatusFilter('3', ARCHIVED)).toEqual({ status: 'archived' });
    });

    it('v4 active → {archived: 0}', () => {
      expect(assetStatusFilter('4', ACTIVE)).toEqual({ archived: '0' });
    });

    it('v4 archived → {archived: 1}', () => {
      expect(assetStatusFilter('4', ARCHIVED)).toEqual({ archived: '1' });
    });
  });

  describe('assetStatusFilterParam (URL fragment)', () => {
    it('v3 → filter[status]=active', () => {
      expect(assetStatusFilterParam('3', ACTIVE)).toBe('filter[status]=active');
      expect(assetStatusFilterParam('3', ARCHIVED)).toBe('filter[status]=archived');
    });

    it('v4 → filter[archived]=0/1', () => {
      expect(assetStatusFilterParam('4', ACTIVE)).toBe('filter[archived]=0');
      expect(assetStatusFilterParam('4', ARCHIVED)).toBe('filter[archived]=1');
    });
  });

  describe('assetArchivePayload', () => {
    it('v3 → {status: "archived"}', () => {
      expect(assetArchivePayload('3')).toEqual({ status: 'archived' });
    });

    it('v4 → {archived: true}', () => {
      expect(assetArchivePayload('4')).toEqual({ archived: true });
    });
  });

  describe('readAssetStatus (shape-detected, no version)', () => {
    it('reads v4 archived=false as active', () => {
      expect(readAssetStatus({ attributes: { archived: false, name: 'X' } })).toBe('active');
    });

    it('reads v4 archived=true as archived', () => {
      expect(readAssetStatus({ attributes: { archived: true, name: 'X' } })).toBe('archived');
    });

    it('reads v3 status=active as active', () => {
      expect(readAssetStatus({ attributes: { status: 'active', name: 'X' } })).toBe('active');
    });

    it('reads v3 status=archived as archived', () => {
      expect(readAssetStatus({ attributes: { status: 'archived', name: 'X' } })).toBe('archived');
    });

    it('prefers v4 archived field when both present (mixed-shape safety)', () => {
      // Should not happen in practice but defensive: archived field wins.
      expect(readAssetStatus({ attributes: { archived: true, status: 'active' } })).toBe('archived');
      expect(readAssetStatus({ attributes: { archived: false, status: 'archived' } })).toBe('active');
    });

    it('defaults to active on missing/empty attributes', () => {
      expect(readAssetStatus({})).toBe('active');
      expect(readAssetStatus({ attributes: {} })).toBe('active');
      expect(readAssetStatus(null)).toBe('active');
      expect(readAssetStatus(undefined)).toBe('active');
    });
  });

  describe('parameterised v3+v4 round-trip (read → filter)', () => {
    // Sanity: emit a filter, simulate a response in that version's shape,
    // round-trip it through readAssetStatus. Both versions should yield
    // the same display label.
    const cases: Array<[ApiVersion, AssetStatus]> = [
      ['3', ACTIVE], ['3', ARCHIVED], ['4', ACTIVE], ['4', ARCHIVED],
    ];
    it.each(cases)('version %s status %s round-trips', (version, status) => {
      const filter = assetStatusFilter(version, status);
      // Build a mock response in the matching version's shape
      const asset = version === '4'
        ? { attributes: { archived: status === ARCHIVED, name: 'X' } }
        : { attributes: { status, name: 'X' } };
      expect(readAssetStatus(asset)).toBe(status);
      // Filter should have exactly one entry
      expect(Object.keys(filter)).toHaveLength(1);
    });
  });
});
