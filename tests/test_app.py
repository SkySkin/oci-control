from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.app import COOKIE, create_app
from server.config import Settings
from server.security import digest, make_password_hash

PASSWORD = "correct-test-passphrase"
ORIGIN = "https://control.test"


class FakeCloud:
    def __init__(self):
        self.calls = []
        self.fail = False

    def collect(self):
        return {"schemaVersion": 1, "generatedAt": "2026-10-08T12:00:00Z", "resources": [], "mode": "demo"}

    def prepare_action(self, action, region, resource_id, params):
        return {"resourceName": "demo-server", "summary": "操作演示资源", "requiresText": None, "etag": "etag-v1", "context": {"state": "RUNNING"}}

    def execute_action(self, action, region, resource_id, params, etag=None, context=None):
        self.calls.append((action, region, resource_id, params, etag, context))
        if self.fail:
            raise RuntimeError("DO_NOT_REFLECT_sensitive-provider-payload")
        return {"status": "submitted", "message": "已提交"}


@pytest.fixture
def env(tmp_path):
    data = tmp_path / "private"
    data.mkdir()
    (data / "password.hash").write_text(make_password_hash(PASSWORD))
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html>OCI Control</html>")
    settings = Settings(data_dir=data, web_dir=web, public_url=ORIGIN, mode="demo")
    cloud = FakeCloud()
    app = create_app(settings, cloud, background=False)
    with TestClient(app, base_url=ORIGIN) as client:
        yield settings, cloud, app, client


def login(client, native=False):
    response = client.post("/api/login", json={"password": PASSWORD, "client": "android" if native else "web"}, headers={} if native else {"Origin": ORIGIN})
    assert response.status_code == 200, response.text
    value = response.json()
    return {"Authorization": "Bearer " + value["token"]} if native else {"Origin": ORIGIN, "X-CSRF-Token": value["csrfToken"]}


def prepare(client, headers, action="instance.stop"):
    response = client.post("/api/actions/prepare", json={"action": action, "region": "us-example-1", "resourceId": "demo-resource", "params": {}}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_public_boundary_and_cookie_flags(env):
    settings, cloud, app, client = env
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/session").json()["authenticated"] is False
    for endpoint in ("snapshot", "status", "audit"):
        assert client.get("/api/" + endpoint).status_code == 401
    response = client.post("/api/login", json={"password": PASSWORD}, headers={"Origin": ORIGIN})
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=strict" in cookie
    assert "domain=" not in cookie
    assert "token" not in response.json()
    assert client.get("/api/session").headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in client.get("/").headers["content-security-policy"]


def test_csrf_and_foreign_origin_are_rejected(env):
    *_, client = env
    headers = login(client)
    assert client.post("/api/refresh", json={}).status_code == 403
    assert client.post("/api/refresh", json={}, headers={"Origin": ORIGIN}).status_code == 403
    bad = dict(headers, Origin="https://evil.test")
    assert client.post("/api/refresh", json={}, headers=bad).status_code == 403
    assert client.post("/api/login", json={"password": PASSWORD, "client": "android"}, headers={"Origin": "https://evil.test"}).status_code == 403
    assert client.post("/api/login", content="password=x", headers={"Content-Type": "text/plain"}).status_code == 415


def test_session_survives_restart_and_logout_revokes(env):
    settings, cloud, app, client = env
    headers = login(client)
    token = client.cookies.get(COOKIE)
    server_id = client.get("/api/session").json()["serverId"]
    app2 = create_app(settings, cloud, background=False)
    with TestClient(app2, base_url=ORIGIN) as second:
        second.cookies.set(COOKIE, token)
        assert second.get("/api/session").json()["serverId"] == server_id
        assert second.post("/api/logout", json={}, headers=headers).status_code == 200
        second.cookies.set(COOKIE, token)
        assert second.get("/api/audit").status_code == 401


def test_password_rotation_revokes_existing_sessions(env):
    settings, cloud, app, client = env
    login(client)
    settings.password_hash_file.write_text(make_password_hash("a-new-long-passphrase"))
    assert client.get("/api/audit").status_code == 401


def test_native_bearer_is_persistent_and_not_cookie_auth(env):
    settings, cloud, app, client = env
    headers = login(client, native=True)
    assert COOKIE not in client.cookies
    assert client.get("/api/session", headers=headers).json()["authenticated"]
    client.cookies.set(COOKIE, headers["Authorization"][7:])
    assert not client.get("/api/session").json()["authenticated"]
    assert client.post("/api/logout", json={}, headers=headers).status_code == 200
    assert client.get("/api/session", headers=headers).json()["authenticated"] is False


def test_rate_limit_persists_and_validation_never_echoes_secret(env):
    settings, cloud, app, client = env
    response = client.post("/api/login", json={"password": "x" * 1100})
    assert response.status_code == 422 and "xxxx" not in response.text
    for _ in range(10):
        assert client.post("/api/login", json={"password": "wrong"}).status_code == 401
    assert client.post("/api/login", json={"password": PASSWORD}).status_code == 429
    assert client.post("/api/login", content='{"password":"' + "x" * 17000 + '"}', headers={"Content-Type": "application/json"}).status_code == 413


def test_action_requires_preview_text_and_cannot_replay(env):
    settings, cloud, app, client = env
    headers = login(client)
    preview = prepare(client, headers)
    assert preview["requiresText"] == "demo-server"
    payload = {"confirmationId": preview["confirmationId"], "idempotencyKey": "request-one"}
    assert client.post("/api/actions/execute", json=payload, headers=headers).status_code == 400
    assert not cloud.calls
    payload["confirmationText"] = "demo-server"
    response = client.post("/api/actions/execute", json=payload, headers=headers)
    assert response.status_code == 200
    assert cloud.calls[0][-2:] == ("etag-v1", {"state": "RUNNING"})
    assert client.post("/api/actions/execute", json=payload, headers=headers).json() == response.json()
    assert len(cloud.calls) == 1
    payload["idempotencyKey"] = "request-two"
    assert client.post("/api/actions/execute", json=payload, headers=headers).status_code == 409
    assert len(client.get("/api/audit").json()["events"]) == 1


def test_action_is_bound_to_device_and_expires(env):
    settings, cloud, app, client = env
    first = login(client, native=True)
    preview = prepare(client, first)
    second = login(client, native=True)
    payload = {"confirmationId": preview["confirmationId"], "confirmationText": "demo-server", "idempotencyKey": "request-test"}
    assert client.post("/api/actions/execute", json=payload, headers=second).status_code == 404
    with app.state.runtime.store.connect() as db:
        db.execute("UPDATE confirmations SET expires=0")
    assert client.post("/api/actions/execute", json=payload, headers=first).status_code == 409
    assert not cloud.calls


def test_arbitrary_operations_and_params_denied(env):
    *_, client = env
    headers = login(client)
    for action, params in (("instance.terminate", {}), ("instance.start", {"command": "shell"}), ("instance.rename", {"displayName": "bad\nname"})):
        response = client.post("/api/actions/prepare", json={"action": action, "region": "us-example-1", "resourceId": "resource", "params": params}, headers=headers)
        assert response.status_code in (400, 403)


def test_provider_failure_consumes_confirmation_and_hides_raw_error(env):
    settings, cloud, app, client = env
    headers = login(client)
    cloud.fail = True
    preview = prepare(client, headers)
    payload = {"confirmationId": preview["confirmationId"], "confirmationText": "demo-server", "idempotencyKey": "request-fail"}
    response = client.post("/api/actions/execute", json=payload, headers=headers)
    assert response.status_code == 409
    assert "DO_NOT_REFLECT" not in response.text
    assert client.post("/api/actions/execute", json=payload, headers=headers).status_code == 409
    assert len(cloud.calls) == 1


def test_atomic_claim_and_interrupted_execution_never_retries(env):
    settings, cloud, app, client = env
    store = app.state.runtime.store
    ident, _ = store.prepare("session", "instance.start", "region", "id", {}, {})
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: store.claim(ident, "session", "same-key")[0], range(8)))
    assert results.count("claimed") == 1
    app2 = create_app(settings, cloud, background=False)
    assert app2.state.runtime.store.claim(ident, "session", "same-key")[0] == "unknown"


def test_identity_change_discards_old_account_snapshot(env):
    settings, cloud, app, client = env
    login(client)
    app.state.runtime.store.set_meta("snapshot", json.dumps({"serverId": "old-server", "resources": []}))
    original = app.state.runtime.store.server_id
    settings.mode = "live"
    app2 = create_app(settings, cloud, background=False)
    assert app2.state.runtime.store.server_id != original
    assert app2.state.runtime.snapshot is None


def test_http_requires_explicit_configuration_and_no_unsafe_cookie_reuse(tmp_path):
    with pytest.raises(ValueError):
        Settings(data_dir=tmp_path, public_url="http://192.0.2.1:8787", allow_http=False)
    assert not Settings(data_dir=tmp_path, public_url="http://192.0.2.1:8787", allow_http=True).secure_cookie
    for url in ("https://user:pass@example.test", "https://example.test/path", "file:///private"):
        with pytest.raises(ValueError):
            Settings(data_dir=tmp_path, public_url=url)
