import type { Snapshot } from './types';

const prefix = 'oci-control.snapshot.v1.';
const indexKey = (origin: string) => `${prefix}index.${encodeURIComponent(origin)}`;
const snapshotKey = (origin: string, serverId: string) => `${prefix}data.${encodeURIComponent(origin)}.${encodeURIComponent(serverId)}`;
type ObjectValue = Record<string, unknown>;
const object = (value: unknown): value is ObjectValue => !!value && typeof value === 'object' && !Array.isArray(value);
const text = (value: unknown): value is string => typeof value === 'string';
const finite = (value: unknown) => typeof value === 'number' && Number.isFinite(value);
const nullableNumber = (value: unknown) => value == null || finite(value);
const date = (value: unknown) => text(value) && Number.isFinite(Date.parse(value));
const list = (value: unknown, valid: (item: unknown) => boolean) => Array.isArray(value) && value.every(valid);
const optional = (value: unknown, valid: (item: unknown) => boolean) => value === undefined || valid(value);
const nullableText = (value: unknown) => value == null || text(value);
const metricDay = (field: string) => (value: unknown) => object(value) && date(value.date) && finite(value[field]);
function validDetails(value: unknown): boolean {
  if (!object(value)) return false;
  if (value.topologyNote !== undefined && !text(value.topologyNote)) return false;
  if (value.listeners !== undefined && !list(value.listeners, item => object(item) && text(item.name) && optional(item.protocol, text) && optional(item.port, finite) && nullableText(item.defaultBackendSetName))) return false;
  if (value.backendSets !== undefined) {
    if (!Array.isArray(value.backendSets) && !object(value.backendSets)) return false;
    const sets = Array.isArray(value.backendSets) ? value.backendSets : Object.values(value.backendSets);
    if (!sets.every(item => object(item) && optional(item.name, text) && nullableText(item.health) && optional(item.backends, value => list(value, backend => object(backend) && text(backend.name) && nullableText(backend.health))))) return false;
  }
  return true;
}
export function isSnapshot(value: unknown): value is Snapshot {
  if (!object(value)) return false;
  const s = value;
  if (s.schemaVersion !== 1 || !text(s.serverId) || !s.serverId || !date(s.generatedAt) || !['live', 'demo'].includes(String(s.mode))) return false;
  if (!object(s.tenancy) || !text(s.tenancy.name) || !text(s.tenancy.homeRegion)) return false;
  if (!list(s.regions, r => object(r) && text(r.id) && text(r.name) && ['ready', 'error'].includes(String(r.status)) && finite(r.resourceCount))) return false;
  if (!list(s.resources, r => object(r) && ['id', 'name', 'state', 'region', 'compartment'].every(key => text(r[key])) && ['instance', 'nlb', 'lb', 'bootVolume', 'blockVolume', 'bucket', 'vcn'].includes(String(r.kind)) && list(r.actions, text) && ['shape', 'createdAt'].every(key => optional(r[key], text)) && ['ocpus', 'memoryGb', 'sizeGb', 'cpuPercent', 'memoryPercent', 'networkBytesOut'].every(key => nullableNumber(r[key])) && ['publicIps', 'privateIps'].every(key => optional(r[key], value => list(value, text))) && optional(r.details, validDetails))) return false;
  if (!object(s.cost) || !object(s.traffic)) return false;
  const c = s.cost, t = s.traffic;
  if (!text(c.currency) || !text(c.note) || !['monthToDate', 'previousMonth', 'forecast'].every(key => nullableNumber(c[key])) || !(c.asOf == null || date(c.asOf)) || !list(c.daily, metricDay('amount')) || !list(c.byService, item => object(item) && text(item.name) && finite(item.amount))) return false;
  if (!text(t.note) || !['monitoring', 'billing', 'unavailable'].includes(String(t.source)) || !['todayBytes', 'monthBytes', 'officialMonthBytes', 'freeAllowanceBytes', 'officialQuantity'].every(key => nullableNumber(t[key])) || !(t.asOf == null || date(t.asOf)) || !list(t.daily, metricDay('bytes'))) return false;
  if (!(t.officialUnit == null || text(t.officialUnit)) || !['officialNote', 'officialStatus'].every(key => optional(t[key], text)) || !(t.officialAsOf == null || date(t.officialAsOf))) return false;
  if (!optional(t.officialSkus, value => list(value, item => object(item) && ['skuName', 'skuPartNumber', 'unit', 'service'].every(key => text(item[key])) && nullableNumber(item.quantity)))) return false;
  return list(s.alerts, item => object(item) && ['id', 'title', 'message'].every(key => text(item[key])) && ['info', 'warning', 'critical'].includes(String(item.level)) && optional(item.resourceId, text)) && list(s.errors, item => object(item) && text(item.scope) && text(item.message));
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
