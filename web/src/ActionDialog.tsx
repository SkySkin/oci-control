import { useEffect, useMemo, useState } from 'react';
import { CheckCircle2, ShieldCheck } from 'lucide-react';
import { ApiClient } from './api';
import { ErrorNotice, Modal } from './components';
import { actionNames, dateTime } from './format';
import type { ActionName, Confirmation, Execution, Resource } from './types';

type Backend = { set: string; name: string; disabled: boolean };
export function extractBackends(details?: Record<string, unknown>): Backend[] {
  const sets = details?.backendSets;
  if (!sets || typeof sets !== 'object') return [];
  const entries: [string, unknown][] = Array.isArray(sets) ? sets.map((s, i) => [String(s?.name ?? i), s]) : Object.entries(sets);
  return entries.flatMap(([set, raw]) => {
    const data = raw as { backends?: unknown[] } | null;
    return Array.isArray(data?.backends) ? data.backends.flatMap(rawBackend => {
      if (!rawBackend || typeof rawBackend !== 'object') return [];
      const b = rawBackend as { name?: string; isOffline?: boolean; isDrain?: boolean; 'is-offline'?: boolean; 'is-drain'?: boolean };
      return b.name ? [{ set, name: b.name, disabled: !!(b.isOffline || b.isDrain || b['is-offline'] || b['is-drain']) }] : [];
    }) : [];
  });
}

export default function ActionDialog({ api, resource, action, online, onClose, onSuccess }: { api: ApiClient; resource: Resource; action: ActionName; online: boolean; onClose: () => void; onSuccess: () => void }) {
  const [name, setName] = useState(resource.name);
  const backends = useMemo(() => extractBackends(resource.details), [resource.details]);
  const [backendIndex, setBackendIndex] = useState('');
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [confirmationText, setConfirmationText] = useState('');
  const [key, setKey] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<Execution | null>(null);
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, []);
  const expired = confirmation ? !Number.isFinite(Date.parse(confirmation.expiresAt)) || now >= Date.parse(confirmation.expiresAt) : false;
  const isBackend = action.startsWith('nlb.');
  const selectedBackend = backendIndex === '' ? undefined : backends[Number(backendIndex)];
  const validParams = action === 'instance.rename' ? !!name.trim() && name.trim() !== resource.name : !isBackend || !!selectedBackend;

  async function prepare() {
    if (!online || busy || !validParams) return;
    setBusy(true); setError('');
    try {
      const params: Record<string, string> = action === 'instance.rename' ? { displayName: name.trim() } : isBackend && selectedBackend ? { backendSetName: selectedBackend.set, backendName: selectedBackend.name } : {};
      const preview = await api.prepare({ action, region: resource.region, resourceId: resource.id, params });
      if (preview.action !== action || !preview.confirmationId || !Number.isFinite(Date.parse(preview.expiresAt))) throw new Error('操作预览无效，请重新准备。');
      setConfirmation(preview); setConfirmationText(''); setKey(crypto.randomUUID()); setNow(Date.now());
    } catch (e) { setError(e instanceof Error ? e.message : '准备操作失败，请重试。'); }
    finally { setBusy(false); }
  }
  async function execute() {
    if (!confirmation || expired || busy || !online || (confirmation.requiresText && confirmationText !== confirmation.requiresText)) return;
    setBusy(true); setError('');
    try { setResult(await api.execute(confirmation.confirmationId, confirmationText, key)); onSuccess(); }
    catch (e) { setError(`${e instanceof Error ? e.message : '操作未完成。'} 若结果不明，可查看活动记录；重试将使用同一请求标识，不会自动重复提交。`); }
    finally { setBusy(false); }
  }
  return <Modal title={result ? '操作已提交' : actionNames[action]} onClose={() => { if (!busy) onClose(); }}>
    {result ? <div className="operation-success"><CheckCircle2 size={38} aria-hidden="true" /><h3>{result.status === 'succeeded' ? '操作执行成功' : '请求已受理'}</h3><p>{result.message}</p><p className="muted">资源状态将在下次采集后更新，可在活动记录中查看结果。</p><button className="button primary" onClick={onClose}>完成</button></div> : <>
      <div className="operation-steps" aria-label={confirmation ? '第 2 步，共 2 步' : '第 1 步，共 2 步'}><span className={!confirmation ? 'current' : ''}>1　准备操作</span><span className={confirmation ? 'current' : ''}>2　核对并确认</span></div>
      <div className="operation-target"><strong>{resource.name}</strong><span>{resource.region}</span></div>
      {!confirmation ? <form onSubmit={event => { event.preventDefault(); void prepare(); }}><p className="form-intro">服务器将检查资源当前状态和你的权限，返回本次操作的准确影响。</p>{action === 'instance.rename' && <label className="field">新资源名称<input value={name} onChange={event => setName(event.target.value)} maxLength={255} required autoFocus autoComplete="off" /></label>}
        {isBackend && <label className="field">后端节点<select required value={backendIndex} onChange={e => setBackendIndex(e.target.value)}><option value="">选择要操作的后端</option>{backends.map((backend, index) => <option key={`${backend.set}-${backend.name}`} value={index}>{backend.set} / {backend.name}（{backend.disabled ? '已停用或排空' : '启用中'}）</option>)}</select>{!backends.length && <span className="field-help">快照尚未包含后端节点，请刷新资源后重试。</span>}</label>}
        {error && <ErrorNotice>{error}</ErrorNotice>}<div className="modal-actions"><button type="button" className="button secondary" onClick={onClose} disabled={busy}>取消</button><button className="button primary" disabled={busy || !online || !validParams}><ShieldCheck size={17} aria-hidden="true" />{busy ? '正在检查…' : '生成操作预览'}</button></div></form> : <form onSubmit={event => { event.preventDefault(); void execute(); }}>
        <div className="confirmation-summary"><ShieldCheck size={22} aria-hidden="true" /><div><h3>请核对本次操作</h3><p>{confirmation.summary}</p></div></div><p className="field-help">预览有效期至 {dateTime(confirmation.expiresAt)}。执行前服务器会再次核对资源状态。</p>
        {confirmation.requiresText && <label className="field">输入「{confirmation.requiresText}」以确认<input value={confirmationText} onChange={event => setConfirmationText(event.target.value)} autoComplete="off" spellCheck={false} autoFocus placeholder="完整输入资源名称" /></label>}
        {expired && <div className="notice warning" role="status">预览已过期，请重新检查资源状态。</div>}{!online && <div className="notice warning" role="status">当前连接不可用，恢复连接后请重新核对操作。</div>}{error && <ErrorNotice>{error}</ErrorNotice>}
        <div className="modal-actions"><button type="button" className="button secondary" disabled={busy} onClick={() => { setConfirmation(null); setError(''); }}>重新准备</button><button className={`button ${confirmation.requiresText ? 'danger-button' : 'primary'}`} disabled={busy || !online || expired || (!!confirmation.requiresText && confirmationText !== confirmation.requiresText)}>{busy ? '正在执行…' : '确认执行'}</button></div>
      </form>}
    </>}
  </Modal>;
}
