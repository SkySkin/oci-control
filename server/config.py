from __future__ import annotations

import configparser
import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("OCI_CONTROL_DATA_DIR", "data")).expanduser())
    password_hash_file: Path | None = None
    config_file: str = field(default_factory=lambda: os.getenv("OCI_CONFIG_FILE", str(Path.home() / ".oci/config")))
    profile: str = field(default_factory=lambda: os.getenv("OCI_PROFILE", "DEFAULT"))
    public_url: str = field(default_factory=lambda: os.getenv("OCI_CONTROL_PUBLIC_URL", "").rstrip("/"))
    allow_http: bool = field(default_factory=lambda: os.getenv("OCI_CONTROL_ALLOW_HTTP", "false").lower() == "true")
    mode: str = field(default_factory=lambda: os.getenv("OCI_CONTROL_MODE", "live"))
    host: str = field(default_factory=lambda: os.getenv("OCI_CONTROL_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(os.getenv("OCI_CONTROL_PORT", "8787")))
    web_dir: Path = field(default_factory=lambda: Path(os.getenv("OCI_CONTROL_WEB_DIR", "web/dist")))
    refresh_seconds: int = field(default_factory=lambda: max(60, int(os.getenv("OCI_CONTROL_REFRESH_SECONDS", "300"))))
    session_seconds: int = 90 * 24 * 3600

    def __post_init__(self):
        self.data_dir = Path(self.data_dir).expanduser().resolve()
        self.web_dir = Path(self.web_dir).resolve()
        self.config_file = str(Path(self.config_file).expanduser())
        self.password_hash_file = Path(self.password_hash_file or os.getenv("OCI_CONTROL_PASSWORD_HASH_FILE", str(self.data_dir / "password.hash"))).expanduser()
        if self.mode not in ("live", "demo"):
            raise ValueError("OCI_CONTROL_MODE must be live or demo")
        if self.public_url:
            u = urlsplit(self.public_url)
            if u.scheme not in ("http", "https") or not u.hostname or u.username or u.password or u.query or u.fragment or u.path not in ("", "/"):
                raise ValueError("PUBLIC_URL must be an http(s) origin without credentials or path")
            if u.scheme == "http" and not self.allow_http:
                raise ValueError("HTTP requires OCI_CONTROL_ALLOW_HTTP=true")

    @property
    def secure_cookie(self) -> bool:
        return not self.allow_http or self.public_url.startswith("https://")

    def identity(self) -> str:
        config = configparser.ConfigParser(interpolation=None)
        try:
            config.read(self.config_file)
            section = config[self.profile]
            values = [section.get("tenancy", ""), section.get("user", "")]
        except (OSError, KeyError, configparser.Error):
            values = [self.config_file, self.profile]
        return hashlib.sha256((self.mode + "|" + "|".join(values)).encode()).hexdigest()
