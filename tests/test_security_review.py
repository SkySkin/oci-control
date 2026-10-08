"""Independent security probes; all runtime state and OCI config are synthetic.

Known findings use strict xfail so integration fixes require removing the marker.
No CloudClient is constructed and no external requests are made.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.app import COOKIE, create_app
from server.config import Settings
from server.security import make_password_hash


ORIGIN = "https://review.example.test"
PASSWORD = "synthetic-review-passphrase"


class FakeCloud:
    def __init__(self):
        self.writes = 0

    def collect(self):
        return {"schemaVersion": 1, "generatedAt": "2026-10-08T00:00:00Z", "resources": []}

    def prepare_action(self, action, region, resource_id, params):
        return {"resourceName": "synthetic-instance", "summary": "Synthetic action",
                "requiresText": None, "etag": "synthetic-etag-1", "context": {"state": "RUNNING"}}

    def execute_action(self, action, region, resource_id, params, etag=None, context=None):
        self.writes += 1
        return {"status": "submitted", "message": "Synthetic action accepted"}


@dataclass
class ReviewEnv:
    settings: Settings
    cloud: FakeCloud
    app: object
    client: TestClient


@pytest.fixture
def review(tmp_path):
    data = tmp_path / "runtime"
    data.mkdir()
    password_file = data / "password.hash"
    password_file.write_text(make_password_hash(PASSWORD))
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html>Synthetic review</html>")
    config = tmp_path / "synthetic-oci.ini"
    config.write_text("[DEFAULT]\ntenancy=synthetic-account-a\nuser=synthetic-user-a\n")
    settings = Settings(data_dir=data, password_hash_file=password_file,
                        web_dir=web, config_file=str(config), profile="DEFAULT",
                        public_url=ORIGIN, allow_http=False, mode="demo")
    cloud = FakeCloud()
    app = create_app(settings, cloud, background=False)
    with TestClient(app, base_url=ORIGIN) as client:
        yield ReviewEnv(settings, cloud, app, client)


def login(review, native=False):
    response = review.client.post("/api/login", headers={"Origin": ORIGIN},
                                  json={"password": PASSWORD, "client": "android" if native else "web"})
    assert response.status_code == 200
    body = response.json()
    return ({"Authorization": "Bearer " + body["token"]} if native else
            {"Origin": ORIGIN, "X-CSRF-Token": body["csrfToken"]})


def prepare(review, headers):
    response = review.client.post("/api/actions/prepare", headers=headers,
                                  json={"action": "instance.stop", "region": "region-a",
                                        "resourceId": "synthetic-instance", "params": {}})
    assert response.status_code == 200
    return response.json()["confirmationId"]


@pytest.mark.parametrize("origin", [None, "null", "https://review.example.test.evil.test", "http://review.example.test"])
def test_cookie_mutations_require_exact_origin_even_with_valid_csrf(review, origin):
    headers = login(review)
    if origin is None:
        del headers["Origin"]
    else:
        headers["Origin"] = origin
    assert review.client.post("/api/logout", headers=headers, json={}).status_code == 403
    assert review.client.get("/api/session").json()["authenticated"] is True


def test_cross_site_metadata_denies_even_correct_origin_and_native_bearer(review):
    headers = login(review, native=True)
    headers.update({"Origin": ORIGIN, "Sec-Fetch-Site": "cross-site"})
    assert review.client.post("/api/refresh", headers=headers, json={}).status_code == 403


def test_cookie_session_cannot_be_used_as_native_bearer_to_bypass_csrf(review):
    login(review)
    headers = {"Authorization": "Bearer " + review.client.cookies.get(COOKIE)}
    assert review.client.post("/api/refresh", headers=headers, json={}).status_code == 401


def test_parallel_execute_calls_and_duplicate_keys_cannot_repeat_write(review):
    headers = login(review, native=True)
    ident = prepare(review, headers)
    payload = {"confirmationId": ident, "confirmationText": "synthetic-instance", "idempotencyKey": "review-same-key"}
    with ThreadPoolExecutor(max_workers=6) as pool:
        responses = list(pool.map(lambda _: review.client.post("/api/actions/execute", headers=headers, json=payload), range(6)))
    assert all(response.status_code in (200, 409) for response in responses)
    assert any(response.status_code == 200 for response in responses)
    assert review.cloud.writes == 1
    other = prepare(review, headers)
    payload["confirmationId"] = other
    assert review.client.post("/api/actions/execute", headers=headers, json=payload).status_code == 409
    assert review.cloud.writes == 1
    assert len(review.app.state.runtime.store.audit_events()) == 1


def test_logout_revokes_native_token_and_prepared_action_across_restart(review):
    headers = login(review, native=True)
    ident = prepare(review, headers)
    assert review.client.post("/api/logout", headers=headers, json={}).status_code == 200
    restarted = create_app(review.settings, review.cloud, background=False)
    with TestClient(restarted, base_url=ORIGIN) as client:
        assert client.get("/api/session", headers=headers).json()["authenticated"] is False
        assert client.post("/api/actions/execute", headers=headers,
                           json={"confirmationId": ident, "confirmationText": "synthetic-instance",
                                 "idempotencyKey": "review-after-logout"}).status_code == 401
    assert review.cloud.writes == 0


def test_synthetic_account_change_discards_sessions_and_old_snapshot(review):
    headers = login(review, native=True)
    runtime = review.app.state.runtime
    old_id = runtime.store.server_id
    runtime.store.set_meta("snapshot", '{"serverId":"synthetic-old-account","resources":[]}')
    Path(review.settings.config_file).write_text("[DEFAULT]\ntenancy=synthetic-account-b\nuser=synthetic-user-b\n")
    restarted = create_app(review.settings, review.cloud, background=False)
    assert restarted.state.runtime.store.server_id != old_id
    assert restarted.state.runtime.snapshot is None
    with TestClient(restarted, base_url=ORIGIN) as client:
        assert client.get("/api/session", headers=headers).json()["authenticated"] is False


def test_static_encoded_traversal_and_symlink_do_not_expose_outside_file(review, tmp_path):
    outside = tmp_path / "synthetic-private.txt"
    outside.write_text("SYNTHETIC-PRIVATE-FILE")
    (review.settings.web_dir / "public-link.txt").symlink_to(outside)
    for path in ("/public-link.txt", "/%2e%2e/synthetic-private.txt", "/%2e%2e%2fsynthetic-private.txt"):
        response = review.client.get(path)
        assert response.status_code == 404
        assert "SYNTHETIC-PRIVATE-FILE" not in response.text


@pytest.mark.parametrize("path", ["/api/exec", "/api/shell", "/api/command", "/api/actions/terminate"])
def test_no_arbitrary_command_routes(review, path):
    headers = login(review, native=True)
    assert review.client.post(path, headers=headers, json={"command": "synthetic-no-command"}).status_code in (404, 405)
    assert review.cloud.writes == 0


def test_interrupted_provider_write_remains_visible_in_audit(review):
    headers = login(review, native=True)
    ident = prepare(review, headers)
    store = review.app.state.runtime.store
    with store.connect() as db:
        session_id = db.execute("SELECT session_id FROM confirmations WHERE id=?", (ident,)).fetchone()[0]
    assert store.claim(ident, session_id, "review-interrupted-key")[0] == "claimed"
    # Model process loss after provider acceptance, before finish()/audit().
    review.cloud.execute_action("instance.stop", "region-a", "synthetic-instance", {},
                                etag="synthetic-etag-1", context={"state": "RUNNING"})
    restarted = create_app(review.settings, review.cloud, background=False)
    assert restarted.state.runtime.store.claim(ident, session_id, "review-interrupted-key")[0] == "unknown"
    assert review.cloud.writes == 1
    assert restarted.state.runtime.store.audit_events(), "Accepted/unknown operation must be visible in audit"
