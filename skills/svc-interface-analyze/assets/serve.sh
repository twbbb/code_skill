#!/usr/bin/env bash
#
# 常驻服务。页面都在本 skill 的 assets/。
# analysis/ 只提供 JSON。关掉终端也还在。
# 再跑一次，已经是当前 serve.py 就直接打开；代码变了才重启。
#
#   ./serve.sh /path/to/analysis          # 打开清单
#   ./serve.sh /path/to/foo.json          # 打开这份 JSON 的调用链
#   ./serve.sh -n /path/to/analysis       # 只确保服务在跑，不打开浏览器
#   ./serve.sh                            # 只确保服务在跑，打印地址
#   ./serve.sh stop
#

set -euo pipefail

self=$(basename "$0")
here=$(cd "$(dirname "$0")" && pwd)
analyze_root=$(cd "$here/.." && pwd)
analyze_assets=$here
list_assets=$here
py=$here/serve.py
port=${SI_PORT:-8766}
state=${XDG_STATE_HOME:-$HOME/.local/state}/svc-interfaces
pidfile=$state/serve.pid
log=$state/serve.log
open_browser=1
target=""

die() { printf '%s: %s\n' "$self" "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    -n|--no-open) open_browser=0; shift ;;
    -h|--help)    sed -e '1d' -e '/^$/,$d' -e 's/^# \{0,1\}//' "$0"; exit 0 ;;
    stop)         target=stop; shift ;;
    -*)           die "未知参数 $1（-h 看用法）" ;;
    *)
      [ -z "$target" ] || die "只能给一个路径"
      target=$1
      shift
      ;;
  esac
done

command -v python3 >/dev/null 2>&1 || die "需要 python3"
[ -f "$py" ] || die "找不到 $py"
mkdir -p "$state"

export SI_LIST_HTML="$list_assets/index.html"
export SI_LIST_JS="$list_assets/list.js"
export SI_VIEW_HTML="$analyze_assets/interface-page.template.html"
export SI_MINDMAP_JS="$analyze_assets/mindmap.js"
export SI_MINDMAP_CSS="$analyze_assets/mindmap.css"
export SI_EXAMPLE_HTML="$analyze_root/example.html"
export SI_EXAMPLE_JSON="$analyze_root/example.json"

rev=$(python3 -c 'import os,sys; print(int(os.stat(sys.argv[1]).st_mtime))' "$py")
want="ok service-interfaces $rev"

health_body() {
  python3 -c '
import sys, urllib.request
try:
    print(urllib.request.urlopen(sys.argv[1], timeout=0.4).read().decode("ascii", "replace").strip())
except Exception:
    raise SystemExit(1)
' "http://127.0.0.1:${port}/health" 2>/dev/null || true
}

port_open() {
  python3 -c '
import socket, sys
s = socket.socket()
s.settimeout(0.2)
try:
    raise SystemExit(0 if s.connect_ex(("127.0.0.1", int(sys.argv[1]))) == 0 else 1)
finally:
    s.close()
' "$port"
}

pid_from_file() {
  [ -f "$pidfile" ] || return 0
  local pid
  pid=$(cat "$pidfile" 2>/dev/null || true)
  case "$pid" in
    ''|*[!0-9]*) return 0 ;;
  esac
  printf '%s\n' "$pid"
}

cmd_of() {
  ps -p "$1" -o command= 2>/dev/null || true
}

stop_ours() {
  local pid cmd
  pid=$(pid_from_file || true)
  if [ -n "$pid" ]; then
    cmd=$(cmd_of "$pid")
    case "$cmd" in
      *serve.py*)
        kill "$pid" 2>/dev/null || true
        ;;
    esac
  fi
  if port_open; then
    pid=$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | head -n 1 || true)
    if [ -n "$pid" ]; then
      cmd=$(cmd_of "$pid")
      case "$cmd" in
        *serve.py*)
          kill "$pid" 2>/dev/null || true
          ;;
        *)
          die "端口 $port 被别的进程占用（pid $pid）"
          ;;
      esac
    fi
  fi
  local i=0
  while [ "$i" -lt 40 ]; do
    if ! port_open; then
      rm -f "$pidfile"
      return 0
    fi
    i=$((i + 1))
    sleep 0.05
  done
  pid=$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | head -n 1 || true)
  if [ -n "$pid" ]; then
    cmd=$(cmd_of "$pid")
    case "$cmd" in
      *serve.py*) kill -9 "$pid" 2>/dev/null || true ;;
      *) die "端口 $port 仍被占用（pid $pid）" ;;
    esac
  fi
  sleep 0.1
  rm -f "$pidfile"
}

start_server() {
  if port_open; then
    local body
    body=$(health_body)
    case "$body" in
      ok\ service-interfaces\ *) ;;
      *) die "端口 $port 已被占用，但不是这个服务" ;;
    esac
    stop_ours
  fi
  python3 "$py" --daemon --port "$port" --pidfile "$pidfile" --logfile "$log"
  local i=0
  while [ "$i" -lt 50 ]; do
    if [ "$(health_body)" = "$want" ]; then
      return 0
    fi
    i=$((i + 1))
    sleep 0.05
  done
  printf '%s: 服务没起来，日志末尾：\n' "$self" >&2
  tail -n 20 "$log" >&2 || true
  exit 1
}

open_url() {
  [ "$open_browser" -eq 1 ] || return 0
  if command -v open >/dev/null 2>&1; then
    open "$1"
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$1"
  fi
}

if [ "$target" = "stop" ]; then
  if ! port_open && [ ! -f "$pidfile" ]; then
    printf '%s: 没在跑\n' "$self"
    exit 0
  fi
  stop_ours
  printf '%s: 已停\n' "$self"
  exit 0
fi

url="http://127.0.0.1:${port}/"
if [ -n "$target" ]; then
  [ -e "$target" ] || die "找不到 $target"
  abs=$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$target")
  enc=$(python3 -c 'import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))' "$abs")
  if [ -d "$target" ]; then
    url="http://127.0.0.1:${port}/list?dir=${enc}"
  elif [ "${target%.json}" != "$target" ]; then
    url="http://127.0.0.1:${port}/view?json=${enc}"
  else
    die "需要 analysis 目录，或一份 .json"
  fi
fi

body=$(health_body)
if [ "$body" = "$want" ]; then
  printf '%s: 已在运行\n' "$self" >&2
else
  case "$body" in
    ok\ service-interfaces\ *)
      printf '%s: 代码更新，重启\n' "$self" >&2
      ;;
    *)
      printf '%s: 启动\n' "$self" >&2
      ;;
  esac
  start_server
fi

printf '%s\n' "$url"
if [ -n "$target" ]; then
  open_url "$url"
fi
