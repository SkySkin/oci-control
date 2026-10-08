import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Session, Snapshot } from './types';
const state = vi.hoisted(() => ({ sessions: {} as Record<string, Session>, snapshots: {} as Record<string, Snapshot | Error>, login: null as Promise<Session> | null }));
vi.mock('./api', () => ({
  isNative: true,
  normalizeServerUrl: (url: string) => new URL(url).origin,
  ApiError: class extends Error { constructor(message: string, public status = 0) { super(message); } },
  ApiClient: class {
    constructor(public origin: string) {}
    session() { return Promise.resolve(state.sessions[this.origin]); }
    login() { return state.login; }
    snapshot() { const snapshot = state.snapshots[this.origin]; return snapshot instanceof Error ? Promise.reject(snapshot) : Promise.resolve(snapshot); }
    status() { return Promise.resolve({ configured: true, cliInstalled: true, refreshing: false, lastError: null, lastRefreshAt: null }); }
  },
}));
import App from './App';
import { saveServerPreference, saveSnapshot } from './cache';
import { fixture } from './test-fixtures';

const session = (serverId: string): Session => ({ authenticated: true, serverId, version: '0.1.0', mode: 'demo', capabilities: { actions: [] } });
const accountSnapshot = (serverId: string): Snapshot => ({ ...fixture(serverId), tenancy: { name: `合成账号 ${serverId}`, homeRegion: 'test-region' } });
beforeEach(() => { localStorage.clear(); window.location.hash = ''; state.sessions = {}; state.snapshots = {}; state.login = null; });
afterEach(cleanup);

describe('server identity isolation regressions', () => {
  it('discards login A when it resolves after switching to authenticated server B', async () => {
    saveServerPreference({ url: 'https://a.example.test', allowHttp: false });
    state.sessions['https://a.example.test'] = { authenticated: false, version: '0.1.0', mode: 'demo' };
    state.sessions['https://b.example.test'] = session('B');
    state.snapshots['https://a.example.test'] = accountSnapshot('A');
    state.snapshots['https://b.example.test'] = accountSnapshot('B');
    let resolveLogin!: (value: Session) => void;
    state.login = new Promise(resolve => { resolveLogin = resolve; });
    render(<App />);
    fireEvent.change(screen.getByLabelText('访问密码'), { target: { value: 'synthetic-password' } });
    await waitFor(() => expect((screen.getByRole('button', { name: '登录控制台' }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button', { name: '登录控制台' }));
    fireEvent.click(screen.getByRole('button', { name: '更换' }));
    fireEvent.change(screen.getByLabelText('服务器地址'), { target: { value: 'https://b.example.test' } });
    fireEvent.click(screen.getByRole('button', { name: '保存并连接' }));
    await screen.findByText('合成账号 B');
    await act(async () => { resolveLogin(session('A')); await state.login; });
    expect(screen.queryByText('合成账号 A')).toBeNull();
    expect(screen.getByText('合成账号 B')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '设置' }));
    expect(screen.getByText('https://b.example.test')).toBeTruthy();
    expect(screen.queryByText(/合成账号 A/)).toBeNull();
  });
  it('does not expose account A snapshot metadata in authenticated account B settings', async () => {
    saveServerPreference({ url: 'https://same.example.test', allowHttp: false });
    saveSnapshot('https://same.example.test', accountSnapshot('A'));
    state.sessions['https://same.example.test'] = session('B');
    state.snapshots['https://same.example.test'] = new Error('Synthetic snapshot unavailable');
    render(<App />);
    await screen.findByRole('heading', { name: '云资源总览' });
    fireEvent.click(screen.getByRole('button', { name: '设置' }));
    expect(screen.queryByText(/合成账号 A/)).toBeNull();
    expect(screen.getByText('本机尚未保存当前账号快照')).toBeTruthy();
  });
});
