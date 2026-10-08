import type { Snapshot } from './types';

const prefix = 'oci-control.snapshot.v1.';
const indexKey = (origin: string) => `${prefix}index.${encodeURIComponent(origin)}`;
const snapshotKey = (origin: string, serverId: string) => `${prefix}data.${encodeURIComponent(origin)}.${encodeURIComponent(serverId)}`;
export function isSnapshot(value: unknown): value is Snapshot {
  if (!value || typeof value !== 'object') return false;
  const s = value as Snapshot;
  return s.schemaVersion === 1 && typeof s.serverId === 'string' && !!s.serverId && Number.isFinite(Date.parse(s.generatedAt)) &&
    ['live', 'demo'].includes(s.mode) && !!s.tenancy && typeof s.tenancy.name === 'string' && Array.isArray(s.regions) &&
    s.regions.every(r => !!r && typeof r.id === 'string' && typeof r.name === 'string' && ['ready', 'error'].includes(r.status) && Number.isFinite(r.resourceCount)) &&
    Array.isArray(s.resources) && s.resources.every(r => !!r && typeof r.id === 'string' && typeof r.name === 'string' && typeof r.state === 'string' && typeof r.region === 'string' && typeof r.compartment === 'string' && ['instance', 'nlb', 'lb', 'bootVolume', 'blockVolume', 'bucket', 'vcn'].includes(r.kind) && Array.isArray(r.actions)) &&
    !!s.cost && Array.isArray(s.cost.daily) && Array.isArray(s.cost.byService) && !!s.traffic && Array.isArray(s.traffic.daily) && Array.isArray(s.alerts) && Array.isArray(s.errors);
}
export function saveSnapshot(origin: string, snapshot: Snapshot): boolean {
  if (!isSnapshot(snapshot)) return false;
  try {
    localStorage.setItem(snapshotKey(origin, snapshot.serverId), JSON.stringify(snapshot));
    localStorage.setItem(indexKey(origin), snapshot.serverId);
    return true;
  } catch { return false; }
}
export function readSnapshot(origin: string, serverId?: string): Snapshot | null {
  try {
    const id = serverId ?? localStorage.getItem(indexKey(origin));
    if (!id) return null;
    const snapshot: unknown = JSON.parse(localStorage.getItem(snapshotKey(origin, id)) || 'null');
    return isSnapshot(snapshot) && snapshot.serverId === id ? snapshot : null;
  } catch { return null; }
}
export function purgeSnapshots(origin: string): void {
  const dataPrefix = `${prefix}data.${encodeURIComponent(origin)}.`;
  try {
    const keys = Array.from({ length: localStorage.length }, (_, i) => localStorage.key(i));
    keys.forEach(key => { if (key?.startsWith(dataPrefix) || key === indexKey(origin)) localStorage.removeItem(key); });
  } catch { throw new Error('无法清除本机快照，请检查浏览器存储权限。'); }
}
export type ServerPreference = { url: string; allowHttp: boolean };
export function readServerPreference(): ServerPreference | null {
  try {
    const value = JSON.parse(localStorage.getItem('oci-control.server') || 'null');
    return value && typeof value.url === 'string' && typeof value.allowHttp === 'boolean' ? value : null;
  } catch { return null; }
}
export function saveServerPreference(value: ServerPreference) { localStorage.setItem('oci-control.server', JSON.stringify(value)); }
