from __future__ import annotations

import asyncio
import hmac
import json
import logging
import shutil
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from . import __version__
from .config import Settings
from .security import digest, random_token, read_password_hash, verify_password
from .store import Store

LOG = logging.getLogger("oci_control")
COOKIE = "oci_control_session"
ACTIONS = ["instance.start", "instance.stop", "instance.reboot", "instance.rename", "nlb.backend.enable", "nlb.backend.disable"]


def utcnow():
    return datetime.now(timezone.utc).isoformat()


class ApiError(Exception):
    def __init__(self, code, message, status=400):
        self.code, self.message, self.status = code, message, status


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Input):
    password: str = Field(min_length=1, max_length=1024)
    client: Literal["web", "android"] = "web"


class Prepare(Input):
    action: str = Field(max_length=64)
    region: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9-]+$")
    resourceId: str = Field(min_length=1, max_length=300)
    params: dict = Field(default_factory=dict)


class Execute(Input):
    confirmationId: str = Field(min_length=1, max_length=80)
    confirmationText: str | None = Field(default=None, max_length=300)
    idempotencyKey: str = Field(min_length=8, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")


class Runtime:
    def __init__(self, settings, cloud=None):
        self.settings = settings
        read_password_hash(settings.password_hash_file)
        self.store = Store(settings.data_dir, settings.identity())
        self.cloud = cloud
        self.refreshing = False
        self.last_error = None
        self.last_refresh = None
        self.tasks = set()
        self.snapshot = None
        saved = self.store.get_meta("snapshot")
        if saved:
            with suppress(ValueError, TypeError):
                self.snapshot = json.loads(saved)
                self.last_refresh = self.snapshot.get("generatedAt")

    def get_cloud(self):
        if self.cloud is None:
            if self.settings.mode == "demo":
                from .demo import DemoCloudClient
                self.cloud = DemoCloudClient()
            else:
                from .cloud import CloudClient
                self.cloud = CloudClient(self.settings.config_file, self.settings.profile)
        return self.cloud

    def safe_cloud_error(self, exc):
        # OCI and HTTP exceptions can contain credentials or request URLs. Only our adapter's sanitized error is public.
        from .cloud import CloudError
        if isinstance(exc, CloudError):
            return str(getattr(exc, "code", "CLOUD_ERROR"))[:80], str(exc)[:500]
        return "CLOUD_UNAVAILABLE", "云端请求未完成。请检查 OCI 配置、权限或网络后重试。"

    async def collect(self):
        try:
            snapshot = await asyncio.to_thread(lambda: self.get_cloud().collect())
            snapshot["serverId"] = self.store.server_id
            snapshot["mode"] = self.settings.mode
            self.store.set_meta("snapshot", json.dumps(snapshot, ensure_ascii=False, allow_nan=False))
            self.snapshot = snapshot
            self.last_refresh = snapshot.get("generatedAt", utcnow())
            self.last_error = None
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _, self.last_error = self.safe_cloud_error(exc)
            LOG.warning("Cloud snapshot refresh failed (%s)", type(exc).__name__)
        finally:
            self.refreshing = False

    def start_refresh(self):
        if self.refreshing:
            return
        self.refreshing = True
        task = asyncio.create_task(self.collect())
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def periodic(self):
        while True:
            self.start_refresh()
            await asyncio.sleep(self.settings.refresh_seconds)


def create_app(settings=None, cloud=None, background=True):
    settings = settings or Settings()
    runtime = Runtime(settings, cloud)

    @asynccontextmanager
    async def lifespan(app):
        periodic = asyncio.create_task(runtime.periodic()) if background else None
        yield
        if periodic:
            periodic.cancel()
            with suppress(asyncio.CancelledError):
                await periodic
        for task in list(runtime.tasks):
            task.cancel()
        if runtime.tasks:
            await asyncio.gather(*runtime.tasks, return_exceptions=True)

    app = FastAPI(title="OCI Control", version=__version__, docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.runtime = runtime

    @app.exception_handler(ApiError)
    async def api_error(request, exc):
        return JSONResponse({"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Never echo inputs: validation errors on a password field must not reflect that password.
        return JSONResponse({"error": {"code": "INVALID_INPUT", "message": "请求参数不正确，请检查后重试。"}}, status_code=422)

    def check_origin(request):
        origin = request.headers.get("origin")
        expected = settings.public_url or str(request.base_url).rstrip("/")
        if origin and origin != expected:
            raise ApiError("ORIGIN_DENIED", "请求来源不被允许。", 403)
        if request.headers.get("sec-fetch-site") == "cross-site":
            raise ApiError("ORIGIN_DENIED", "请求来源不被允许。", 403)

    @app.middleware("http")
    async def boundary(request, call_next):
        try:
            if request.method in ("POST", "PUT", "PATCH", "DELETE"):
                check_origin(request)
                if request.headers.get("content-type", "").split(";")[0] != "application/json":
                    raise ApiError("JSON_REQUIRED", "此接口需要 JSON 请求。", 415)
                chunks, size = [], 0
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > 16384:
                        raise ApiError("BODY_TOO_LARGE", "请求内容过大。", 413)
                    chunks.append(chunk)
                request._body = b"".join(chunks)
            response = await call_next(request)
        except ApiError as exc:
            response = await api_error(request, exc)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def auth(request, mutation=False, optional=False):
        bearer = request.headers.get("authorization", "")
        native = bearer.startswith("Bearer ")
        token = bearer[7:] if native else request.cookies.get(COOKIE)
        if not token or len(token) > 256:
            if optional:
                return None
            raise ApiError("AUTH_REQUIRED", "请先输入访问密钥登录。", 401)
        try:
            fingerprint = digest(read_password_hash(settings.password_hash_file))
        except ValueError:
            raise ApiError("AUTH_UNAVAILABLE", "服务端访问密钥配置不可用。", 503) from None
        session = runtime.store.get_session(digest(token), fingerprint, settings.session_seconds)
        if not session or (native and session["client"] != "android") or (not native and session["client"] != "web"):
            if optional:
                return None
            raise ApiError("SESSION_EXPIRED", "登录已失效，请重新输入访问密钥。", 401)
        if mutation:
            check_origin(request)
            if not native and (not request.headers.get("origin") or not hmac.compare_digest(request.headers.get("x-csrf-token", ""), session["csrf"])):
                raise ApiError("CSRF_DENIED", "操作验证失效，请刷新页面后重试。", 403)
        return session

    def cookie(response, value):
        response.set_cookie(COOKIE, value, max_age=settings.session_seconds, httponly=True, secure=settings.secure_cookie, samesite="strict", path="/")

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "version": __version__}

    @app.get("/api/session")
    async def session(request: Request):
        current = auth(request, optional=True)
        body = {"authenticated": bool(current), "version": __version__, "mode": settings.mode}
        if current:
            body.update(csrfToken=current["csrf"], serverId=runtime.store.server_id, capabilities={"actions": ACTIONS})
        response = JSONResponse(body)
        if current and current["client"] == "web":
            cookie(response, request.cookies[COOKIE])
        return response

    @app.post("/api/login")
    async def login(body: Login, request: Request):
        peer = request.client.host if request.client else "unknown"
        if not runtime.store.attempt_login(peer):
            raise ApiError("LOGIN_RATE_LIMITED", "尝试次数过多，请 5 分钟后再试。", 429)
        encoded = read_password_hash(settings.password_hash_file)
        valid = await asyncio.to_thread(verify_password, body.password, encoded)
        if not valid:
            raise ApiError("INVALID_PASSWORD", "访问密钥不正确。", 401)
        token, csrf = random_token(), random_token()
        runtime.store.create_session(digest(token), csrf, digest(encoded), settings.session_seconds, body.client)
        payload = {"authenticated": True, "csrfToken": csrf, "serverId": runtime.store.server_id, "mode": settings.mode}
        if body.client == "android":
            payload["token"] = token
        response = JSONResponse(payload)
        if body.client == "web":
            cookie(response, token)
        return response

    @app.post("/api/logout")
    async def logout(request: Request):
        current = auth(request, mutation=True)
        runtime.store.revoke_session(current["id"])
        response = JSONResponse({"authenticated": False})
        response.delete_cookie(COOKIE, path="/", secure=settings.secure_cookie, httponly=True, samesite="strict")
        return response

    @app.get("/api/status")
    async def status(request: Request):
        auth(request)
        return {"configured": settings.mode == "demo" or Path(settings.config_file).is_file(), "cliInstalled": shutil.which("oci") is not None, "refreshing": runtime.refreshing, "lastError": runtime.last_error, "lastRefreshAt": runtime.last_refresh}

    @app.get("/api/snapshot")
    async def snapshot(request: Request):
        auth(request)
        if runtime.snapshot is None:
            raise ApiError("SNAPSHOT_PENDING", runtime.last_error or "正在首次同步云端数据，请稍后刷新。", 503)
        return runtime.snapshot

    @app.post("/api/refresh", status_code=202)
    async def refresh(request: Request):
        auth(request, mutation=True)
        runtime.start_refresh()
        return {"status": "refreshing"}

    @app.get("/api/audit")
    async def audit(request: Request):
        auth(request)
        return {"events": runtime.store.audit_events()}

    @app.post("/api/actions/prepare")
    async def prepare(body: Prepare, request: Request):
        current = auth(request, mutation=True)
        if body.action not in ACTIONS:
            raise ApiError("ACTION_DENIED", "不支持此操作。", 403)
        allowed = {"displayName"} if body.action == "instance.rename" else {"backendSetName", "backendName"} if body.action.startswith("nlb.") else set()
        if set(body.params) != allowed or any(not isinstance(v, str) or not 1 <= len(v) <= 256 or any(ord(c) < 32 for c in v) for v in body.params.values()):
            raise ApiError("INVALID_PARAMS", "操作参数不正确。")
        try:
            preview = await asyncio.to_thread(lambda: runtime.get_cloud().prepare_action(body.action, body.region, body.resourceId, body.params))
        except Exception as exc:
            code, message = runtime.safe_cloud_error(exc)
            raise ApiError(code, message, 409) from None
        # Reboot, stopping and drainage explicitly require the current resource name.
        if body.action in ("instance.stop", "instance.reboot", "nlb.backend.disable"):
            preview["requiresText"] = preview["resourceName"]
        ident, expires = runtime.store.prepare(current["id"], body.action, body.region, body.resourceId, body.params, preview)
        return {"confirmationId": ident, "action": body.action, "resourceName": preview["resourceName"], "summary": preview["summary"], "expiresAt": datetime.fromtimestamp(expires, timezone.utc).isoformat(), "requiresText": preview.get("requiresText")}

    @app.post("/api/actions/execute")
    async def execute(body: Execute, request: Request):
        current = auth(request, mutation=True)
        confirmation = runtime.store.confirmation(body.confirmationId, current["id"])
        if not confirmation:
            raise ApiError("CONFIRMATION_MISSING", "确认已失效，请重新预览操作。", 404)
        preview = json.loads(confirmation["preview"])
        required = preview.get("requiresText")
        if required and body.confirmationText != required:
            raise ApiError("CONFIRMATION_TEXT", "请输入完整资源名称以确认操作。")
        state, value = runtime.store.claim(body.confirmationId, current["id"], body.idempotencyKey)
        if state == "replayed":
            return value
        if state != "claimed":
            raise ApiError("CONFIRMATION_" + state.upper(), "操作已提交、已过期或结果待核对，请刷新资源状态后再操作。", 409)
        try:
            result = await asyncio.to_thread(lambda: runtime.get_cloud().execute_action(confirmation["action"], confirmation["region"], confirmation["resource_id"], json.loads(confirmation["params"]), etag=preview.get("etag"), context=preview.get("context")))
        except Exception as exc:
            code, message = runtime.safe_cloud_error(exc)
            runtime.store.finish(body.confirmationId, "failed", {"code": code, "message": message})
            raise ApiError(code, message + " 请先核对资源状态，再决定是否重新操作。", 409) from None
        response = {"operationId": body.confirmationId, "status": result.get("status", "submitted"), "message": result.get("message", "操作已提交，正在刷新资源状态。")}
        runtime.store.finish(body.confirmationId, "succeeded", response)
        runtime.start_refresh()
        return response

    @app.get("/{path:path}")
    async def static(path: str):
        if path.startswith("api/"):
            raise ApiError("NOT_FOUND", "接口不存在。", 404)
        target = (settings.web_dir / path).resolve()
        if not target.is_relative_to(settings.web_dir) or any(part.startswith(".") for part in Path(path).parts):
            raise ApiError("NOT_FOUND", "页面不存在。", 404)
        if not target.is_file():
            target = settings.web_dir / "index.html"
        if target.is_file():
            return FileResponse(target, headers={"Cache-Control": "no-cache" if target.name in ("index.html", "sw.js") else "public, max-age=3600"})
        return JSONResponse({"error": {"code": "WEB_NOT_BUILT", "message": "前端尚未构建，请运行 cd web && npm ci && npm run build。"}}, status_code=503)

    return app
