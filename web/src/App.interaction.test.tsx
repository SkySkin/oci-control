import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
const lifecycle = vi.hoisted(() => ({ resume: () => {} }));
vi.mock('./native', () => ({ NativeChrome: { setTheme: async () => {} }, useNativeLifecycle: (_back: () => boolean, resume: () => void) => { lifecycle.resume = resume; } }));
vi.mock('./api', () => ({
  isNative: false,
  normalizeServerUrl: (value: string) => new URL(value).origin,
  ApiError: class extends Error { status = 0; },
  ApiClient: class {
    constructor(public origin: string) {}
    session() {} snapshot() {} status() {} refresh() {} prepare() {} execute() {} logout() {}
  },
}));
import App from './App';
import { ApiClient } from './api';
import { fixture } from './test-fixtures';
import type { Snapshot } from './types';

const tick = () => new Promise(resolve => setTimeout(resolve, 20));
const deferred = <T,>() => { let resolve!: (value: T) => void; const promise = new Promise<T>(yes => { resolve = yes; }); return { promise, resolve }; };
const status = () => ({ configured: true, cliInstalled: true, refreshing: false, lastError: null, lastRefreshAt: fixture().generatedAt });
beforeEach(() => {
  localStorage.clear();
  vi.spyOn(ApiClient.prototype, 'session').mockResolvedValue({ authenticated: true, serverId: fixture().serverId, version: '0.2.0', mode: 'demo', capabilities: { actions: ['instance.stop', 'instance.rename'] } });
  vi.spyOn(ApiClient.prototype, 'snapshot').mockResolvedValue(fixture());
  vi.spyOn(ApiClient.prototype, 'status').mockResolvedValue(status());
  vi.spyOn(ApiClient.prototype, 'refresh').mockResolvedValue({ status: 'refreshing' });
  vi.spyOn(ApiClient.prototype, 'prepare').mockResolvedValue({ confirmationId: 'synthetic-confirmation', action: 'instance.stop', resourceName: '测试实例', summary: '停止合成实例', expiresAt: new Date(Date.now() + 60000).toISOString(), requiresText: '测试实例' });
  vi.spyOn(ApiClient.prototype, 'execute').mockResolvedValue({ operationId: 'synthetic-operation', status: 'submitted', message: '已受理' });
});
afterEach(async () => { cleanup(); await tick(); vi.restoreAllMocks(); });
async function start() { render(<App />); await screen.findByText('测试实例'); await waitFor(() => expect((screen.getByRole('button', { name: '刷新快照' }) as HTMLButtonElement).disabled).toBe(false)); }
async function detail(from = 'resources') {
  await start();
  if (from === 'resources') fireEvent.click(screen.getByRole('button', { name: '资源' }));
  const row = screen.getByRole('button', { name: /查看 测试实例/ }); row.focus(); fireEvent.click(row);
  await screen.findByRole('heading', { name: '资源详情' });
}
async function back() { await act(async () => { history.back(); await tick(); }); }

it('opens a separate detail route, restores filter/scroll/focus on browser back and supports forward', async () => {
  await start(); fireEvent.click(screen.getByRole('button', { name: '资源' }));
  fireEvent.change(screen.getByRole('textbox', { name: '搜索资源' }), { target: { value: '测试' } });
  fireEvent.change(screen.getByRole('combobox', { name: '资源类型' }), { target: { value: 'instance' } });
  vi.spyOn(window, 'scrollY', 'get').mockReturnValue(640);
  const row = screen.getByRole('button', { name: /查看 测试实例/ }); row.focus(); fireEvent.click(row);
  expect(location.hash).toContain('#resources/synthetic-instance');
  expect(screen.queryByRole('textbox', { name: '搜索资源' })).toBeNull();
  expect(document.activeElement).toBe(screen.getByRole('heading', { name: '资源详情' }));
  await back();
  expect((screen.getByRole('textbox', { name: '搜索资源' }) as HTMLInputElement).value).toBe('测试');
  expect((screen.getByRole('combobox', { name: '资源类型' }) as HTMLSelectElement).value).toBe('instance');
  expect(window.scrollTo).toHaveBeenLastCalledWith({ top: 640, behavior: 'instant' });
  expect(document.activeElement).toBe(screen.getByRole('button', { name: /查看 测试实例/ }));
  await act(async () => { history.forward(); await tick(); });
  expect(screen.getByRole('heading', { name: '资源详情' })).toBeTruthy();
});
it('returns from overview details to the original overview and skip-link preserves route', async () => {
  await detail('overview');
  fireEvent.click(screen.getByRole('button', { name: '返回来源页面' }));
  await screen.findByRole('heading', { name: '云资源总览' });
  fireEvent.click(screen.getByRole('button', { name: '资源' }));
  const hash = location.hash;
  fireEvent.click(screen.getByRole('link', { name: '跳至主要内容' }));
  expect(location.hash).toBe(hash); expect(document.activeElement?.id).toBe('main-content');
});
it.each(['取消', '关闭对话框', 'browser'])('consumes a dialog history entry via %s, then a single back reaches list', async method => {
  await detail();
  const stop = screen.getByRole('button', { name: '停止' }); stop.focus(); fireEvent.click(stop);
  await act(tick);
  expect(document.body.style.overflow).toBe('hidden');
  if (method === 'browser') await back(); else { fireEvent.click(screen.getByRole('button', { name: method })); await act(tick); }
  expect(screen.queryByRole('dialog')).toBeNull(); expect(document.body.style.overflow).toBe(''); expect(document.activeElement).toBe(stop);
  await back(); expect(screen.getByRole('heading', { name: '资源工作台' })).toBeTruthy();
});
it('keeps a busy preview dialog on browser back and never executes without exact explicit confirmation', async () => {
  const pending = deferred<Awaited<ReturnType<ApiClient['prepare']>>>();
  vi.mocked(ApiClient.prototype.prepare).mockReturnValue(pending.promise);
  await detail(); fireEvent.click(screen.getByRole('button', { name: '停止' })); await act(tick);
  fireEvent.click(screen.getByRole('button', { name: '生成操作预览' }));
  await back(); expect(screen.getByRole('dialog')).toBeTruthy(); expect(ApiClient.prototype.execute).not.toHaveBeenCalled();
  await act(async () => { pending.resolve({ confirmationId: 'synthetic-confirmation', action: 'instance.stop', resourceName: '测试实例', summary: '停止合成实例', expiresAt: new Date(Date.now() + 60000).toISOString(), requiresText: '测试实例' }); await pending.promise; });
  const confirm = screen.getByRole('button', { name: '确认执行' });
  fireEvent.click(confirm); expect(ApiClient.prototype.execute).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText('输入「测试实例」以确认'), { target: { value: '测试实例' } });
  fireEvent.click(confirm); fireEvent.click(confirm);
  await screen.findByRole('button', { name: '完成' }); expect(ApiClient.prototype.execute).toHaveBeenCalledOnce();
  fireEvent.click(screen.getByRole('button', { name: '完成' })); await act(tick); await back();
  expect(screen.getByRole('heading', { name: '资源工作台' })).toBeTruthy();
});
it('ignores in-flight snapshot after offline and enables recovery only after explicit reconnection', async () => {
  await start(); const pending = deferred<Snapshot>(); vi.mocked(ApiClient.prototype.snapshot).mockReturnValueOnce(pending.promise);
  fireEvent.click(screen.getByRole('button', { name: '设置' })); fireEvent.click(screen.getByRole('button', { name: '重新连接' }));
  await act(async () => { await Promise.resolve(); }); fireEvent(window, new Event('offline'));
  await act(async () => { pending.resolve(fixture()); await pending.promise; });
  fireEvent.click(screen.getByRole('button', { name: '资源' })); fireEvent.click(screen.getByRole('button', { name: /查看 测试实例/ }));
  expect((screen.getByRole('button', { name: '停止' }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByText('连接已中断，显示上次保存的快照')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: '重新连接' }));
  await waitFor(() => expect((screen.getByRole('button', { name: '停止' }) as HTMLButtonElement).disabled).toBe(false));
});
it('shows status failures with recovery, refresh completion and partial-refresh failure', async () => {
  vi.mocked(ApiClient.prototype.status).mockRejectedValueOnce(new Error('synthetic failure'));
  await start(); expect(screen.getByText('无法读取采集状态。请重新连接后重试。')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: '重试读取' }));
  await waitFor(() => expect(screen.queryByText('无法读取采集状态。请重新连接后重试。')).toBeNull());
  fireEvent.click(screen.getByRole('button', { name: '刷新快照' }));
  await screen.findByText('采集已启动，已有快照会持续显示');
  fireEvent.click(screen.getByRole('button', { name: '设置' })); fireEvent.click(screen.getByRole('button', { name: '重新连接' }));
  await screen.findByText('采集已完成，快照已更新');
  vi.mocked(ApiClient.prototype.status).mockResolvedValue({ ...status(), lastError: '合成区域采集失败' });
  fireEvent.click(screen.getByRole('button', { name: '刷新快照' })); await screen.findByText('采集已启动，已有快照会持续显示');
  fireEvent.click(screen.getByRole('button', { name: '重新连接' }));
  await screen.findByText('采集未完成：合成区域采集失败。请检查配置后重试。');
});
it('purge confirmation consumes its back entry and logout first requires a local confirmation', async () => {
  await start(); fireEvent.click(screen.getByRole('button', { name: '设置' }));
  fireEvent.click(screen.getByRole('button', { name: '清除本机快照' })); await act(tick);
  fireEvent.click(screen.getByRole('button', { name: '确认清除' })); await act(tick);
  expect(screen.queryByRole('dialog')).toBeNull();
  await back(); expect(screen.getByRole('heading', { name: '云资源总览' })).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: '设置' }));
  const logout = vi.spyOn(ApiClient.prototype, 'logout').mockResolvedValue(undefined);
  fireEvent.click(screen.getByRole('button', { name: '退出登录' })); await act(tick);
  expect(logout).not.toHaveBeenCalled(); fireEvent.click(screen.getByRole('button', { name: '取消' })); await act(tick);
  await back(); expect(screen.getByRole('heading', { name: '云资源总览' })).toBeTruthy();
});

it('releases the refresh request lock when resume invalidates its old response', async () => {
  const pending = deferred<{ status: string }>();
  vi.mocked(ApiClient.prototype.refresh).mockReturnValueOnce(pending.promise);
  await start(); fireEvent.click(screen.getByRole('button', { name: '刷新快照' }));
  await act(async () => lifecycle.resume());
  await waitFor(() => expect((screen.getByRole('button', { name: '刷新快照' }) as HTMLButtonElement).disabled).toBe(false));
  expect(ApiClient.prototype.refresh).toHaveBeenCalledOnce();
  await act(async () => { pending.resolve({ status: 'refreshing' }); await pending.promise; });
  fireEvent.click(screen.getByRole('button', { name: '刷新快照' }));
  expect(ApiClient.prototype.refresh).toHaveBeenCalledTimes(2);
});
it.each(['取消', '关闭对话框', '完成'])('returns to the actual source after forwarding through a dismissed %s overlay', async method => {
  vi.spyOn(window, 'scrollY', 'get').mockReturnValue(800);
  await detail(); fireEvent.click(screen.getByRole('button', { name: '停止' })); await act(tick);
  if (method === '完成') {
    fireEvent.click(screen.getByRole('button', { name: '生成操作预览' }));
    await screen.findByRole('button', { name: '确认执行' });
    fireEvent.change(screen.getByLabelText('输入「测试实例」以确认'), { target: { value: '测试实例' } });
    fireEvent.click(screen.getByRole('button', { name: '确认执行' }));
    await screen.findByRole('button', { name: '完成' });
  }
  fireEvent.click(screen.getByRole('button', { name: method })); await act(tick);
  await back(); expect(screen.getByRole('heading', { name: '资源工作台' })).toBeTruthy();
  await act(async () => { history.forward(); await tick(); });
  await act(async () => { history.forward(); await tick(); });
  expect(screen.getByRole('heading', { name: '资源详情' })).toBeTruthy();
  expect(screen.queryByRole('dialog')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: '返回来源页面' }));
  await screen.findByRole('heading', { name: '资源工作台' });
  expect(window.scrollTo).toHaveBeenLastCalledWith({ top: 800, behavior: 'instant' });
  expect(document.activeElement).toBe(screen.getByRole('button', { name: /查看 测试实例/ }));
});
