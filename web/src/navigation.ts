import { useLayoutEffect, useState } from 'react';
import type { ResourceKind } from './types';

export type Page = 'overview' | 'resources' | 'traffic' | 'activity' | 'settings';
export type Route = { page: Page; resourceId: string | null; region: string; kind: ResourceKind | 'all'; query: string };
type Entry = { key: string; scroll: number; focus?: string; source?: string; parent?: string; overlay?: string };
type Layer = { id: string; close: () => void; blocked: () => boolean; previous: Entry; entry: Entry; hash: string; after?: () => void; pending?: boolean };
const layers: Layer[] = [];
const listeners = new Set<() => void>();
let returnTarget: { parent: string; detail: string; source: string } | null = null;
const pages = ['overview', 'resources', 'traffic', 'activity', 'settings'];
const kinds = ['instance', 'nlb', 'lb', 'bootVolume', 'blockVolume', 'bucket', 'vcn'];
const newEntry = (): Entry => ({ key: crypto.randomUUID(), scroll: 0 });
const readEntry = (): Entry => history.state?.ociRoute || newEntry();
const writeEntry = (entry: Entry, hash = location.hash) => history.replaceState({ ociRoute: entry }, '', hash || '#overview');
const notify = () => listeners.forEach(listener => listener());

export function readRoute(): Route {
  const [path, search = ''] = location.hash.slice(1).replace(/^\//, '').split('?');
  const [page, id] = path.split('/');
  const params = new URLSearchParams(search);
  let resourceId: string | null = null;
  try { resourceId = page === 'resources' && id ? decodeURIComponent(id) : null; } catch { /* invalid link falls back to list */ }
  return { page: pages.includes(page) ? page as Page : 'overview', resourceId, region: params.get('region') || 'all', kind: kinds.includes(params.get('kind') || '') ? params.get('kind') as ResourceKind : 'all', query: params.get('q') || '' };
}
function routeHash(route: Route) {
  const params = new URLSearchParams();
  if (route.region !== 'all') params.set('region', route.region);
  if (route.kind !== 'all') params.set('kind', route.kind);
  if (route.query) params.set('q', route.query);
  return `#${route.page}${route.resourceId ? `/${encodeURIComponent(route.resourceId)}` : ''}${params.size ? `?${params}` : ''}`;
}
function savePosition() {
  const active = document.activeElement as HTMLElement | null;
  writeEntry({ ...readEntry(), scroll: window.scrollY, focus: active?.id || undefined });
}
function onHistory() {
  const layer = layers.at(-1);
  if (layer && readEntry().overlay !== layer.id) {
    if (layer.blocked() && !layer.after) history.pushState({ ociRoute: layer.entry }, '', layer.hash);
    else { layers.pop(); layer.close(); layer.after?.(); }
    return;
  }
  const entry = readEntry();
  if (returnTarget) {
    const target = returnTarget;
    // A dismissed dialog can remain in Forward history as a duplicate detail.
    // Walk only that same known detail key; stop at its actual source entry.
    if (entry.key === target.detail) { history.back(); return; }
    returnTarget = null;
    if (entry.key !== target.parent) writeEntry(newEntry(), target.source);
  }
  // Forward never revives an old cloud confirmation or a dismissed local dialog.
  if (!layer && entry.overlay) { delete entry.overlay; writeEntry(entry); }
  notify();
}

export function useAppNavigation() {
  const [route, setRoute] = useState(readRoute);
  useLayoutEffect(() => {
    if (!history.state?.ociRoute) writeEntry(newEntry());
    const update = () => setRoute(readRoute());
    listeners.add(update);
    window.addEventListener('popstate', onHistory);
    window.addEventListener('hashchange', onHistory);
    history.scrollRestoration = 'manual';
    return () => { returnTarget = null; listeners.delete(update); window.removeEventListener('popstate', onHistory); window.removeEventListener('hashchange', onHistory); };
  }, []);
  useLayoutEffect(() => {
    const entry = readEntry();
    const target = (entry.focus && document.getElementById(entry.focus)) || document.getElementById('page-title');
    target?.focus({ preventScroll: true });
    window.scrollTo({ top: entry.scroll || 0, behavior: 'instant' });
  }, [route.page, route.resourceId]);
  const navigate = (page: string) => {
    if (!pages.includes(page)) return;
    if (page === route.page && !route.resourceId) return;
    savePosition();
    history.pushState({ ociRoute: newEntry() }, '', routeHash({ ...route, page: page as Page, resourceId: null }));
    notify();
  };
  const openResource = (id: string) => {
    savePosition();
    const parent = readEntry();
    const entry = { ...newEntry(), parent: parent.key, source: location.hash };
    history.pushState({ ociRoute: entry }, '', routeHash({ ...route, page: 'resources', resourceId: id }));
    notify();
  };
  const backFromDetail = () => {
    const entry = readEntry();
    if (returnTarget) return;
    if (entry.parent && entry.source) { returnTarget = { parent: entry.parent, detail: entry.key, source: entry.source }; history.back(); }
    else { writeEntry(newEntry(), '#resources'); notify(); }
  };
  const updateFilters = (values: Partial<Pick<Route, 'region' | 'kind' | 'query'>>) => {
    writeEntry(readEntry(), routeHash({ ...route, ...values }));
    notify();
  };
  return { route, navigate, openResource, backFromDetail, updateFilters };
}

export function registerBackLayer(close: () => void, blocked: () => boolean) {
  const previous = readEntry();
  const id = crypto.randomUUID();
  const entry = { ...previous, overlay: id };
  const layer = { id, close, blocked, previous, entry, hash: location.hash };
  layers.push(layer);
  history.pushState({ ociRoute: entry }, '', location.hash);
  // Standalone dialogs (e.g. login) also need browser-back support.
  if (!listeners.size) window.addEventListener('popstate', onHistory);
  return () => {
    const index = layers.indexOf(layer);
    if (index >= 0) layers.splice(index, 1);
    if (readEntry().overlay === id) history.back();
    if (!listeners.size) window.removeEventListener('popstate', onHistory);
  };
}
export function dismissTopLayer(after?: () => void, completed = false): boolean {
  const layer = layers.at(-1);
  if (!layer) return false;
  if (!layer.pending && (completed || !layer.blocked())) { layer.pending = true; layer.after = after; history.back(); }
  return true;
}
