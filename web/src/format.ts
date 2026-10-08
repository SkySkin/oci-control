import type { ResourceKind } from './types';
export const kindNames: Record<ResourceKind, string> = { instance: '计算实例', nlb: '网络负载均衡', lb: '负载均衡', bootVolume: '启动卷', blockVolume: '块存储', bucket: '对象存储', vcn: '虚拟云网络' };
export const actionNames: Record<string, string> = { 'instance.start': '启动实例', 'instance.stop': '停止实例', 'instance.reboot': '重启实例', 'instance.rename': '重命名', 'nlb.backend.enable': '启用后端', 'nlb.backend.disable': '停用后端' };
export function number(value: number | null | undefined, digits = 0) { return value == null || !Number.isFinite(value) ? '暂无数据' : new Intl.NumberFormat('zh-CN', { maximumFractionDigits: digits }).format(value); }
export function bytes(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value) || value < 0) return '暂无数据';
  if (value === 0) return '0 B';
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB'];
  const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
  return `${number(value / 1024 ** index, index ? 2 : 0)} ${units[index]}`;
}
export function money(value: number | null | undefined, currency = 'USD') {
  if (value == null || !Number.isFinite(value)) return '暂无数据';
  try { return new Intl.NumberFormat('zh-CN', { style: 'currency', currency, maximumFractionDigits: 2 }).format(value); }
  catch { return `${number(value, 2)} ${currency}`; }
}
export function dateTime(value: string | null | undefined) {
  if (!value || !Number.isFinite(Date.parse(value))) return '尚未采集';
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(new Date(value));
}
export function fullDate(value: string | null | undefined) { return value && Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '尚未采集'; }
export function stateLabel(state: string) { return ({ RUNNING: '运行中', STOPPED: '已停止', STOPPING: '停止中', STARTING: '启动中', AVAILABLE: '可用', ACTIVE: '正常', PROVISIONING: '创建中', TERMINATED: '已终止', TERMINATING: '终止中', FAILED: '异常', UPDATING: '更新中', UNKNOWN: '未知' } as Record<string, string>)[state?.toUpperCase()] || state || '未知'; }
export function stateTone(state: string) { return ['RUNNING', 'AVAILABLE', 'ACTIVE', 'SUCCEEDED'].includes(state?.toUpperCase()) ? 'good' : ['FAILED', 'TERMINATED'].includes(state?.toUpperCase()) ? 'danger' : 'neutral'; }
