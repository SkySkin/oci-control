import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Activity, ArrowLeft, ChartNoAxesCombined, CircleHelp, LayoutDashboard, ListFilter, LogIn, RefreshCw, Search, Server, Settings2, Wifi, WifiOff } from 'lucide-react';
import { ApiClient, ApiError, isNative, normalizeServerUrl } from './api';
import { isSnapshot, purgeSnapshots, readServerPreference, readSnapshot, saveServerPreference, saveSnapshot } from './cache';
import { Badge, Brand, Empty, ErrorNotice, RegionAtlas, ResourceDetail, ResourceTable } from './components';
import ActionDialog from './ActionDialog';
import { ActivityPage, LoginPage, Overview, PurgeDialog, SettingsPage, SnapshotFooter, TrafficPage } from './pages';
import { dateTime, kindNames } from './format';
import type { ActionName, ResourceKind, ServerStatus, Session, Snapshot } from './types';

const navigation = [
  { id: 'overview', label: '总览', title: '云资源总览', description: '每一处资源，都在视野之内。', icon: LayoutDashboard },
  { id: 'resources', label: '资源', title: '资源工作台', description: '探索区域、检查状态，准备下一次操作。', icon: Server },
  { id: 'traffic', label: '费用与流量', title: '费用与流量', description: '读懂用量，也看清数据的边界。', icon: ChartNoAxesCombined },
  { id: 'activity', label: '活动记录', title: '活动记录', description: '每一次操作，都有可追溯的结果。', icon: Activity },
  { id: 'settings', label: '设置', title: '连接与设置', description: '管理服务器、登录会话和本机数据。', icon: Settings2 },
] as const;
type Page = typeof navigation[number]['id'];
const allowedActions = new Set(['instance.start', 'instance.stop', 'instance.reboot', 'instance.rename', 'nlb.backend.enable', 'nlb.backend.disable']);
function currentPage(): Page { const page = window.location.hash.slice(1).split('?')[0]; return navigation.some(n => n.id === page) ? page as Page : 'overview'; }
function initialOrigin() {
  if (!isNative) return window.location.origin;
  const preference = readServerPreference();
  try { return preference ? normalizeServerUrl(preference.url, preference.allowHttp) : ''; } catch { return ''; }
}

export default function App() {
  const [origin, setOrigin] = useState(initialOrigin);
  const api = useMemo(() => new ApiClient(origin), [origin]);
  const requestContext = useRef({ origin, api });
  requestContext.current = { origin, api };
  const [session, setSession] = useState<Session | null>(null);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [saved, setSaved] = useState<Snapshot | null>(() => readSnapshot(origin));
  const [status, setStatus] = useState<ServerStatus | null>(null);
  const [connected, setConnected] = useState(false);
  const [checking, setChecking] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [offlineView, setOfflineView] = useState(false);
  const [error, setError] = useState('');
  const [cacheWarning, setCacheWarning] = useState('');
  const [page, setPage] = useState<Page>(currentPage);
  const [region, setRegion] = useState('all');
  const [kind, setKind] = useState<ResourceKind | 'all'>('all');
  const [query, setQuery] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [action, setAction] = useState<ActionName | null>(null);
  const [purge, setPurge] = useState(false);
  const [auditRevision, setAuditRevision] = useState(0);
  const [toast, setToast] = useState('');
  const generation = useRef(0);
  const inFlight = useRef(false);
  const activeSession = useRef<Session | null>(null);

  const loadData = useCallback(async (currentSession: Session, ticket: number) => {
    const results = await Promise.allSettled([api.snapshot(), api.status()]);
    if (ticket !== generation.current) return;
    const [snapResult, statusResult] = results;
    if (statusResult.status === 'fulfilled') setStatus(statusResult.value);
    if (results.some(result => result.status === 'rejected' && result.reason instanceof ApiError && result.reason.status === 401)) {
      setSession(null); activeSession.current = null; setSnapshot(null); setConnected(false); setAction(null); setError('登录会话已失效，请重新登录。'); return;
    }
    if (snapResult.status === 'fulfilled') {
      if (!isSnapshot(snapResult.value) || snapResult.value.serverId !== currentSession.serverId) {
        setConnected(false); setSnapshot(null); setError('快照身份与当前服务器不一致，已停止显示。请重新连接。'); return;
      }
      setSnapshot(snapResult.value); setSaved(snapResult.value); setConnected(true); setError('');
      setCacheWarning(saveSnapshot(origin, snapResult.value) ? '' : '本机存储不可用或空间不足，本次快照未能保存供离线查看。');
    } else {
      const e = snapResult.reason;
      setConnected(e instanceof ApiError && e.status > 0);
      setError(e instanceof Error ? e.message : '快照读取失败，请重试。');
    }
  }, [api, origin]);

  const connect = useCallback(async () => {
    if (!origin || inFlight.current) { setChecking(false); return; }
    const ticket = generation.current;
    inFlight.current = true; setSyncing(true);
    try {
      const s = await api.session();
      if (ticket !== generation.current) return;
      activeSession.current = s; setSession(s); setConnected(true); setError('');
      if (s.authenticated && s.serverId) {
        setOfflineView(false);
        setSnapshot(previous => previous?.serverId === s.serverId ? previous : readSnapshot(origin, s.serverId));
        await loadData(s, ticket);
      } else { setSnapshot(null); setAction(null); }
    } catch (e) {
      if (ticket === generation.current) { setConnected(false); setError(e instanceof Error ? e.message : '服务器连接失败'); }
    } finally { if (ticket === generation.current) { setChecking(false); setSyncing(false); inFlight.current = false; } }
  }, [api, origin, loadData]);

  useEffect(() => {
    generation.current++; inFlight.current = false; activeSession.current = null;
    setSession(null); setSnapshot(null); setStatus(null); setConnected(false); setChecking(true); setError(''); setOfflineView(false); setSaved(readSnapshot(origin)); setSelectedId(null); setAction(null); setRegion('all');
    void connect();
    return () => { generation.current++; inFlight.current = false; };
  }, [connect, origin]);
  useEffect(() => {
    const onHash = () => { setPage(currentPage()); };
    window.addEventListener('hashchange', onHash); return () => window.removeEventListener('hashchange', onHash);
  }, []);
  useEffect(() => {
    const onOffline = () => setConnected(false);
    const onOnline = () => { if (!offlineView) void connect(); };
    window.addEventListener('offline', onOffline); window.addEventListener('online', onOnline);
    return () => { window.removeEventListener('offline', onOffline); window.removeEventListener('online', onOnline); };
  }, [connect, offlineView]);
  useEffect(() => {
    if (!session?.authenticated || offlineView) return;
    const timer = setInterval(() => { if (!document.hidden) void connect(); }, status?.refreshing ? 4000 : snapshot ? 60000 : 10000);
    return () => clearInterval(timer);
  }, [connect, session?.authenticated, offlineView, status?.refreshing, !!snapshot]);
  useEffect(() => { if (!toast) return; const timer = setTimeout(() => setToast(''), 5000); return () => clearTimeout(timer); }, [toast]);

  const navigate = (value: string) => { if (navigation.some(n => n.id === value)) { window.location.hash = value; setPage(value as Page); setSelectedId(null); } };
  const changeServer = (url: string, allowHttp: boolean) => { saveServerPreference({ url, allowHttp }); if (url === origin) void connect(); else setOrigin(url); };
  const logout = async () => {
    try { await api.logout(); }
    catch (e) { throw new Error(`${e instanceof Error ? e.message : '退出失败。'} 当前会话尚未确认撤销，请恢复连接后重试退出。`); }
    generation.current++; inFlight.current = false; activeSession.current = null;
    setSession(null); setSnapshot(null); setOfflineView(false); setAction(null); setSelectedId(null); setError(''); setSaved(readSnapshot(origin));
  };
  const clearCache = () => {
    try { purgeSnapshots(origin); setSaved(null); setPurge(false); if (offlineView) { setSnapshot(null); setOfflineView(false); } setToast('本机快照已清除'); }
    catch (e) { setError(e instanceof Error ? e.message : '清除失败'); setPurge(false); }
  };
  const refresh = async () => {
    if (!connected || !session?.authenticated || syncing || status?.refreshing) return;
    setSyncing(true); setError('');
    try { await api.refresh(); setStatus(s => s ? { ...s, refreshing: true } : { configured: false, cliInstalled: false, refreshing: true, lastError: null, lastRefreshAt: null }); setToast('采集已启动，已有快照会持续显示'); }
    catch (e) { setError(e instanceof Error ? e.message : '刷新未完成'); }
    finally { setSyncing(false); }
  };
  const displaySnapshot = offlineView ? saved : snapshot;
  const settingsSnapshot = displaySnapshot || (saved?.serverId === session?.serverId ? saved : null);
  const selected = displaySnapshot?.resources.find(r => r.id === selectedId) || null;
  const canOperate = connected && !!session?.authenticated && !offlineView && !!displaySnapshot;
  const resourceActions = selected ? selected.actions.filter(a => allowedActions.has(a) && !!session?.capabilities?.actions.includes(a)) : [];
  const scoped = displaySnapshot?.resources.filter(r => region === 'all' || r.region === region) || [];
  const filtered = scoped.filter(r => (kind === 'all' || r.kind === kind) && (!query.trim() || `${r.name} ${r.region} ${r.compartment} ${r.shape || ''}`.toLowerCase().includes(query.trim().toLowerCase())));
  const nav = navigation.find(n => n.id === page)!;
  const busy = syncing || !!status?.refreshing;

  if (!session?.authenticated && !offlineView) return <><LoginPage api={api} loading={checking} error={error} snapshot={saved} onLogin={async password => {
    const loginGeneration = generation.current;
    const loginApi = api;
    const loginOrigin = origin;
    const s = await loginApi.login(password);
    if (loginGeneration !== generation.current || requestContext.current.api !== loginApi || requestContext.current.origin !== loginOrigin) return;
    if (!s.authenticated || !s.serverId) throw new Error('登录未完成，请重试。');
    generation.current++; inFlight.current = false; activeSession.current = s; setSession(s); setConnected(true); setOfflineView(false); setError(''); setSnapshot(readSnapshot(origin, s.serverId)); await loadData(s, generation.current);
  }} onOffline={() => { setOfflineView(true); setConnected(false); navigate('overview'); }} onServerChange={changeServer} onPurge={() => setPurge(true)} />{purge && <PurgeDialog onClose={() => setPurge(false)} onConfirm={clearCache} />}</>;

  return <div className="app-shell"><a className="skip-link" href="#main-content">跳至主要内容</a><aside className="sidebar"><Brand /><nav aria-label="主导航">{navigation.map(item => <button key={item.id} className={`nav-item ${page === item.id ? 'active' : ''}`} aria-current={page === item.id ? 'page' : undefined} onClick={() => navigate(item.id)}><item.icon size={20} strokeWidth={1.7} aria-hidden="true" /><span>{item.label}</span>{page === item.id && <span className="nav-active-dot" />}</button>)}</nav><div className="sidebar-bottom"><div className="workspace-avatar">{displaySnapshot?.tenancy.name.slice(0, 1) || '云'}</div><div><strong>{displaySnapshot?.tenancy.name || '当前服务器'}</strong><span>{displaySnapshot?.mode === 'demo' || session?.mode === 'demo' ? '演示环境' : '云资源工作空间'}</span></div></div></aside>
    <div className="app-content"><header className="topbar"><div className="topbar-crumb"><span>工作空间</span><ChevronSeparator /><strong>{nav.label}</strong></div><div className="topbar-status"><span className={`connection-status ${canOperate ? 'online' : 'offline'}`}>{canOperate ? <Wifi size={14} aria-hidden="true" /> : <WifiOff size={14} aria-hidden="true" />}{offlineView ? '离线查看' : connected ? '服务器已连接' : '连接中断'}</span>{(displaySnapshot?.mode === 'demo' || session?.mode === 'demo') && <Badge tone="warning">演示环境</Badge>}<span className="topbar-version">v{session?.version || '0.1.0'}</span></div></header>
    <main id="main-content" className="main-content"><div className="page-heading"><div><h1>{nav.title}</h1><p>{nav.description}</p></div><div className="page-actions">{offlineView ? <button className="button primary" onClick={() => { setOfflineView(false); setError(''); void connect(); }}><LogIn size={17} aria-hidden="true" />登录并连接</button> : <button className="button secondary" onClick={connected ? refresh : () => void connect()} disabled={busy}><RefreshCw size={16} className={busy ? 'spinning' : ''} aria-hidden="true" />{status?.refreshing ? '正在采集…' : syncing ? '正在连接…' : connected ? '刷新快照' : '重新连接'}</button>}</div></div>
    {(offlineView || !connected) && displaySnapshot && <div className="offline-banner" role="status"><WifiOff size={19} aria-hidden="true" /><div><strong>{offlineView ? '正在查看本机离线快照' : '连接已中断，显示上次保存的快照'}</strong><p>采集于 {dateTime(displaySnapshot.generatedAt)}。这不是实时数据，资源操作已停用。</p></div></div>}
    {displaySnapshot?.mode === 'demo' && <div className="demo-banner"><CircleHelp size={16} aria-hidden="true" />当前为服务器明确启用的演示环境，所有资源和用量均为合成数据。</div>}
    {error && !offlineView && <ErrorNotice>{error}</ErrorNotice>}{cacheWarning && <div className="notice warning" role="status">{cacheWarning}</div>}
    {page === 'settings' ? <SettingsPage api={api} session={session} snapshot={settingsSnapshot} status={status} online={connected && !offlineView} onLogout={logout} onPurge={() => setPurge(true)} onServerChange={changeServer} onReconnect={() => void connect()} /> : page === 'activity' ? <ActivityPage api={api} online={canOperate} reloadKey={auditRevision} /> : !displaySnapshot ? <section className="panel"><Empty title={status?.refreshing ? '正在生成第一份快照' : '等待云资源数据'} action={<button className="button secondary" onClick={() => navigate('settings')}>检查服务器配置</button>}>{status?.refreshing ? '服务器正在采集已授权区域。首次采集可能需要几分钟，完成后将自动显示。' : '服务器尚未返回可用快照。请检查 OCI 配置，或稍后重新连接。'}</Empty></section> : <>
      {(page === 'overview' || page === 'resources') && <RegionAtlas regions={displaySnapshot.regions} selected={region} onSelect={setRegion} />}
      {page === 'overview' && <Overview snapshot={displaySnapshot} resources={scoped} onSelect={resource => { setSelectedId(resource.id); navigate('resources'); setSelectedId(resource.id); }} onNavigate={navigate} />}
      {page === 'resources' && <div className={`resource-workspace ${selected ? 'has-detail' : ''}`}><section className="panel resource-explorer"><div className="resource-toolbar"><label className="search-field"><Search size={17} aria-hidden="true" /><input aria-label="搜索资源" value={query} onChange={e => setQuery(e.target.value)} placeholder="搜索名称、区间或规格" /></label><label className="type-filter"><ListFilter size={17} aria-hidden="true" /><select aria-label="资源类型" value={kind} onChange={e => setKind(e.target.value as ResourceKind | 'all')}><option value="all">全部类型</option>{Object.entries(kindNames).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label></div><div className="resource-results"><span>{filtered.length} 项资源</span>{(region !== 'all' || kind !== 'all' || query) && <button className="text-button" onClick={() => { setRegion('all'); setKind('all'); setQuery(''); }}>重置筛选</button>}</div><ResourceTable resources={filtered} onSelect={r => setSelectedId(r.id)} compact={!!selected} /></section>{selected && <ResourceDetail resource={selected} canOperate={canOperate} allowedActions={resourceActions} onAction={value => setAction(value as ActionName)} onClose={() => setSelectedId(null)} />}</div>}
      {page === 'traffic' && <TrafficPage snapshot={displaySnapshot} />}
    </>}
    {displaySnapshot && <SnapshotFooter snapshot={displaySnapshot} />}
    </main></div>{toast && <div className="toast" role="status">{toast}</div>}{purge && <PurgeDialog onClose={() => setPurge(false)} onConfirm={clearCache} />}{action && selected && <ActionDialog api={api} action={action} resource={selected} online={canOperate} onClose={() => setAction(null)} onSuccess={() => { setAuditRevision(n => n + 1); void connect(); }} />}
    {offlineView && <button className="offline-exit" onClick={() => { setOfflineView(false); setSelectedId(null); }} aria-label="返回登录页"><ArrowLeft size={16} aria-hidden="true" />返回登录</button>}
  </div>;
}

function ChevronSeparator() { return <span className="crumb-separator" aria-hidden="true">/</span>; }
