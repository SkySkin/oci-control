export type ActionName = 'instance.start' | 'instance.stop' | 'instance.reboot' | 'instance.rename' | 'nlb.backend.enable' | 'nlb.backend.disable';
export type Session = {
  authenticated: boolean; csrfToken?: string; serverId?: string;
  version: string; mode: 'live' | 'demo'; capabilities?: { actions: string[] };
};
export type Region = { id: string; name: string; isHome: boolean; status: 'ready' | 'error'; resourceCount: number };
export type ResourceKind = 'instance' | 'nlb' | 'lb' | 'bootVolume' | 'blockVolume' | 'bucket' | 'vcn';
export type Resource = {
  id: string; name: string; kind: ResourceKind; region: string; compartment: string; state: string;
  shape?: string; ocpus?: number; memoryGb?: number; sizeGb?: number; publicIps?: string[]; privateIps?: string[];
  createdAt?: string; cpuPercent?: number | null; memoryPercent?: number | null; networkBytesOut?: number | null;
  freeEligible?: boolean | null; details?: Record<string, unknown>; actions: string[];
};
export type Cost = {
  currency: string; monthToDate: number | null; previousMonth: number | null; asOf: string | null;
  forecast: number | null; daily: { date: string; amount: number }[];
  byService: { name: string; amount: number }[]; note: string;
};
export type Traffic = {
  todayBytes: number | null; monthBytes: number | null; officialMonthBytes: number | null;
  freeAllowanceBytes: number | null; asOf: string | null; source: 'monitoring' | 'billing' | 'unavailable';
  daily: { date: string; bytes: number }[]; note: string;
  officialQuantity?: number | null; officialUnit?: string | null; officialAsOf?: string | null;
  officialSource?: 'usage_api'; officialStatus?: 'available' | 'unit_unverified' | 'partial' | 'unavailable'; officialNote?: string;
  officialSkus?: { skuPartNumber: string; skuName: string; service: string; unit: string; quantity: number | null }[];
};
export type Snapshot = {
  schemaVersion: 1; serverId: string; generatedAt: string; mode: 'live' | 'demo';
  tenancy: { name: string; homeRegion: string }; regions: Region[]; resources: Resource[];
  cost: Cost; traffic: Traffic;
  alerts: { id: string; level: 'info' | 'warning' | 'critical'; title: string; message: string; resourceId?: string }[];
  errors: { scope: string; message: string }[];
};
export type ServerStatus = { configured: boolean; cliInstalled: boolean; refreshing: boolean; lastError: string | null; lastRefreshAt: string | null };
export type AuditEvent = { id: string; at: string; action: string; resourceName: string; region: string; status: string; message: string };
export type PrepareRequest = { action: ActionName; region: string; resourceId: string; params: Record<string, string> };
export type Confirmation = { confirmationId: string; action: ActionName; resourceName: string; summary: string; expiresAt: string; requiresText: string | null };
export type Execution = { operationId: string; status: 'succeeded' | 'submitted'; message: string };
