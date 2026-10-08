import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { ActivityPage, TrafficPage } from './pages';
import { ApiClient } from './api';
import { fixture } from './test-fixtures';

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it('shows unconverted Oracle raw quantity even when official bytes are unknown and cost is zero', () => {
  const snapshot = fixture();
  snapshot.cost.monthToDate = 0;
  snapshot.traffic.officialQuantity = 12.345678;
  snapshot.traffic.officialUnit = 'GB Months';
  snapshot.traffic.officialAsOf = '2026-01-02T00:00:00Z';
  snapshot.traffic.officialStatus = 'unit_unverified';
  snapshot.traffic.officialNote = '合成计量：保留原始单位，字节换算未核实。';
  snapshot.traffic.officialSkus = [{ skuPartNumber: 'synthetic-sku', skuName: '测试出站计量', service: '测试网络', unit: 'GB Months', quantity: 12.345678 }];
  render(<TrafficPage snapshot={snapshot} />);
  expect(screen.getByText('Oracle 原始计量')).toBeTruthy();
  expect(screen.getAllByText('12.345678 GB Months')).toHaveLength(2);
  expect(screen.getByText('字节换算未核实')).toBeTruthy();
  expect(screen.getByText(/合成计量：保留原始单位/)).toBeTruthy();
  expect(screen.queryByText('12.35 GiB')).toBeNull();
  expect(screen.getByText(/截至 2026/)).toBeTruthy();
});

it('preserves an actual raw zero, while absent official values remain unknown', () => {
  const snapshot = fixture();
  snapshot.traffic.officialQuantity = 0; snapshot.traffic.officialUnit = 'GB Months';
  const view = render(<TrafficPage snapshot={snapshot} />);
  expect(screen.getByText('0 GB Months')).toBeTruthy();
  snapshot.traffic.officialQuantity = null;
  view.rerender(<TrafficPage snapshot={snapshot} />);
  expect(screen.queryByText('0 GB Months')).toBeNull();
  expect(screen.getByText('官方出站量').nextElementSibling?.textContent).toBe('暂无数据');
});

it('uses Chinese labels for durable executing and unknown audit outcomes', async () => {
  const api = new ApiClient('https://example.test');
  vi.spyOn(api, 'audit').mockResolvedValue({ events: ['executing', 'unknown'].map((status, i) => ({ id: `synthetic-${i}`, action: 'instance.stop', resourceName: '测试实例', region: '测试区域', status, message: '合成审计记录', at: '2026-01-03T00:00:00Z' })) });
  render(<ActivityPage api={api} online reloadKey={0} />);
  await screen.findByText('执行中');
  expect(screen.getByText('结果待核实')).toBeTruthy();
  expect(screen.queryByText('executing')).toBeNull();
  expect(screen.queryByText('unknown')).toBeNull();
});
