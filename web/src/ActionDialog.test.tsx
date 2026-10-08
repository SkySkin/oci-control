import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ApiClient } from './api';
import ActionDialog, { extractBackends } from './ActionDialog';
import { fixture } from './test-fixtures';

beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  HTMLDialogElement.prototype.close = function () { this.open = false; };
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });
const preview = () => ({ confirmationId: 'synthetic-confirmation', action: 'instance.stop' as const, resourceName: '测试实例', summary: '停止测试实例', expiresAt: new Date(Date.now() + 60000).toISOString(), requiresText: '测试实例' });

describe('two-phase cloud operation', () => {
  it('requires prepare and exact confirmation, retains one idempotency key on explicit retry', async () => {
    const api = new ApiClient('https://example.test');
    const prepare = vi.spyOn(api, 'prepare').mockResolvedValue(preview());
    const execute = vi.spyOn(api, 'execute').mockRejectedValueOnce(new Error('网络响应中断')).mockResolvedValueOnce({ operationId: 'synthetic-operation', status: 'submitted', message: '已受理' });
    const success = vi.fn();
    render(<ActionDialog api={api} resource={fixture().resources[0]} action="instance.stop" online onClose={vi.fn()} onSuccess={success} />);
    const user = userEvent.setup();
    expect(execute).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: '生成操作预览' }));
    expect(prepare).toHaveBeenCalledWith({ action: 'instance.stop', resourceId: 'synthetic-instance', region: 'region-test-1', params: {} });
    const confirm = await screen.findByRole('button', { name: '确认执行' });
    expect((confirm as HTMLButtonElement).disabled).toBe(true);
    const input = screen.getByLabelText('输入「测试实例」以确认');
    await user.type(input, '错误名称');
    expect((confirm as HTMLButtonElement).disabled).toBe(true);
    await user.clear(input); await user.type(input, '测试实例'); await user.click(confirm);
    await screen.findByRole('alert');
    expect(execute).toHaveBeenCalledOnce();
    await user.click(screen.getByRole('button', { name: '确认执行' }));
    await waitFor(() => expect(success).toHaveBeenCalledOnce());
    expect(execute.mock.calls[0]).toEqual(execute.mock.calls[1]);
    expect(execute.mock.calls[0][2]).toMatch(/^[a-f0-9-]{36}$/);
  });
  it('blocks expired previews and disconnected execution', async () => {
    const api = new ApiClient('https://example.test');
    vi.spyOn(api, 'prepare').mockResolvedValue({ ...preview(), expiresAt: '2000-01-01T00:00:00Z', requiresText: null });
    const execute = vi.spyOn(api, 'execute');
    const view = render(<ActionDialog api={api} resource={fixture().resources[0]} action="instance.stop" online onClose={vi.fn()} onSuccess={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: '生成操作预览' }));
    const confirm = await screen.findByRole('button', { name: '确认执行' });
    expect((confirm as HTMLButtonElement).disabled).toBe(true);
    view.rerender(<ActionDialog api={api} resource={fixture().resources[0]} action="instance.stop" online={false} onClose={vi.fn()} onSuccess={vi.fn()} />);
    fireEvent.click(confirm);
    expect(execute).not.toHaveBeenCalled();
  });
  it('requires a concrete NLB backend and sends its set and name', async () => {
    const api = new ApiClient('https://example.test');
    const prepare = vi.spyOn(api, 'prepare').mockResolvedValue({ ...preview(), action: 'nlb.backend.disable' });
    const resource = { ...fixture().resources[0], kind: 'nlb' as const, details: { backendSets: [{ name: 'test-set', backends: [{ name: 'synthetic-backend:443', isDrain: false }] }] } };
    render(<ActionDialog api={api} resource={resource} action="nlb.backend.disable" online onClose={vi.fn()} onSuccess={vi.fn()} />);
    expect((screen.getByRole('button', { name: '生成操作预览' }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('后端节点'), { target: { value: '0' } });
    fireEvent.click(screen.getByRole('button', { name: '生成操作预览' }));
    await waitFor(() => expect(prepare).toHaveBeenCalledWith(expect.objectContaining({ params: { backendSetName: 'test-set', backendName: 'synthetic-backend:443' } })));
    expect(extractBackends(resource.details)).toEqual([{ set: 'test-set', name: 'synthetic-backend:443', disabled: false }]);
  });
});
