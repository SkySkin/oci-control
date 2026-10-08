import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
const native = vi.hoisted(() => ({ listeners: {} as Record<string, () => void>, minimize: vi.fn(), remove: vi.fn() }));
vi.mock('./api', () => ({ isNative: true }));
vi.mock('@capacitor/app', () => ({ App: { addListener: vi.fn(async (event: string, callback: () => void) => { native.listeners[event] = callback; return { remove: native.remove }; }), minimizeApp: () => { native.minimize(); return Promise.resolve(); } } }));
import { useNativeLifecycle } from './native';
afterEach(() => { cleanup(); vi.clearAllMocks(); });
it('only minimizes at the root, delegates detail back and resumes through the current read callback', async () => {
  const back = vi.fn(() => true), resume = vi.fn();
  const view = renderHook(() => useNativeLifecycle(back, resume));
  await act(async () => {});
  native.listeners.backButton(); expect(back).toHaveBeenCalledOnce(); expect(native.minimize).not.toHaveBeenCalled();
  back.mockReturnValue(false); native.listeners.backButton(); expect(native.minimize).toHaveBeenCalledOnce();
  native.listeners.resume(); expect(resume).toHaveBeenCalledOnce();
  view.unmount(); await act(async () => {}); expect(native.remove).toHaveBeenCalledTimes(2);
});
