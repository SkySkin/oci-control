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
