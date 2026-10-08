import { Capacitor, CapacitorHttp, registerPlugin } from '@capacitor/core';
import type { AuditEvent, Confirmation, Execution, PrepareRequest, ServerStatus, Session, Snapshot } from './types';

interface SecureSessionPlugin {
  set(options: { key: string; value: string }): Promise<void>;
  get(options: { key: string }): Promise<{ value: string | null }>;
  remove(options: { key: string }): Promise<void>;
}
const SecureSession = registerPlugin<SecureSessionPlugin>('SecureSession');
export const isNative = Capacitor.isNativePlatform();
export class ApiError extends Error {
  constructor(message: string, public status = 0, public code = 'NETWORK_ERROR') { super(message); }
}

export function normalizeServerUrl(value: string, allowHttp = false): string {
  let url: URL;
  try { url = new URL(value.trim()); } catch { throw new Error('请输入完整的服务器地址，例如 https://cloud.example.com'); }
  if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password || url.search || url.hash || (url.pathname !== '/' && url.pathname !== '')) {
    throw new Error('服务器地址仅支持 HTTP(S) 域名和端口，不可包含账号、路径或参数。');
  }
  if (url.protocol === 'http:' && !allowHttp) throw new Error('HTTP 不会加密密码和会话。仅在可信网络中明确同意后连接。');
  return url.origin;
}

export class ApiClient {
  csrfToken: string | undefined;
  constructor(public origin: string, private native = isNative) {}
  private get credentialKey() { return `oci-control.session.${encodeURIComponent(this.origin)}`; }

  async request<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    if (method !== 'GET' && this.csrfToken && !this.native) headers['X-CSRF-Token'] = this.csrfToken;
    let status: number;
    let data: unknown;
    try {
      if (this.native) {
        const { value } = await SecureSession.get({ key: this.credentialKey });
        if (value) headers.Authorization = `Bearer ${value}`;
        const response = await CapacitorHttp.request({
          url: `${this.origin}${path}`, method, headers, data: body,
          responseType: 'json', connectTimeout: 12000, readTimeout: 25000, disableRedirects: true,
        });
        if ((response.status >= 300 && response.status < 400) || (response.url && new URL(response.url).origin !== this.origin)) {
          throw new ApiError('服务器发生重定向，已停止连接。请核对服务器地址。', 0, 'REDIRECT_BLOCKED');
        }
        status = response.status;
        data = response.data;
        if (typeof data === 'string') { try { data = JSON.parse(data); } catch { throw new ApiError('服务器未返回有效 API 数据，请检查地址。'); } }
      } else {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 25000);
        try {
          const response = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), credentials: 'same-origin', redirect: 'error', signal: controller.signal });
          status = response.status;
          try { data = await response.json(); } catch { throw new ApiError('服务器未返回有效 API 数据，请检查部署。', status); }
        } finally { clearTimeout(timer); }
      }
    } catch (error) {
      if (error instanceof ApiError) throw error;
      throw new ApiError('暂时无法连接服务器。请检查网络后重试。');
    }
    if (status < 200 || status >= 300) {
      const error = (data as { error?: { message?: string; code?: string } })?.error;
      throw new ApiError(error?.message || `请求未完成（${status}），请稍后重试。`, status, error?.code);
    }
    return data as T;
  }

  async session() {
    const session = await this.request<Session>('/api/session');
    this.csrfToken = session.csrfToken;
    return session;
  }
  async login(password: string) {
    const result = await this.request<{ csrfToken: string; token?: string }>('/api/login', 'POST', { password, client: this.native ? 'android' : 'web' });
    this.csrfToken = result.csrfToken;
    if (this.native) {
      if (!result.token) throw new ApiError('服务器未返回 Android 会话，请检查服务版本。');
      try { await SecureSession.set({ key: this.credentialKey, value: result.token }); }
      catch { throw new ApiError('无法安全保存登录会话，请检查 Android 安全存储。'); }
    }
    return this.session();
  }
  async logout() {
    await this.request('/api/logout', 'POST', {});
    this.csrfToken = undefined;
    if (this.native) await SecureSession.remove({ key: this.credentialKey });
  }
  snapshot = () => this.request<Snapshot>('/api/snapshot');
  status = () => this.request<ServerStatus>('/api/status');
  refresh = () => this.request<{ status: string }>('/api/refresh', 'POST', {});
  audit = () => this.request<{ events: AuditEvent[] }>('/api/audit');
  prepare = (request: PrepareRequest) => this.request<Confirmation>('/api/actions/prepare', 'POST', request);
  execute = (confirmationId: string, confirmationText: string, idempotencyKey: string) => this.request<Execution>('/api/actions/execute', 'POST', { confirmationId, confirmationText, idempotencyKey });
}
