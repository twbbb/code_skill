#!/usr/bin/env bash
# 展开某个 Go 入口方法的本模块调用链，输出到 $OUT（默认 $PWD/analysis/<方法名>.json）。
# 用法：
#   ./gocalls.sh /path/to/wxtoken RefreshAll
#   ./gocalls.sh /path/to/wxtoken 'wxtokensvc.(*WxTokenImpl).GetAccessToken'
# 输出目录默认 $PWD/analysis，可用 OUT_DIR 覆盖；OUT 直接指定输出文件。
# 要在沙箱外执行：packages.Load 会访问 GOPROXY/GOSUMDB，GOCACHE 也在沙箱外。
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DIR="${1:?用法: $0 <go 模块目录> <入口方法名>}"
ENTRY="${2:?用法: $0 <go 模块目录> <入口方法名>}"
ABS="$(cd "$DIR" && pwd)"
OUT_DIR="${OUT_DIR:-$PWD/analysis}"
OUT="${OUT:-$OUT_DIR/${ENTRY##*.}.json}"

mkdir -p "$(dirname "$OUT")"
BIN="$HERE/bin/gocalls-$(uname -s | tr 'A-Z' 'a-z')-$(uname -m)"

# 预编译二进制优先，避免受本机 go 版本（go.mod 要求 1.24+）限制；没有就现编。
if [ ! -x "$BIN" ]; then
  mkdir -p "$HERE/bin"
  (cd "$HERE/gocalls" && go build -o "$BIN" .)
fi

"$BIN" -dir "$ABS" -entry "$ENTRY" -format json -maxdepth 100 -maxkids 200 >"$OUT"
echo "$OUT" >&2
