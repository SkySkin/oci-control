from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path

from .config import Settings
from .security import make_password_hash


def configure():
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    settings.data_dir.chmod(0o700)
    path = settings.password_hash_file
    if path.exists():
        if input("访问密钥已存在。重设会撤销所有设备登录，继续？[y/N] ").lower() != "y":
            return
    first = getpass.getpass("设置访问密钥（至少 12 字符，不回显）：")
    if first != getpass.getpass("再次输入："):
        raise ValueError("两次输入不一致")
    encoded = make_password_hash(first)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + ".new")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as out:
        out.write(encoded + "\n")
    temporary.chmod(0o600)
    temporary.replace(path)
    print("访问密钥已配置。摘要保存在私有运行目录，密钥不会上传。")
    print("OCI 配置已找到。" if Path(settings.config_file).is_file() else "未找到 OCI 配置。请先运行 oci setup config；API 私钥仅保存在服务器。")


def main():
    os.umask(0o077)
    if sys.argv[1:] == ["configure"]:
        configure()
    elif sys.argv[1:]:
        raise ValueError("用法：python -m server [configure]")
    else:
        import uvicorn
        from .app import create_app
        settings = Settings()
        uvicorn.run(create_app(settings), host=settings.host, port=settings.port, proxy_headers=False, access_log=False)


if __name__ == "__main__":
    try:
        main()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
