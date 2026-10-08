import { beforeEach, describe, expect, it, vi } from 'vitest';
import { isSnapshot, purgeSnapshots, readSnapshot, saveSnapshot } from './cache';
import { fixture } from './test-fixtures';
import { bytes, money, number } from './format';

beforeEach(() => { localStorage.clear(); vi.restoreAllMocks(); });
describe('account-scoped snapshot storage', () => {
  it('isolates both account identities and server origins', () => {
    saveSnapshot('https://one.example.test', fixture('a'));
    saveSnapshot('https://one.example.test', fixture('b'));
    saveSnapshot('https://two.example.test', fixture('a'));
    expect(readSnapshot('https://one.example.test')?.serverId).toBe('b');
    expect(readSnapshot('https://one.example.test', 'a')?.serverId).toBe('a');
    expect(readSnapshot('https://one.example.test', 'c')).toBeNull();
    expect(readSnapshot('https://unseen.example.test', 'a')).toBeNull();
    purgeSnapshots('https://one.example.test');
    expect(readSnapshot('https://one.example.test', 'a')).toBeNull();
    expect(readSnapshot('https://one.example.test', 'b')).toBeNull();
    expect(readSnapshot('https://two.example.test', 'a')?.serverId).toBe('a');
  });
  it('rejects account mismatch and corrupted or old schemas', () => {
    saveSnapshot('https://one.example.test', fixture('a'));
    const key = 'oci-control.snapshot.v1.data.https%3A%2F%2Fone.example.test.a';
    localStorage.setItem(key, JSON.stringify(fixture('other')));
    expect(readSnapshot('https://one.example.test', 'a')).toBeNull();
    localStorage.setItem(key, '{broken');
    expect(readSnapshot('https://one.example.test', 'a')).toBeNull();
    expect(isSnapshot({ ...fixture(), schemaVersion: 2 })).toBe(false);
    expect(isSnapshot({ ...fixture(), resources: [null] })).toBe(false);
    expect(isSnapshot({ ...fixture(), regions: [{}] })).toBe(false);
  });
  it('returns a persistence failure when storage is full', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('full', 'QuotaExceededError'); });
    expect(saveSnapshot('https://one.example.test', fixture())).toBe(false);
  });
});
describe('honest missing metrics', () => {
  it('keeps unknown distinct from actual zero', () => {
    expect(bytes(null)).toBe('暂无数据');
    expect(bytes(0)).toBe('0 B');
    expect(money(null, '')).toBe('暂无数据');
    expect(money(0, 'USD')).toContain('0.00');
    expect(number(undefined)).toBe('暂无数据');
    expect(number(0)).toBe('0');
  });
});

it('rejects malformed nested data without coercing it to zero', () => {
  for (const field of ['regions', 'resources', 'alerts', 'errors'] as const) expect(isSnapshot({ ...fixture(), [field]: [null] })).toBe(false);
  expect(isSnapshot({ ...fixture(), traffic: { ...fixture().traffic, daily: [null] } })).toBe(false);
  expect(isSnapshot({ ...fixture(), cost: { ...fixture().cost, daily: [null] } })).toBe(false);
  expect(isSnapshot({ ...fixture(), cost: { ...fixture().cost, byService: [{ name: 'bad', amount: '0' }] } })).toBe(false);
  expect(isSnapshot({ ...fixture(), resources: [{ ...fixture().resources[0], publicIps: [null] }] })).toBe(false);
});
it('accepts unavailable official quantities and units and rejects corrupted cached elements', () => {
  const snapshot = fixture();
  snapshot.traffic.officialUnit = null;
  snapshot.traffic.officialSkus = [{ skuPartNumber: 'synthetic-sku', skuName: '合成计量', service: 'network', unit: 'GB', quantity: null }];
  expect(isSnapshot(snapshot)).toBe(true);
  saveSnapshot('https://example.test', snapshot);
  const key = 'oci-control.snapshot.v1.data.https%3A%2F%2Fexample.test.synthetic-account-a';
  localStorage.setItem(key, JSON.stringify({ ...snapshot, traffic: { ...snapshot.traffic, daily: [null] } }));
  expect(readSnapshot('https://example.test')).toBeNull();
});

it('accepts collector NLB unknown health and absent listener targets, while rejecting wrong value types', () => {
  const snapshot = fixture();
  snapshot.resources[0].kind = 'nlb';
  snapshot.resources[0].details = { backendSets: [{ name: 'synthetic-set', health: null, backends: [{ name: 'synthetic-backend', health: null }] }], listeners: [{ name: 'synthetic-listener', port: 443, protocol: 'TCP', defaultBackendSetName: null }] };
  expect(isSnapshot(snapshot)).toBe(true);
  snapshot.resources[0].details = { backendSets: [{ name: 'synthetic-set', health: 17 }] };
  expect(isSnapshot(snapshot)).toBe(false);
  snapshot.resources[0].details = { listeners: [{ name: 'synthetic-listener', defaultBackendSetName: {} }] };
  expect(isSnapshot(snapshot)).toBe(false);
});
