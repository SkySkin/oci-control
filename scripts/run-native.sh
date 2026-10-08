#!/usr/bin/env bash
set -euo pipefail
umask 077
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
if [[ ! -x .venv/bin/python ]]; then
  echo '请先运行 ./scripts/install-native.sh。' >&2
  exit 1
fi
export OCI_CONTROL_DATA_DIR="${OCI_CONTROL_DATA_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/oci-control}"
export OCI_CONTROL_WEB_DIR="${OCI_CONTROL_WEB_DIR:-$project_dir/web/dist}"
exec .venv/bin/python -m server "$@"
