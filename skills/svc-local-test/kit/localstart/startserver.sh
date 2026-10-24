#!/usr/bin/env bash
# 本地起停被测服务的进程，进程和端口见 ../env.yaml。标准脚本，由 svc-local-test 维护，不在工作区里改。
#   ./startserver.sh build | start [进程 ...] | stop [进程 ...] [--siblings] | restart [进程 ...] | status
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
exec python3 "$here/../scripts/localstart.py" "$@"
