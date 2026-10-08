import { useEffect, useState } from 'react';
import { isNative } from './api';
import { NativeChrome } from './native';

export type ThemePreference = 'system' | 'light' | 'dark';
export const themeKey = 'oci-control.theme';
export function readTheme(): ThemePreference {
  try { const value = localStorage.getItem(themeKey); return value === 'light' || value === 'dark' ? value : 'system'; } catch { return 'system'; }
}
export function useTheme() {
  const [theme, setTheme] = useState<ThemePreference>(readTheme);
  const [warning, setWarning] = useState('');
  useEffect(() => {
    const media = window.matchMedia?.('(prefers-color-scheme: dark)');
    const apply = () => {
      const resolved = theme === 'system' ? media?.matches ? 'dark' : 'light' : theme;
      document.documentElement.dataset.theme = resolved;
      document.documentElement.dataset.native = String(isNative);
      const backgroundColor = resolved === 'dark' ? '#101418' : '#f7f9fc';
      document.querySelector('meta[name="theme-color"]')?.setAttribute('content', backgroundColor);
      if (isNative) void NativeChrome.setTheme({ theme: resolved, backgroundColor }).catch(() => {});
    };
    apply(); media?.addEventListener('change', apply);
    return () => media?.removeEventListener('change', apply);
  }, [theme]);
  const changeTheme = (value: ThemePreference) => {
    setTheme(value);
    try { localStorage.setItem(themeKey, value); setWarning(''); } catch { setWarning('本机存储不可用，本次外观选择仅在当前页面生效。'); }
  };
  return { theme, changeTheme, themeWarning: warning };
}
