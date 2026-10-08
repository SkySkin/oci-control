#!/usr/bin/env bash
# Run from a reviewed checkout. No fetched shell code and no credential content is printed.
set -euo pipefail
umask 077
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"

if [[ -z "${PYTHON_BIN:-}" ]]; then
  for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 10))'; then
      PYTHON_BIN="$candidate"
      break
    fi
  done
fi
if [[ -z "${PYTHON_BIN:-}" ]] || ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(sys.version_info < (3, 10))'; then
  echo '需要 Python 3.10+（含 venv）；建议 Python 3.12，可设置 PYTHON_BIN=python3.12。' >&2
  exit 1
fi
if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  echo '请从 Node.js 官方渠道安装 Node.js 22 LTS（含 npm）后重试。' >&2
  exit 1
fi
node -e 'if (Number(process.versions.node.split(".")[0]) < 22) { console.error("需要 Node.js 22+"); process.exit(1); }'

"$PYTHON_BIN" -m venv .venv
.venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt
npm --prefix web ci --no-fund
npm --prefix web run build

export OCI_CONTROL_DATA_DIR="${OCI_CONTROL_DATA_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/oci-control}"
.venv/bin/python - <<'PY'
import os
from pathlib import Path
root = Path.cwd().resolve()
data = Path(os.environ['OCI_CONTROL_DATA_DIR']).expanduser().resolve()
if data == root or root in data.parents:
    raise SystemExit('OCI_CONTROL_DATA_DIR 必须位于代码目录之外。')
data.mkdir(parents=True, exist_ok=True, mode=0o700)
data.chmod(0o700)
PY

if [[ -f "${OCI_CONFIG_FILE:-$HOME/.oci/config}" ]]; then
  echo '检测到 OCI 配置文件（未读取内容）。请确认 OCI_PROFILE 和私钥路径正确。'
else
  echo '未发现 OCI 配置。可运行 .venv/bin/oci setup config，按官方文档配置专用 API 密钥。'
  echo '官方指南：https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm'
  echo '仅试用界面时，可设置 OCI_CONTROL_MODE=demo；演示数据不代表真实账户。'
fi
if [[ -x .venv/bin/oci ]]; then
  echo 'OCI CLI 已安装在项目虚拟环境中；不会自动执行云端操作。'
else
  echo 'OCI CLI 未安装，请参照 docs/INSTALL.md 的官方安装步骤。'
fi

echo '即将交互设置面板密码；输入不会显示。已有密码时，不自动修改。'
hash_file="${OCI_CONTROL_PASSWORD_HASH_FILE:-$OCI_CONTROL_DATA_DIR/password.hash}"
if [[ ! -f "$hash_file" ]]; then
  .venv/bin/python -m server configure
fi
echo '安装完成。使用同一 OCI_CONTROL_DATA_DIR，运行 ./scripts/run-native.sh。'
echo '外网访问请先配置 OCI_CONTROL_PUBLIC_URL 和 HTTPS；详见 docs/INSTALL.md。'
