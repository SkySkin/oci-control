"""Public-source safeguards use synthetic inputs only."""
import importlib.util
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "secret-audit.py"
spec = importlib.util.spec_from_file_location("secret_audit", MODULE)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_audit_reports_location_without_secret_value():
    # Construct fake patterns at runtime so the fixture itself stays publishable.
    marker = b"-----BEGIN " + b"PRIVATE KEY-----"
    results = audit.findings(Path("example.txt"), b"heading\n" + marker + b"\nsynthetic\n")
    assert results == ["example.txt:2: possible secret"]
    assert marker.decode() not in "".join(results)


def test_audit_blocks_sensitive_artifacts_even_with_binary_content():
    for name in ("private.pem", "release.jks", "password.hash", "runtime.sqlite", ".env"):
        results = audit.findings(Path(name), b"\x00synthetic")
        assert results and "must not be published" in results[0]


def test_audit_allows_documentation_placeholder_and_gradle_wrapper():
    assert not audit.findings(Path("INSTALL.md"), b"key_file=/oci/api_key.pem\nANDROID_KEYSTORE_PASSWORD")
    assert not audit.findings(Path("gradle-wrapper.jar"), b"PK\x00synthetic archive")


def test_audit_detects_tokens_and_password_hash_without_echo():
    synthetic = b"ghp_" + b"a" * 36
    fake_hash = b"pbkdf2-sha256$" + b"600000$" + b"a" * 32 + b"$" + b"b" * 64
    results = audit.findings(Path("source.py"), synthetic + b"\n" + fake_hash)
    assert len(results) == 2
    assert all("possible secret" in result for result in results)
    assert synthetic.decode() not in "".join(results)
