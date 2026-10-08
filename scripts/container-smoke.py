"""CI-only demo container smoke check. Never points at an external OCI service."""
import json
import os
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:8787"
if os.environ.get("OCI_CONTROL_MODE") != "demo":
    raise SystemExit("Smoke check requires an isolated OCI_CONTROL_MODE=demo container")


def request(path, payload=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = None if payload is None else json.dumps(payload).encode()
    with urlopen(Request(BASE + path, data=data, headers=headers), timeout=3) as response:
        return json.load(response)


for attempt in range(30):
    try:
        assert request("/api/health")["status"] == "ok"
        break
    except (OSError, URLError):
        if attempt == 29:
            raise SystemExit("Demo container did not become healthy") from None
        time.sleep(1)

with urlopen(BASE, timeout=3) as response:
    assert b"<html" in response.read().lower(), "Bundled web entrypoint is missing"
initial = request("/api/session")
assert initial["authenticated"] is False and initial["mode"] == "demo"
login = request("/api/login", {"password": "synthetic-ci-panel-password", "client": "android"})
assert login["authenticated"] is True and login.get("token")
assert request("/api/session", token=login["token"])["mode"] == "demo"
request("/api/logout", {}, login["token"])
assert request("/api/session", token=login["token"])["authenticated"] is False
print("Demo container: health, bundled web, native login and session revocation passed")
