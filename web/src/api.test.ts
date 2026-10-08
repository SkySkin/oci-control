import { beforeEach, describe, expect, it, vi } from 'vitest';
const native = vi.hoisted(() => ({ request: vi.fn(), get: vi.fn(), set: vi.fn(), remove: vi.fn() }));
vi.mock('@capacitor/core', () => ({
  Capacitor: { isNativePlatform: () => false },
  CapacitorHttp: { request: native.request },
  registerPlugin: () => ({ get: native.get, set: native.set, remove: native.remove }),
}));
import { ApiClient, normalizeServerUrl } from './api';

beforeEach(() => { vi.resetAllMocks(); localStorage.clear(); native.get.mockResolvedValue({ value: null }); });
describe('server URL validation', () => {
  it('accepts only an origin and requires HTTP opt-in', () => {
    expect(normalizeServerUrl(' https://cloud.example.test/ ')).toBe('https://cloud.example.test');
    expect(normalizeServerUrl('http://example.test:8787', true)).toBe('http://example.test:8787');
    expect(() => normalizeServerUrl('http://example.test')).toThrow('HTTP');
    for (const value of ['ftp://example.test', 'https://name:pass@example.test', 'https://example.test/api', 'https://example.test?q=x', 'https://example.test/#x']) {
      expect(() => normalizeServerUrl(value, true)).toThrow();
    }
  });
});
describe('browser authentication', () => {
  it('uses cookies plus CSRF and never stores the password or bearer', async () => {
    const fetch = vi.fn().mockResolvedValue({ status: 200, json: async () => ({ authenticated: true, csrfToken: 'synthetic-csrf', serverId: 'synthetic-server', mode: 'demo' }) });
    vi.stubGlobal('fetch', fetch);
    const api = new ApiClient('https://example.test', false);
    await api.login('synthetic-test-password');
    await api.refresh();
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ password: 'synthetic-test-password', client: 'web' });
    expect(fetch.mock.calls[2][0]).toBe('/api/refresh');
    expect(fetch.mock.calls[2][1]).toMatchObject({ credentials: 'same-origin', redirect: 'error', headers: { 'X-CSRF-Token': 'synthetic-csrf' } });
    expect(fetch.mock.calls[2][1].headers.Authorization).toBeUndefined();
    expect(localStorage.length).toBe(0);
    expect(native.set).not.toHaveBeenCalled();
  });
});
describe('native authentication', () => {
  it('uses explicit native HTTP and bearer only from secure storage', async () => {
    native.request.mockResolvedValueOnce({ status: 200, url: 'https://example.test/api/login', data: { token: 'synthetic-bearer', csrfToken: 'synthetic-csrf' } })
      .mockResolvedValueOnce({ status: 200, data: { authenticated: true } });
    native.get.mockResolvedValueOnce({ value: null }).mockResolvedValue({ value: 'synthetic-bearer' });
    const api = new ApiClient('https://example.test', true);
    await api.login('synthetic-test-password');
    expect(native.set).toHaveBeenCalledWith({ key: 'oci-control.session.https%3A%2F%2Fexample.test', value: 'synthetic-bearer' });
    expect(native.request.mock.calls[0][0]).toMatchObject({ disableRedirects: true, data: { client: 'android' } });
    expect(native.request.mock.calls[1][0].headers.Authorization).toBe('Bearer synthetic-bearer');
    expect(native.request.mock.calls[1][0].headers['X-CSRF-Token']).toBeUndefined();
    expect(localStorage.length).toBe(0);
  });
  it('rejects redirects and does not clear native auth until server revocation succeeds', async () => {
    const api = new ApiClient('https://example.test', true);
    native.request.mockResolvedValueOnce({ status: 302, data: {} });
    await expect(api.session()).rejects.toThrow('重定向');
    native.request.mockResolvedValueOnce({ status: 200, url: 'https://different.example.test/api/session', data: {} });
    await expect(api.session()).rejects.toThrow('重定向');
    native.request.mockRejectedValueOnce(new Error('network down'));
    await expect(api.logout()).rejects.toThrow('连接');
    expect(native.remove).not.toHaveBeenCalled();
    native.request.mockResolvedValueOnce({ status: 200, data: {} });
    await api.logout();
    expect(native.remove).toHaveBeenCalledOnce();
  });
});
