#!/usr/bin/env bash
# 把本仓库的技能同步到 Claude 插件和 Cursor 用户技能目录。
# 用法：./script/sync.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CURSOR_SKILLS="${CURSOR_SKILLS:-$HOME/.cursor/skills}"
PLUGIN_NAME="code-skill"
MARKETPLACE_NAME="code-skill"

die() { echo "error: $*" >&2; exit 1; }

find_cli() {
  if command -v tclaude >/dev/null 2>&1; then
    echo tclaude
  elif command -v claude >/dev/null 2>&1; then
    echo claude
  else
    die "找不到 tclaude / claude"
  fi
}

# 仓库里带 SKILL.md 的技能目录名，一行一个。
skill_names() {
  local src
  shopt -s nullglob
  for src in "$ROOT/skills"/*; do
    [[ -d "$src" && -f "$src/SKILL.md" ]] || continue
    basename "$src"
  done
}

# 新技能登记进 plugin.json，删掉的从清单拿掉。原有顺序不变。
sync_plugin_json() {
  echo "== plugin.json"
  if ! command -v python3 >/dev/null 2>&1; then
    echo "  skip（需要 python3）"
    return
  fi
  python3 - "$ROOT" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
found = [f"./skills/{p.name}" for p in sorted((root / "skills").iterdir()) if p.is_dir() and (p / "SKILL.md").is_file()]
found_set = set(found)
for rel in (".claude-plugin/plugin.json", ".cursor-plugin/plugin.json"):
    path = root / rel
    if not path.exists():
        print(f"  skip {rel}（文件不存在）")
        continue
    data = json.loads(path.read_text())
    old = list(data.get("skills") or [])
    kept = [s for s in old if s in found_set]
    added = [s for s in found if s not in kept]
    new = kept + added
    if new == old:
        print(f"  ok  {rel}")
        continue
    data["skills"] = new
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    for s in added:
        print(f"  add {rel}: {s}")
    for s in old:
        if s not in found_set:
            print(f"  del {rel}: {s}")
PY
}

sync_claude() {
  local cli="$1"
  echo "== Claude 插件"
  local markets
  markets="$("$cli" plugin marketplace list --json)"
  if printf '%s' "$markets" | grep -q "\"name\": \"${MARKETPLACE_NAME}\""; then
    echo "  marketplace update ${MARKETPLACE_NAME}"
    "$cli" plugin marketplace update "$MARKETPLACE_NAME"
  else
    echo "  marketplace add ${ROOT}"
    "$cli" plugin marketplace add "$ROOT"
  fi

  local plugins
  plugins="$("$cli" plugin list --json)"
  if printf '%s' "$plugins" | grep -q "\"id\": \"${PLUGIN_NAME}@${MARKETPLACE_NAME}\""; then
    echo "  uninstall ${PLUGIN_NAME}"
    "$cli" plugin uninstall "$PLUGIN_NAME" -y
  fi
  echo "  install ${PLUGIN_NAME}@${MARKETPLACE_NAME}"
  "$cli" plugin install "${PLUGIN_NAME}@${MARKETPLACE_NAME}" -y
}

sync_cursor() {
  echo "== Cursor 技能  ${CURSOR_SKILLS}"
  mkdir -p "$CURSOR_SKILLS"
  shopt -s nullglob

  local src name dest current
  while IFS= read -r name; do
    [[ -n "$name" ]] || continue
    src="${ROOT}/skills/${name}"
    dest="${CURSOR_SKILLS}/${name}"
    if [[ -L "$dest" ]]; then
      current="$(readlink "$dest")"
      if [[ "$current" == "$src" ]]; then
        echo "  ok     ${name}"
      else
        ln -sfn "$src" "$dest"
        echo "  relink ${name}"
      fi
    elif [[ -e "$dest" ]]; then
      echo "  skip   ${name}  （${dest} 已存在且不是软链）"
    else
      ln -s "$src" "$dest"
      echo "  link   ${name}"
    fi
  done < <(skill_names)

  local p target base
  for p in "$CURSOR_SKILLS"/*; do
    [[ -L "$p" ]] || continue
    target="$(readlink "$p")"
    case "$target" in
      "$ROOT/skills"/*)
        base="$(basename "$p")"
        if [[ ! -f "$ROOT/skills/${base}/SKILL.md" ]]; then
          rm "$p"
          echo "  unlink ${base}"
        fi
        ;;
    esac
  done
}

main() {
  local cli
  cli="$(find_cli)"
  sync_plugin_json
  sync_claude "$cli"
  sync_cursor
  echo
  echo "完成。Claude 需要重开会话。"
}

main "$@"
