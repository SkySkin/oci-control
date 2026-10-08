import { App as NativeApp } from '@capacitor/app';
import { registerPlugin } from '@capacitor/core';
import { useEffect, useRef } from 'react';
import { isNative } from './api';
import { dismissTopLayer } from './navigation';

export const NativeChrome = registerPlugin<{ setTheme(options: { theme: 'light' | 'dark'; backgroundColor: string }): Promise<void> }>('NativeChrome');

export function useNativeLifecycle(back: () => boolean, resume: () => void) {
  const callbacks = useRef({ back, resume });
  callbacks.current = { back, resume };
  useEffect(() => {
    if (!isNative) return;
    let disposed = false;
    const handlers = [
      NativeApp.addListener('backButton', () => {
        if (!dismissTopLayer() && !callbacks.current.back()) void NativeApp.minimizeApp().catch(() => {});
      }),
      NativeApp.addListener('resume', () => callbacks.current.resume()),
    ];
    handlers.forEach(promise => { void promise.then(handle => { if (disposed) void handle.remove(); }).catch(() => {}); });
    return () => { disposed = true; handlers.forEach(promise => { void promise.then(handle => handle.remove()).catch(() => {}); }); };
  }, []);
}
