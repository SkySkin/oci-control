#!/bin/sh
set -eu
umask 077
# Named volumes inherit ownership from the image; bind mounts must be writable by uid 10001.
if [ ! -w "${OCI_CONTROL_DATA_DIR:-/data}" ]; then
  echo '数据目录不可写。请将挂载目录授权给容器 UID 10001，或使用命名卷。' >&2
  exit 1
fi
exec "$@"
