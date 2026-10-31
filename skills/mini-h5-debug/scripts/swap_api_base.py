#!/usr/bin/env python3
"""本地测试前把请求层的 API_BASE 换成 http://127.0.0.1:18112，测完改回。

源码里保持线上地址。local 先记下原来的值再替换；restore 按记下的值改回。
记下的值在 ~/.cache/mini-h5-debug/api-base.json，按文件绝对路径存。

用法：
  swap_api_base.py <请求层文件> local
  swap_api_base.py <请求层文件> restore
"""
import argparse
import json
import os
import re
import sys

LOCAL = "http://127.0.0.1:18112"
STATE = os.path.expanduser("~/.cache/mini-h5-debug/api-base.json")
LINE = re.compile(
    r"""^(?P<prefix>export const API_BASE = )(?P<q>['"])(?P<url>[^'"]+)(?P=q);?[ \t]*$""",
    re.M,
)


def die(msg):
    print("error: " + msg, file=sys.stderr)
    sys.exit(1)


def load_state():
    if not os.path.exists(STATE):
        return {}
    with open(STATE, encoding="utf-8") as state_file:
        data = json.load(state_file)
    if not isinstance(data, dict):
        die(STATE + " 不是地址记录")
    return data


def save_state(data):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as state_file:
        json.dump(data, state_file, ensure_ascii=False, indent=2)
        state_file.write("\n")
    os.replace(tmp, STATE)


def read_assignment(path):
    with open(path, encoding="utf-8") as source:
        text = source.read()
    found = list(LINE.finditer(text))
    if not found:
        die(path + " 里没有 export const API_BASE = \"...\"")
    if len(found) > 1:
        die(path + " 里 API_BASE 有多处")
    return text, found[0]


def write_url(path, text, match, new_url):
    line = match.group(0)
    semi = ";" if line.rstrip().endswith(";") else ""
    new_line = match.group("prefix") + match.group("q") + new_url + match.group("q") + semi
    new_text = text[: match.start()] + new_line + text[match.end() :]
    with open(path, "w", encoding="utf-8") as source:
        source.write(new_text)


def cmd_local(path):
    text, match = read_assignment(path)
    current = match.group("url")
    state = load_state()
    if current == LOCAL:
        if path not in state:
            die(path + " 已经是本机地址，没有记下线上地址")
        print("local already " + LOCAL)
        return
    state[path] = current
    save_state(state)
    write_url(path, text, match, LOCAL)
    print("local " + current + " -> " + LOCAL)


def cmd_restore(path):
    state = load_state()
    if path not in state:
        die(path + " 没有记下线上地址")
    online = state[path]
    text, match = read_assignment(path)
    current = match.group("url")
    if current != online:
        write_url(path, text, match, online)
    del state[path]
    save_state(state)
    print("restore " + current + " -> " + online)


def main():
    parser = argparse.ArgumentParser(description="本地测试临时替换 API_BASE")
    parser.add_argument("file", help="含 export const API_BASE 的文件")
    parser.add_argument("action", choices=["local", "restore"])
    args = parser.parse_args()
    path = os.path.abspath(args.file)
    if not os.path.isfile(path):
        die("找不到文件 " + path)
    if args.action == "local":
        cmd_local(path)
    else:
        cmd_restore(path)


if __name__ == "__main__":
    main()
