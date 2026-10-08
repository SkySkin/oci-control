import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { useTheme, themeKey } from './theme';

afterEach(() => { cleanup(); vi.restoreAllMocks(); localStorage.clear(); });
it('follows system by default, persists explicit themes, and responds when system mode resumes', () => {
  let dark = false; let changed!: () => void;
  vi.stubGlobal('matchMedia', vi.fn(() => ({ get matches() { return dark; }, addEventListener: (_event: string, callback: () => void) => { changed = callback; }, removeEventListener: vi.fn() })));
  const { result } = renderHook(useTheme);
  expect(result.current.theme).toBe('system'); expect(document.documentElement.dataset.theme).toBe('light');
  act(() => { dark = true; changed(); }); expect(document.documentElement.dataset.theme).toBe('dark');
  act(() => result.current.changeTheme('light')); expect(localStorage.getItem(themeKey)).toBe('light');
  act(() => { dark = true; changed(); }); expect(document.documentElement.dataset.theme).toBe('light');
  act(() => result.current.changeTheme('system')); expect(document.documentElement.dataset.theme).toBe('dark');
  vi.unstubAllGlobals();
});
