import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react(), {
    name: 'offline-app-shell',
    enforce: 'post',
    generateBundle(_options, bundle) {
      const files = Object.keys(bundle).filter(file => /\.(js|css|woff2)$/.test(file));
      const version = files.find(file => /index.*\.js$/.test(file)) || 'v1';
      // Only versioned public assets and the static HTML shell enter this cache.
      // API responses, credentials and snapshots are never service-worker cached.
      this.emitFile({ type: 'asset', fileName: 'sw.js', source: `
const CACHE = ${JSON.stringify(`oci-control-shell-${version}`)};
const ASSETS = ${JSON.stringify(['/', '/mark.svg', ...files.map(file => `/${file}`)])};
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('oci-control-shell-') && key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return;
  if (event.request.mode === 'navigate') {
    event.respondWith(fetch(event.request).catch(() => caches.open(CACHE).then(cache => cache.match('/')).then(response => response || Response.error())));
  } else if (ASSETS.includes(url.pathname)) {
    event.respondWith(caches.open(CACHE).then(cache => cache.match(event.request)).then(cached => cached || fetch(event.request)));
  }
});
` });
    },
  }],
  server: { proxy: { '/api': 'http://127.0.0.1:8787' } },
  test: { environment: 'jsdom', clearMocks: true },
});
