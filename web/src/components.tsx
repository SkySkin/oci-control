import { useEffect, useId, useRef, useState } from 'react';
import { dismissTopLayer, registerBackLayer } from './navigation';
import type { ReactNode } from 'react';
import { AlertCircle, ArrowDownToLine, Check, ChevronRight, Cloud, Database, Globe2, HardDrive, Network, Server, ShieldCheck, X } from 'lucide-react';
import type { Region, Resource, ResourceKind } from './types';
import { bytes, dateTime, kindNames, number, stateLabel, stateTone } from './format';

export function Brand({ compact = false }: { compact?: boolean }) {
  return <div className="brand"><svg viewBox="0 0 48 48" aria-hidden="true"><path d="m11 29 13-17 13 17M16 23h16M11 35h26" /><circle cx="24" cy="29" r="3" /></svg><div><strong>云境</strong>{!compact && <span>OCI Control</span>}</div></div>;
}
export function ResourceIcon({ kind, size = 19 }: { kind: ResourceKind; size?: number }) {
  const Icon = ({ instance: Server, nlb: Network, lb: Network, bootVolume: HardDrive, blockVolume: Database, bucket: Cloud, vcn: Globe2 })[kind] || Server;
  return <Icon size={size} aria-hidden="true" strokeWidth={1.65} />;
}
export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: string }) { return <span className={`badge ${tone}`}><span className="status-dot" />{children}</span>; }
export function StateBadge({ state }: { state: string }) { return <Badge tone={stateTone(state)}>{stateLabel(state)}</Badge>; }
export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return <div className="empty-state"><div className="empty-mark"><Cloud size={28} aria-hidden="true" strokeWidth={1.25} /></div><h3>{title}</h3>{children && <p>{children}</p>}{action}</div>;
}
export function ErrorNotice({ children }: { children: ReactNode }) { return <div className="notice danger" role="alert"><AlertCircle size={18} aria-hidden="true" /><div>{children}</div></div>; }
export function Modal({ title, children, onClose, busy = false }: { title: string; children: ReactNode; onClose: () => void; busy?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  const callbacks = useRef({ onClose, busy });
  callbacks.current = { onClose, busy };
  const id = useId();
  const close = () => { if (!callbacks.current.busy && !dismissTopLayer()) callbacks.current.onClose(); };
  useEffect(() => {
    const dialog = ref.current!;
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    dialog.showModal();
    // Prefer the safe action, never autofocus a destructive confirmation.
    (dialog.querySelector('[autofocus]') as HTMLElement | null)?.focus();
    let disposed = false;
    let unregister: (() => void) | undefined;
    void Promise.resolve().then(() => {
      if (!disposed) unregister = registerBackLayer(() => callbacks.current.onClose(), () => callbacks.current.busy);
    });
    const viewport = window.visualViewport;
    const resize = () => {
      dialog.style.setProperty('--viewport-height', `${viewport?.height || window.innerHeight}px`);
      if (dialog.contains(document.activeElement)) (document.activeElement as HTMLElement)?.scrollIntoView?.({ block: 'nearest' });
    };
    resize(); viewport?.addEventListener('resize', resize);
    return () => {
      disposed = true; unregister?.(); viewport?.removeEventListener('resize', resize);
      dialog.close(); document.body.style.overflow = overflow;
      if (previous?.isConnected) previous.focus({ preventScroll: true });
    };
  }, []);
  return <dialog ref={ref} className="modal" aria-labelledby={id} aria-busy={busy} onCancel={event => { event.preventDefault(); close(); }}><div className="modal-heading"><h2 id={id}>{title}</h2><button type="button" className="icon-button" aria-label="关闭对话框" disabled={busy} onClick={close}><X size={22} /></button></div>{children}</dialog>;
}

export function RegionAtlas({ regions, selected, onSelect }: { regions: Region[]; selected: string; onSelect: (id: string) => void }) {
  return <section className="region-atlas" aria-label="区域资源分布"><div className="section-heading"><div><h2>区域视图</h2><p>选择区域，聚焦资源</p></div><button className={`text-button ${selected === 'all' ? 'selected' : ''}`} onClick={() => onSelect('all')}>全部区域 <ChevronRight size={15} aria-hidden="true" /></button></div>
    {regions.length === 0 ? <Empty title="尚无区域数据">首次采集完成后，这里将显示已授权区域。</Empty> : <div className="atlas-body"><div className="atlas-origin"><div className="atlas-origin-icon"><Globe2 size={25} strokeWidth={1.25} aria-hidden="true" /></div><span>云资源</span><small>{regions.length} 个区域</small></div><div className="region-nodes">{regions.map(region => <button key={region.id} className={`region-node ${selected === region.id ? 'selected' : ''}`} aria-pressed={selected === region.id} onClick={() => onSelect(region.id)}><span className={`node-point ${region.status}`} /><div className="region-node-label"><strong>{region.name || region.id}</strong><small>{region.id}</small></div><span className="region-count">{number(region.resourceCount)}<small>资源</small></span><span className="region-note">{region.status === 'error' ? '采集异常' : region.isHome ? '主区域' : '已采集'}</span></button>)}</div></div>}
  </section>;
}

type Point = { date: string; value: number };
export function DataChart({ points, format, label, tone = 'blue' }: { points: Point[]; format: (n: number) => string; label: string; tone?: 'blue' | 'teal' }) {
  const id = useId();
  const [active, setActive] = useState<number | null>(null);
  const usable = points.filter(p => Number.isFinite(p.value) && Number.isFinite(Date.parse(p.date))).sort((a, b) => Date.parse(a.date) - Date.parse(b.date));
  if (!usable.length) return <div className="chart-empty"><div className="chart-empty-lines" aria-hidden="true"><i /><i /><i /></div><div><span>暂无可绘制的数据</span><small>采集可用后显示趋势，缺失数据不计为 0。</small></div></div>;
  const width = 680, height = 180, left = 0, right = 8, top = 12, bottom = 24;
  const minTime = Date.parse(usable[0].date), maxTime = Date.parse(usable.at(-1)!.date);
  const maximum = Math.max(...usable.map(p => p.value), 1);
  const minimum = Math.min(...usable.map(p => p.value), 0);
  const x = (p: Point) => usable.length === 1 ? width / 2 : left + (Date.parse(p.date) - minTime) / Math.max(maxTime - minTime, 1) * (width - left - right);
  const y = (value: number) => top + (maximum - value) / (maximum - minimum) * (height - top - bottom);
  // Split at missing calendar days. A absent day never becomes a zero or a line bridge.
  const segments: Point[][] = [];
  usable.forEach((p, index) => { if (!index || Date.parse(p.date) - Date.parse(usable[index - 1].date) > 36 * 3600_000) segments.push([]); segments.at(-1)!.push(p); });
  const chosen = active == null ? null : usable[active];
  return <div className={`data-chart ${tone}`}><div className="chart-summary"><span>{label}</span><strong>{chosen ? `${chosen.date.slice(5, 10)}  ${format(chosen.value)}` : `最高 ${format(maximum === 1 && usable.every(p => p.value === 0) ? 0 : maximum)}`}</strong></div><svg className="chart-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${label}，${usable.length} 个采样日。下方可展开完整数据表。`}>
    <defs><linearGradient id={id} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="currentColor" stopOpacity=".18" /><stop offset="100%" stopColor="currentColor" stopOpacity="0" /></linearGradient></defs>
    {[0, .5, 1].map(n => <line key={n} className="chart-grid" x1={left} x2={width - right} y1={top + n * (height - top - bottom)} y2={top + n * (height - top - bottom)} />)}
    {segments.map((segment, index) => <g key={index}><path d={`M${segment.map(p => `${x(p)},${y(p.value)}`).join(' L')} L${x(segment.at(-1)!)},${y(minimum)} L${x(segment[0])},${y(minimum)} Z`} fill={`url(#${id})`} /><path d={`M${segment.map(p => `${x(p)},${y(p.value)}`).join(' L')}`} fill="none" stroke="currentColor" strokeWidth="2" vectorEffect="non-scaling-stroke" /></g>)}
    {usable.map((p, index) => <circle key={`${p.date}-${index}`} cx={x(p)} cy={y(p.value)} r={active === index ? 5 : 2.5} fill="currentColor" onMouseEnter={() => setActive(index)} onMouseLeave={() => setActive(null)}><title>{p.date}: {format(p.value)}</title></circle>)}
  </svg><div className="chart-dates"><span>{usable[0].date.slice(5, 10)}</span><span>{usable.at(-1)!.date.slice(5, 10)}</span></div><details className="chart-table"><summary>查看每日数据</summary><table><thead><tr><th>日期</th><th>{label}</th></tr></thead><tbody>{usable.map((p, i) => <tr key={`${p.date}-${i}`}><td>{p.date.slice(0, 10)}</td><td>{format(p.value)}</td></tr>)}</tbody></table></details></div>;
}

export function ResourceTable({ resources, onSelect, compact = false }: { resources: Resource[]; onSelect: (r: Resource) => void; compact?: boolean }) {
  if (!resources.length) return <Empty title="没有匹配的资源">尝试切换区域、类型或搜索词。只显示当前账号已授权的资源。</Empty>;
  return <div className="resource-list"><div className={`resource-table-heading ${compact ? 'compact' : ''}`} aria-hidden="true"><span>资源名称 / 类型</span><span>区域</span><span>状态</span>{!compact && <span>规格 / 容量</span>}<span /></div>{resources.map(resource => <button className={`resource-row ${compact ? 'compact' : ''}`} key={resource.id} id={`resource-${encodeURIComponent(resource.id)}`} onClick={() => onSelect(resource)} aria-label={`查看 ${resource.name}，${kindNames[resource.kind]}，${stateLabel(resource.state)}`}><div className="resource-name"><span className={`resource-symbol ${resource.kind}`}><ResourceIcon kind={resource.kind} /></span><span><strong>{resource.name}</strong><small>{kindNames[resource.kind]}</small></span></div><span className="resource-region">{resource.region}</span><StateBadge state={resource.state} />{!compact && <span className="resource-spec">{resource.shape || (resource.sizeGb != null ? `${number(resource.sizeGb)} GB` : '—')}</span>}<ChevronRight className="row-chevron" size={16} aria-hidden="true" /></button>)}</div>;
}

export function ResourceDetail({ resource, canOperate, allowedActions, onAction }: { resource: Resource; canOperate: boolean; allowedActions: string[]; onAction: (action: string) => void }) {
  const fields = [
    ['区域', resource.region], ['区间', resource.compartment], ['规格', resource.shape],
    ['OCPU', resource.ocpus == null ? undefined : number(resource.ocpus, 2)],
    ['内存', resource.memoryGb == null ? undefined : `${number(resource.memoryGb, 2)} GB`],
    ['存储容量', resource.sizeGb == null ? undefined : `${number(resource.sizeGb)} GB`],
    ['创建时间', resource.createdAt ? dateTime(resource.createdAt) : undefined],
    ['公共 IP', resource.publicIps?.join('、')], ['私有 IP', resource.privateIps?.join('、')],
  ].filter(([, value]) => value);
  return <section className="resource-detail" aria-label={`${resource.name} 详情`}><div className="detail-heading"><span className="resource-symbol"><ResourceIcon kind={resource.kind} size={23} /></span></div><h2>{resource.name}</h2><div className="detail-status"><span>{kindNames[resource.kind]}</span><StateBadge state={resource.state} /></div><dl className="detail-fields">{fields.map(([key, value]) => <div key={key} className={['规格', '区间', '创建时间', '公共 IP', '私有 IP'].includes(key || '') ? 'wide-field' : undefined}><dt>{key}</dt><dd>{value}</dd></div>)}</dl><details className="resource-id"><summary>资源标识</summary><code>{resource.id}</code></details>{resource.kind === 'instance' && <div className="detail-metrics"><div><span>CPU</span><strong>{resource.cpuPercent == null ? '暂无数据' : `${number(resource.cpuPercent, 1)}%`}</strong></div><div><span>内存使用</span><strong>{resource.memoryPercent == null ? '暂无数据' : `${number(resource.memoryPercent, 1)}%`}</strong></div><div><span>监测出站流量</span><strong>{bytes(resource.networkBytesOut)}</strong></div></div>}
    {(resource.kind === 'nlb' || resource.kind === 'lb') && <NetworkTopology details={resource.details} />}
    <div className="detail-actions"><h3>资源操作</h3><p>{canOperate ? '提交前将读取当前状态，并生成操作预览。' : '当前为只读视图。连接并登录后可准备操作。'}</p><div className="action-buttons">{allowedActions.length ? allowedActions.map(action => <button key={action} className={`button secondary ${action.includes('stop') || action.includes('disable') ? 'danger-text' : ''}`} disabled={!canOperate} onClick={() => onAction(action)}>{action === 'instance.start' ? <Check size={16} aria-hidden="true" /> : action === 'instance.stop' ? <ArrowDownToLine size={16} aria-hidden="true" /> : <ShieldCheck size={16} aria-hidden="true" />}{({ 'instance.start': '启动', 'instance.stop': '停止', 'instance.reboot': '重启', 'instance.rename': '重命名', 'nlb.backend.enable': '启用后端', 'nlb.backend.disable': '停用后端' } as Record<string, string>)[action]}</button>) : <span className="muted">此资源暂不支持可用操作</span>}</div></div>
  </section>;
}

function NetworkTopology({ details }: { details?: Record<string, unknown> }) {
  const rawSets = details?.backendSets;
  const sets = (Array.isArray(rawSets) ? rawSets : rawSets && typeof rawSets === 'object' ? Object.entries(rawSets).map(([name, value]) => ({ ...(value as object), name })) : []) as { name: string; health?: string; backends?: { name: string; health?: string; isOffline?: boolean; isDrain?: boolean }[] }[];
  const listeners = Array.isArray(details?.listeners) ? details.listeners as { name: string; protocol?: string; port?: number; defaultBackendSetName?: string }[] : [];
  const healthLabel = (value?: string) => ({ OK: '健康', WARNING: '告警', CRITICAL: '严重', UNKNOWN: '未知' } as Record<string, string>)[value || ''] || '未知';
  return <section className="network-topology"><h3>转发拓扑</h3>{listeners.length ? listeners.map(listener => <div className="listener-node" key={listener.name}><Network size={15} aria-hidden="true" /><div><strong>{listener.name}</strong><span>{listener.protocol || '未知协议'} {listener.port ?? '—'} · {listener.defaultBackendSetName || '未指定后端集'}</span></div></div>) : <p className="muted">暂无监听器数据</p>}<div className="backend-sets">{sets.map(set => <div className="backend-set" key={set.name}><div className="backend-set-heading"><strong>{set.name}</strong><span>{healthLabel(set.health)}</span></div>{set.backends?.length ? set.backends.map(backend => <div className="backend-node" key={backend.name}><Server size={13} aria-hidden="true" /><div><strong>{backend.name}</strong><span>{backend.isOffline ? '已停用' : backend.isDrain ? '排空中' : '已启用'} · {healthLabel(backend.health)}</span></div></div>) : <p className="muted">暂无后端节点</p>}</div>)}</div>{typeof details?.topologyNote === 'string' && <p className="topology-note">{details.topologyNote}</p>}</section>;
}
