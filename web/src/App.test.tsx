import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import App from './App';
import { fixture } from './test-fixtures';
import { readSnapshot, saveSnapshot } from './cache';
import { ServerForm } from './pages';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
beforeEach(() => { localStorage.clear(); window.location.hash = ''; });

describe('offline and session lifecycle', () => {
  it('requires explicit offline entry after failed session check and never requests actions', async () => {
    saveSnapshot(window.location.origin, fixture());
    const fetch = vi.fn().mockRejectedValue(new Error('offline'));
    vi.stubGlobal('fetch', fetch);
    render(<App />);
    await screen.findByRole('button', { name: /查看离线快照/ });
    expect(screen.queryByRole('heading', { name: '云资源总览' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /查看离线快照/ }));
    await screen.findByRole('heading', { name: '云资源总览' });
    expect(screen.getByText('正在查看本机离线快照')).toBeTruthy();
    expect(screen.getByText(/这不是实时数据，资源操作已停用/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '资源' }));
    fireEvent.click(screen.getByRole('button', { name: /查看 测试实例/ }));
    expect(screen.getByText('当前为只读视图。连接并登录后可准备操作。')).toBeTruthy();
    expect(fetch.mock.calls.every(([path]) => path === '/api/session')).toBe(true);
  });
  it('logout revokes the session while retaining account snapshots', async () => {
    let authenticated = true;
    const fetch = vi.fn(async (path: string) => {
      if (path === '/api/logout') { authenticated = false; return { status: 200, json: async () => ({ status: 'ok' }) }; }
      const data = path === '/api/session' ? { authenticated, csrfToken: 'synthetic-csrf', serverId: fixture().serverId, version: '0.1.0', mode: 'demo', capabilities: { actions: ['instance.stop'] } }
        : path === '/api/snapshot' ? fixture() : { configured: true, cliInstalled: true, refreshing: false, lastError: null, lastRefreshAt: fixture().generatedAt };
      return { status: 200, json: async () => data };
    });
    vi.stubGlobal('fetch', fetch);
    render(<App />);
    await screen.findByRole('heading', { name: '云资源总览' });
    await waitFor(() => expect(readSnapshot(window.location.origin)).not.toBeNull());
    fireEvent.click(screen.getByRole('button', { name: '设置' }));
    fireEvent.click(screen.getByRole('button', { name: '退出登录' }));
    await screen.findByRole('heading', { name: '进入控制台' });
    expect(fetch.mock.calls.some(([path]) => path === '/api/logout')).toBe(true);
    expect(readSnapshot(window.location.origin)?.serverId).toBe(fixture().serverId);
    expect(screen.getByRole('button', { name: /查看离线快照/ })).toBeTruthy();
  });
  it('does not show a different account cache after authenticating', async () => {
    saveSnapshot(window.location.origin, fixture('previous-account'));
    vi.stubGlobal('fetch', vi.fn(async (path: string) => ({ status: path === '/api/snapshot' ? 503 : 200, json: async () => path === '/api/session' ? { authenticated: true, serverId: 'new-account', version: '0.1.0', mode: 'live' } : path === '/api/snapshot' ? { error: { message: '首次采集等待中', code: 'SNAPSHOT_NOT_READY' } } : { configured: true, cliInstalled: true, refreshing: false, lastError: null, lastRefreshAt: null } })));
    render(<App />);
    await screen.findByText('首次采集等待中');
    expect(screen.queryByText('测试实例')).toBeNull();
    expect(screen.getByRole('heading', { name: '等待云资源数据' })).toBeTruthy();
  });
});

it('requires fresh explicit opt-in when the HTTP server address changes', () => {
  const save = vi.fn();
  render(<ServerForm initialUrl="" onSave={save} />);
  fireEvent.change(screen.getByLabelText('服务器地址'), { target: { value: 'http://one.example.test' } });
  const submit = screen.getByRole('button', { name: '保存并连接' });
  expect((submit as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole('checkbox'));
  fireEvent.click(submit);
  expect(save).toHaveBeenCalledWith('http://one.example.test', true);
  fireEvent.change(screen.getByLabelText('服务器地址'), { target: { value: 'http://two.example.test' } });
  expect((submit as HTMLButtonElement).disabled).toBe(true);
});
