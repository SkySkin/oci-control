import type { Snapshot } from './types';

// Deliberately synthetic; tests never load OCI configuration or a live API.
export function fixture(serverId = 'synthetic-account-a'): Snapshot {
  return {
    schemaVersion: 1, serverId, generatedAt: '2026-01-03T10:20:30Z', mode: 'demo',
    tenancy: { name: '测试账号', homeRegion: 'region-test-1' },
    regions: [{ id: 'region-test-1', name: '测试区域', isHome: true, status: 'ready', resourceCount: 1 }],
    resources: [{ id: 'synthetic-instance', name: '测试实例', kind: 'instance', region: 'region-test-1', compartment: '测试区间', state: 'RUNNING', actions: ['instance.stop', 'instance.rename'], cpuPercent: null }],
    cost: { currency: 'USD', monthToDate: null, previousMonth: 0, asOf: null, forecast: null, daily: [], byService: [], note: '测试账单未返回' },
    traffic: { todayBytes: null, monthBytes: null, officialMonthBytes: null, freeAllowanceBytes: null, asOf: null, source: 'unavailable', daily: [], note: '测试监测未返回' },
    alerts: [], errors: [],
  };
}
